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

**The question, then:** why do the first commands after "WLAN FW is
active" get no answer on some boots, warm or cold?

### A good cold boot for comparison (`coldboot1.log`, 2026-11-07)

Power cycle, our mtd0 kernel:

| Time | Line | Note |
|---|---|---|
| 10.957 | `registered new interface driver mwifiex_usb` | insmod from init.mainline |
| 10.987 | `start to download FW...` | The boot ROM won the winner check: a real download |
| 11.493 | `FW download over, size 253996 bytes` | 0.5 s download |
| 12.007 | `WLAN FW is active` | Patch 0004's `msleep(500)` after the last block |
| 12.085 | `host_mlme: disable, key_api: 0` | The init commands **are answered**: FUNC_INIT, then the GET_HW_SPEC response gives the key API |
| 12.093 | `CMD_RESP: cmd 0x242 error, result=0x2` | `HostCmd_CMD_CHAN_REGION_CFG` (GET), sent unconditionally at init. FP69 (14.69.12.p50) predates it and refuses it. **Harmless**: the result is ignored and init goes on. It's on every good boot (also m1_boot7.log) |
| 23.357–23.466 | associate, EAPOL | Joined |
| 120.888 | `CMD_RESP: cmd 0x23f error, result=0x2` | `HostCmd_CMD_STA_CONFIGURE` (GET): `mwifiex_get_chan_info()`, run when userspace asks for the channel (cfg80211 `get_channel`, e.g. `iw dev mlan0 info`). FP69 doesn't have it either. **Harmless**: userspace just gets no channel |
| 126.001–126.010 | `Have pending ack frames!` ×2, then `successfully disconnected ...: reason code 7` | See "The reason-7 drop" below. It's not the boot failure |
| 129.950 | associated again | 4 s later |

The capture's first lines (`[4563.57]`, from the session before this
boot) show the same reason-7 drop and re-association 4 s later.

What a failing boot's capture must show, to place it in section 3:
- **"start to download FW..." present.** The download happened, as on
  this boot. Then the cold or warm difference is only the
  firmware's boot (hypothesis 2).
- **Absent, with "FW download over, size 0 bytes".** The firmware was
  reused (hypothesis 1).
- **`read_data_sync: failed` and "8782: no boot ROM answer".** A silent
  chip (hypothesis 3).

### The warm failure, captured (`nandroot1.log`, 2026-11-07)

This was the first boot from the NAND root, after a warm `busybox reboot -f`,
on the same kernel 5b17e2ec. Warm reboots that day: 2 of 3 failed. The one
cold boot was fine.

| Time | Line |
|---|---|
| 10.696 | `registered new interface driver mwifiex_usb` |
| 10.780 | **`start to download FW...`** |
| 11.289 | **`FW download over, size 253996 bytes`** |
| 11.797 | `WLAN FW is active` (after the 500 ms sleep) |
| 22.297 | `Timeout cmd id = 0xa9, act = 0x0`, `last_cmd_index = 1`, **`last_cmd_resp_index = 0`, `last_event_index = 0`**, `num_cmd_h2c_failure = 0`, `data_sent=0 cmd_sent=0`, `ps_mode=0` |
| 22.370 | `_mwifiex_fw_dpc: unregister device`, then `Card is removed: -2` |

**What this settles:**
- **After the warm reboot the chip was back in the boot ROM.** The
  boot ROM won the winner check and took the whole image, every block
  without a CRC error, as on the cold boot. Up to "WLAN FW is active",
  warm and cold boots log the same lines, with almost the same timing.
  So **hypothesis 1 (a reused stale firmware) and hypothesis 3 (a silent
  chip during the download) are ruled out** for this failure.
- **After the download, the new firmware never says anything.**
  - FUNC_INIT went out at USB level (no host-to-card failure,
    `cmd_sent=0`).
  - In 10.5 s there was no command response, and **no event of any
    kind**: `last_event_index = 0`, so no INIT_DONE either. The RX URB
    on EP1 was submitted before the command.
  - So the downloaded firmware didn't start, or started without a working
    USB side. It's not a command that came "too early": a firmware that
    booted late would still have sent INIT_DONE or answered within 10 s.
- **The difference between warm and cold is the chip's state before the
  download.** On a cold boot the chip is freshly powered. On a warm
  reboot it went back to the boot ROM without losing power, after the
  old firmware ran with the radio on and was never shut down (no
  FUNC_SHUTDOWN: no `.shutdown`, no rmmod).
  - How it got back to the boot ROM isn't known: the old firmware
    resetting itself on the USB suspend or bus reset, or something
    in the boot path.
  - Whatever did it leaves state behind (radio, clocks, power
    management) that a soft restart doesn't clear. A newly downloaded
    image then fails to start in about 2 of 3 cases.

So **hypothesis 2, recast:** after a warm reboot, the firmware image
downloads cleanly but often doesn't start. The earlier cold-boot
failures (uniprocessor m1-net, D2) need their own logs to say whether
they were the same thing.

### The reason-7 drop (a separate issue)

- Reason 7 is "Class 3 frame received from nonassociated STA". **The
  access point** deauthenticated or disassociated us because it no longer
  had us as associated while we sent data. The firmware reports it as a
  deauth/disassoc event (`sta_event.c` → `mwifiex_reset_connect_state`).
