# 8782 Wi-Fi sometimes not coming up at boot (mainline)

Offline analysis, 2026-11-07. Inputs:
- the stock Marvell driver binaries (`/lib/modules/8782/mlan.ko` and
  `usb8xxx.ko`, "M2614459-GPL-(FP69)", disassembled with objdump);
- the stock boot logs and scripts;
- mainline mwifiex 6.18.59 with our patch 0004;
- our earlier Wi-Fi notes (wifi_88w8782.md, wifi_join_test1.md,
  debian_root_boot.md).

Nothing here was run on the printer.

## The failure

From the main session's description of the failing boot (2026-11-07),
after a warm `busybox reboot -f` (the 8782 keeps power through it):

| Time | Line | What it means |
|---|---|---|
| ~10.9 s | `usb 2-1.1: WLAN FW is active` | mwifiex prints this after **any** successful `dnld_fw`, downloaded or not. Only the lines before it tell the two apart (see below) |
| ~21 s | command-timeout dump, `last_cmd_id` ... `a9`, `data_sent=0 cmd_sent=0` | The first init command, `HostCmd_CMD_FUNC_INIT` (0xa9), got no answer in `MWIFIEX_TIMER_10S`. `cmd_sent=0` means the bulk OUT transfer completed: the chip **acknowledged the bytes at USB level** but never answered |
| ~21 s | `_mwifiex_fw_dpc: unregister device`, then `Card is removed: -2` repeated | The normal teardown after a failed init: the killed receive URBs complete with -ENOENT. This is noise, not a second fault |

The next warm reboot came up fine.

The 0xa9 timeout isn't new. It was seen:
- on cold boots of the uniprocessor m1-net (wifi_join_test1.md: every
  time, while every SMP kernel worked);
- in D1 and D2 (debian_root_boot.md, nand_boot_cmdline.md);
- and now after a warm reboot.

So one explanation has to cover both cases: the chip just downloaded and
booted, and the chip already running firmware.

## 1. How the vendor driver handles the 8782 compared with mainline

From the vendor binaries:
- The USB ID table maps 1286:2040 to card type 2. Its version string is
  "USB8782"; card type 1 is "USB8797".
- `woal_init_sw`: `feature_control` is `0xffffffff`, but **0 for card
  type 2**.
- `wlan_dnld_fw` (mlan.ko) takes its `check_winner` from bit 8 of
  `feature_control`. So:
  - **the 8797 does the winner check and doesn't wait afterwards;**
  - **the 8782 does a full download with no winner check, then waits for
    the firmware's ready event.** It reads EP1 for up to 2000 ms. The
    header must be `0xBEEFFACE` (an event) with cause 7, which is
    `EVENT_INIT_DONE` in mainline's fw.h. Otherwise it fails with "FW_READY
    event is not received".