- "Have pending ack frames!" is mwifiex freeing frames still waiting for
  TX status at that reset. It's a consequence, not the cause.
- 102.6 s after the association. The 0x23f refusal 5 s earlier is
  probably unrelated: it's a local GET that never reaches the air.
- Usual causes are the AP's power-save or inactivity handling of a
  station in IEEE power save. mwifiex turns power save on by default,
  and it's not known whether stock does.
- **Test:** run `iw dev mlan0 set power_save off` after the join, then
  log with `iw event -t`. Does the drop still come about 100 s after each
  association? Is it periodic, e.g. the AP's group rekey?
- The 4 s reconnect works, so this is a glitch in the network, not a boot
  failure.

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

## 3. Why the first commands time out: the candidates

"WLAN FW is active" is the normal message after a download (see the good
cold boot above). The fault is that the first command (0xa9) after it
gets no answer. Patch 0004 strays from the vendor's 8782 sequence in
three places, and each one leads to exactly that symptom:

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

**Status after `nandroot1.log`:** (1) and (3) are ruled out for the
warm failures seen so far: the download happened. (2) holds in its
recast form: the image downloads cleanly, then the firmware never starts.
(1) and (3) stay in the fix list, because 0004 still has those gaps.

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

The main session runs it. N is each test's run count. For each run, record
whether `CMD_RESP: 0xa9` came, and whether `event_cause 0x7` came.

| Test | How the previous boot ends | N | Expected, if the leftover chip state is the cause |
|---|---|---|---|
| T1 | Power cycle (cold) | 10 | All good, with `event_cause 0x7` before or around the first command |
| T2 | `reboot -f` with mlan0 associated | 20 | About 2 of 3 fail as in `nandroot1.log`: a full download, then no event and no response |
| T3 | `ip link set mlan0 down; rmmod mwifiex_usb mwifiex; reboot -f` (FUNC_SHUTDOWN sent, radio off) | 20 | **All good, or clearly fewer failures** than T2 |
| T4 | `reboot -f` with mlan0 down but the modules loaded | 10 | Between T2 and T3: shows whether association or power save matters |
| T5 | **After a failed boot**, without rebooting: `rmmod mwifiex_usb mwifiex; insmod ...` (3 times), then the same with a USB reset of the 8782 in between (`USBDEVFS_RESET`, below) | each failure | Shows whether **a second download recovers** the chip, so whether a driver-level retry is a usable fix |

T3 against T2 decides whether a clean shutdown prevents the failure. T5
decides whether the driver can recover from it.

The USB reset for T5 (read-only apart from the reset itself; device path
from `cat /sys/bus/usb/devices/2-1.1/busnum devnum`):

```python
import fcntl
fd = open("/dev/bus/usb/002/003", "wb", buffering=0)   # 2-1.1, check devnum
fcntl.ioctl(fd, 0x5514)                                # USBDEVFS_RESET
```

Read the hub descriptor (in the open questions) once, anytime.

## 5. Proposed fix (not yet written or built)

In order of value. All of it is a 0004 follow-up and 8782-only. Items 1
and 2 depend on T3 and T5.

1. **Shut the firmware down at reboot** (if T3 confirms it).
   - Add `.shutdown = mwifiex_usb_shutdown` to `mwifiex_usb_driver`. It
     does what disconnect does while the device is still attached:
     `mwifiex_deauthenticate_all()`, then FUNC_SHUTDOWN.
   - `reboot`, `reboot -f` and `poweroff` all run `device_shutdown()`,
     so the radio is off and the firmware stopped before the warm
     restart.
   - It doesn't cover a panic or watchdog reset; item 2 does.
   - Until it's built: put
     `ip link set mlan0 down; rmmod mwifiex_usb mwifiex` in init.mainline's
     reboot and poweroff paths (`rc.dp200 stop`). That's T3.
2. **Wait for INIT_DONE, and retry the download when it doesn't come.**
   - After a real download, read EP1 with `mwifiex_read_data_sync()` for
     up to 2000 ms. Accept `0xBEEFFACE` with cause 7, as the vendor
     does. This replaces `msleep(500)`.
   - On a miss, fail in 2 s instead of a 10 s command timeout. Then
     `usb_reset_device()` (the vendor's reset on a failed probe) and
     download again, at most 2–3 times, logging each attempt.
   - Only worth it if T5 shows a second download can recover. If it can't,
     the last resort is the hub's port power (if the hub switches it),
     otherwise a clear "8782 needs a power cycle" message.
3. **Make a reused firmware safe** (no failure seen this way yet). When
   the winner check says "not the winner":
   1. log the header word at MSG level;
   2. drain EP1/EP2 IN until the reads time out;
   3. send FUNC_SHUTDOWN, then the normal FUNC_INIT.
4. **Drop the "assuming the firmware runs" fallback.** A chip that
   doesn't answer the probe block fails the probe with a clear message
   and `usb_reset_device()`, as the vendor does.
5. **init.mainline:**
   - Remove the `authorized` 0/1 re-enumerate. With modules, the insmod
     always comes after the firmware is in place.
   - Log "8782: no mlan0 after 30 s", so a failure is visible.

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