- `woal_usb_probe` sets the 8782's `boot_state` to READY (2) and the
  8797's boot PID to DNLD (1).
  - The USB reset after a download (`woal_init_fw_dpc`, "WLAN FW is
    downloaded" → ~250 ms → `usb_reset_device`) applies only to the
    8797's boot PID. That matches stock's dmesg: one probe, no
    re-enumeration.
  - With `boot_state` 2 (the 8782), **probe failure and disconnect
    (rmmod) both call `usb_reset_device`.**

| Step | Vendor SDK (8782) | Mainline + patch 0004 |
|---|---|---|
| Chip already running firmware (warm reboot) | No winner check: always downloads. What a running 8782 does with download blocks isn't known (see the open questions) | Winner check: running firmware answers with bit 31 set ("USB is not the winner", WARN level, so normally hidden). The download is skipped and the **running firmware is reused, whatever state it is in** |
| Download fails or gets no answer | Probe fails, then `usb_reset_device` | Patch 0004 **turns the failure into success**: "8782: no boot ROM answer, assuming the firmware runs" |
| After the download | **Waits for EVENT_INIT_DONE** (≤ 2 s), and only then sends the first command | `msleep(500)` (100 ms in the first images). Then the RX URB is submitted and FUNC_INIT sent. INIT_DONE, if it comes, is handled as an ordinary event and ignored (`sta_event.c`: `case EVENT_INIT_DONE: break`) |
| Unbind / rmmod | FUNC_SHUTDOWN (`mlan_shutdown_fw`), then `usb_reset_device` | Deauth + FUNC_SHUTDOWN, no USB reset |
| Reboot / poweroff | Nothing; stock never unloads the driver | Nothing: `mwifiex_usb_driver` has **no `.shutdown`**, and `reboot -f` runs no rmmod. The firmware stays up, still associated, with power save as it was |
| Command timeout | `wlan_cmd_timeout_func` logs it | `mwifiex_cmd_timeout_func`; during init this ends the init, and the device is unregistered |

### The "Failed to get firmware" path

This happened when mwifiex was built in and probed from the initramfs:
- `request_firmware_nowait` → `_mwifiex_fw_dpc(NULL)` → "Failed to get
  firmware" → unregister. **The chip is never touched:** no download, no
  command, no reset.
- init.mainline then toggled `authorized` 0/1. That is a logical
  unbind/rebind with SET_CONFIGURATION, **not a chip or port reset**.
- So the re-enumerate doesn't damage the chip. It just ran the normal
  probe a second time.
- With mwifiex as modules, insmodded after the root (and its firmware)
  is mounted, the condition never triggers: the dmesg has no "Failed to
  get firmware".
- In this morning's failing boot the probe came from the insmod
  (~10.9 s), so the re-enumerate most likely didn't run. Check the init
  log for "8782 re-enumerated".
- **The re-enumerate is a workaround for the built-in ordering. That
  ordering is gone, so the re-enumerate can go** (see the fix).

## 2. Wi-Fi reset or power GPIO: none found

| Source | Result |
|---|---|
| Our DTS (`88pa6170-dp200.dts`) | Only the EHCI nodes and the USB PHY. No regulator, reset or power-sequence node for the hub or the 8782 |
| Vendor kernel (`vendor_System.map`, `vendor_hwtables.txt`) | No Wi-Fi, WLAN, hub-reset or power symbols. The 8782 is plain USB behind the on-board hub |
| Stock scripts (`rcS`, `install_wifi_drivers.sh`, `wifi_sta_start.sh`, `stop_wifi_sta.sh`, `/lib/modules/8782/unload`) | insmod/rmmod and ifconfig only; no GPIO, no power control. Stock never unloads before a reboot |
| hardware_notes.md | Nothing on the Wi-Fi module's power or reset |

So software can't power-cycle or hardware-reset the 8782. The only
possibilities left are below; each needs one read-only check on the
printer.
- **Hub port power.** The 8782 sits on port 1 of the Terminus 1a40:0101
  hub (2-1). If the hub does per-port power switching *and* the board
  wires it, the kernel can turn port 1's VBUS off and on. Check: read the
  hub descriptor's `wHubCharacteristics` (bits 1:0: 00 ganged, 01
  individual, 1x none). The read-only snippet is at the end.
- **The SDK's soft reset.** mlan.ko has "DNLD_CMD: SoftReset" and
  usb8xxx has `woal_request_soft_reset` (reached from
  `/proc/mwlan/config`). It puts the firmware back into the boot ROM, but
  it needs a firmware that still answers commands.
- **A board trace to a SoC GPIO**, e.g. a PDn pin on the module. Nothing
  in software points to one. It would need a look at the board (the
  Mainboard_Photos folder) or a continuity test.

## 3. The most likely root cause

Patch 0004 strays from the vendor's 8782 sequence in three places, and
together they explain both the warm and the cold failures:

1. **It reuses a firmware in an unknown state (the warm reboot).**
   - Nothing shuts the firmware down at reboot: there's no `.shutdown`
     and no rmmod.
   - So after `reboot -f`, the new kernel's winner check finds the old
     session's firmware still running. That firmware may still be
     associated, in IEEE power save, holding queued events or RX data
     for a host that's gone, or in the middle of a command.
   - Then FUNC_INIT goes into that state. The USB layer ACKs it, but the
     firmware doesn't answer.
   - Whether it answers depends on what the firmware was doing at the
     moment of the reboot: **intermittent**.
   - The vendor never adopts a running 8782 firmware this way.
2. **It waits a fixed time, not for INIT_DONE (the cold boot).**
   - After a real download, the vendor waits for the firmware to say
     it's up. Mainline sends FUNC_INIT after a fixed delay.
   - If the new firmware is still booting, the command is dropped, with
     the same 10 s timeout and the same symptom.
   - This fits the earlier cold-boot failures: the uniprocessor kernel
     with the 100 ms delay, and the D2 boot whose UBI scan ran at the
     same time.
3. **It hides a silent chip.** "No boot ROM answer, assuming the
   firmware runs" turns "the chip didn't answer at all" into "WLAN FW is
   active". Then the 10 s timeout follows, and the real cause is lost
   from the log.

**Not the cause:**
- **The re-enumerate.** It touches no chip state, and with modules it no
  longer runs.
- **Ethernet.**
- **The hard-hang errata.** The failures predate them and happen on
  boots that otherwise work.

This is a **hypothesis until the reboot-loop test** separates (1), (2)
and (3). The log lines below tell them apart.

## 4. Telling the hypotheses apart: logging, no rebuild needed

The kernel has no `DYNAMIC_DEBUG` and no `USB_MON`. mwifiex's own module
parameter is enough:

```sh
# init.mainline, for the test boots only (instead of the plain insmod):
insmod mwifiex.ko debug_mask=0x20000037   # MSG|FATAL|ERROR|CMD|EVENT|WARN
insmod mwifiex_usb.ko
```

Logged at those levels (all `dev_info`, so they reach the serial
console):

| Line | Level | Tells you |
|---|---|---|
| `start to download FW...` / `info: FW download over, size 253996 bytes` | MSG | A real download: the chip was in the boot ROM |
| `USB is not the winner 0x...` then `FW download over, size 0 bytes` | WARN, MSG | **Firmware reused.** The value is the first word the chip sent back: `0xbeefface` is a queued event and `0xf00dface` a command response (both stale), anything else a reply to the probe block |
| `read_data_sync: failed` / `write_data_sync: failed`, then `8782: no boot ROM answer` | ERROR, MSG | **Silent chip** (3) |
| `event_cause 0x7` | EVENT | INIT_DONE came. Compare its time with the first `cmd: DNLD_CMD: 0xa9` line (2) |
| `cmd: DNLD_CMD: 0xa9, ...` then `cmd: CMD_RESP: 0xa9, result 0` or the timeout | CMD | Whether the first command was answered |
| `event_cause 0x...` **before** the first command, on a reused firmware | EVENT | Stale events from the previous session (1) |

Keep each boot's log across the reboot: the serial capture, or init.mainline
appending `dmesg | grep -E 'usb 2-1.1|mwifiex|mlan0'` to a file on the SD
card or the USB stick (not NAND, to avoid the writes).

### The reboot-loop matrix

The main session runs it. N is each test's run count, and each run
records whether the boot logged `CMD_RESP: 0xa9`.

| Test | How the previous boot ends | N | If (1) stale firmware | If (2) INIT_DONE race |
|---|---|---|---|---|
| T1 | Power cycle (cold) | 10 | All good | Some fail. `DNLD_CMD 0xa9` comes before `event_cause 0x7` |
| T2 | `reboot -f` with mlan0 associated | 20 | Some fail. "not the winner", maybe stale `event_cause` lines | No change from T1 |
| T3 | `ip link set mlan0 down; rmmod mwifiex_usb mwifiex; reboot -f` (FUNC_SHUTDOWN sent) | 20 | **All good** | Like T1 |
| T4 | `reboot -f` with mlan0 down but the modules loaded | 10 | Between T2 and T3: shows whether association/power save matters | — |

T3 vs T2 is the decisive pair. Read the hub descriptor (below) once,
anytime.

## 5. Proposed fix (not yet written or built)

In order of value. Items 1 and 2 are patch-0004 follow-ups, small and
8782-only.

1. **Shut the firmware down at reboot.**
   - Add `.shutdown = mwifiex_usb_shutdown` to `mwifiex_usb_driver`. It
     does what disconnect does when the device is still attached:
     `mwifiex_deauthenticate_all()`, then FUNC_SHUTDOWN.
   - `reboot`, `reboot -f` and `poweroff` all run `device_shutdown()`, so
     the next probe finds a stopped firmware. That's the state the 8797's
     PID_2 path (`insmod` after `rmmod`) uses every day.
   - It doesn't cover a panic or watchdog reset; item 3 does.
   - Until it's built: add
     `ip link set mlan0 down; rmmod mwifiex_usb mwifiex` to init.mainline's
     reboot and poweroff traps (`rc.dp200 stop` path). This is the same as
     T3.
2. **Wait for INIT_DONE instead of sleeping.** After a real download, read
   EP1 with `mwifiex_read_data_sync()` for up to 2000 ms. Accept
   `0xBEEFFACE` with cause 7, as the vendor does, and log anything else.
   This replaces `msleep(500)`, and it also consumes the event before
   the RX URBs start.
3. **Make a reused firmware safe, or don't reuse it.**
   - When the winner check says "not the winner":
     1. log the header word (MSG level, not WARN);
     2. drain EP1/EP2 IN with short reads until they time out, so
        stale events and data don't pile up;
     3. send FUNC_SHUTDOWN, then let the normal FUNC_INIT follow.
   - If FUNC_INIT still times out on a reused firmware, try the
     SDK-style soft reset once (back to the boot ROM, then a fresh
     download), as long as the firmware still answers.
4. **Drop the "assuming the firmware runs" fallback.**
   - If the chip doesn't answer the probe block, fail the probe with a
     clear message and `usb_reset_device()`, as the vendor does. Don't
     claim success.
   - If the hub turns out to switch port power, a port power-cycle can
     go here as the last resort.
5. **init.mainline:**
   - Remove the `authorized` 0/1 re-enumerate. With modules,
     the insmod always comes after the firmware is in place: the
     stock-NAND copy happens before the insmod.
   - Keep a short "8782: no mlan0 after 30 s" log line, so a failure
     is visible.

Items 1 and 2 are the vendor's behaviour (or mainline's own disconnect
path) moved to the right moment. They aren't workarounds. Item 3 covers
the resets that bypass shutdown.

## Open questions (for the printer, read-only)

- **What does a running 8782 do with a full download?** That's what the
  vendor does on a warm reboot. Does Wi-Fi under stock survive
  `reboot` (stock → stock)? If it does, the stock dmesg after it says
  how (e.g. "FW received Blk with CRC error" and a probe retry).
- **Does the hub switch port power?** Read-only, on mainline, from Python
  in the root:

  ```python
  import fcntl, struct, ctypes
  # USBDEVFS_CONTROL: GET_DESCRIPTOR(HUB), class request to the device
  buf = ctypes.create_string_buffer(16)
  req = struct.pack("BBHHHIP", 0xA0, 6, 0x2900, 0, 16, 1000,
                    ctypes.addressof(buf))
  fd = open("/dev/bus/usb/002/002", "rb+", buffering=0)  # bus 2, hub 2-1
  n = fcntl.ioctl(fd, 0xC0105500, req)   # _IOWR('U', 0, 16-byte struct)
  print(buf.raw[:9].hex(), "wHubCharacteristics bits 1:0 =",
        buf.raw[3] & 3)  # 0 ganged, 1 individual, 2/3 no switching
  ```

  Check the hub's device number with `ls /sys/bus/usb/devices/2-1/devnum`
  first.
