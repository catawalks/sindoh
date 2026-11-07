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

### Revised after a cold failure (`after_t5hang_boot.log`)

After hang 4 (nandboot_hang_analysis.md) the owner power-cycled the printer. That **cold** boot
failed exactly like the warm one:
- `start to download FW...` at 10.741 s, a full 253,996 bytes by
  11.266 s;
- `WLAN FW is active` at 11.777 s;
- a 0xa9 timeout at 22.317 s, with no response and no event.

**Today's boots:**

| Capture | Start | Root | Download → "active" | Wi-Fi |
|---|---|---|---|---|
| (morning, first report) | warm | ? | ? | failed |
| (morning) | warm | ? | ? | good |
| `coldboot1.log` | cold | **SD** (`/dev/mmcblk0p1`) | 11.493 → 12.007 | **good** |
| `nandroot1.log` | warm | **NAND** (`ubi0:filesystem`) | 11.289 → 11.797 | failed |
| `after_t5hang_boot.log` | cold | **NAND** | 11.266 → 11.777 | failed |

**What changes:**
- **Leftover chip state is no longer the lead.** A power cycle of the
  printer takes the 8782's supply with it unless the module sits on a
  standby rail. Nothing in software or the vendor files suggests one, but
  section 2 found no power control at all, so it can't be ruled out
  offline.
  - Did the owner switch off at the mains, or with the front power key?
    A soft-off could leave rails up.
  - The chip comes back in its boot ROM either way (both failures did a
    full download). So a remaining rail would only matter if the RF or
    power-management side keeps state the boot ROM doesn't reset.
- **Firmware timing isn't the difference either.** Failed and good boots
  have the same 0.5 s download and the same ~510 ms from the last block to
  the first command. Nothing on the host side looks slower on the failing
  boots.
- **What the failures share: the NAND root.** Both captured failures
  booted from mtd6; the only captured success booted from SD. It's an
  old pattern: the D2 failure coincided with the boot-time UBI scan
  (nand_boot_cmdline.md), and the uniprocessor m1-net, where the CPU is
  busier, failed every time.
  - On a NAND-root boot, the minutes around the insmod are full of NAND
    work: UBI attach and scan (7.0–8.2 s), UBIFS "recovery needed" and
    deferred recovery (8.3–9.9 s), then every file init reads.
  - Our NAND read path (patch 0010) moves data by **PIO** and
    **busy-polls** NDSR in a `cpu_relax()` loop. That costs a lot of CPU,
    plus SoC bus traffic to the NAND controller, for every page.
  - How that would stop a firmware *on the chip* from starting isn't
    known. Possible paths:
    - a host-side USB timing duty, e.g. a late SOF or a slow IN token
      just as the firmware brings up its USB side;
    - contention on the SoC bus or memory affecting the EHCI;
    - supply droop when NAND programs coincide with the 8782's RF
      calibration.
  - **Two NAND-root failures and one SD success are not proof.** The
    morning boots need their root recorded.

**Correction (full 11-07 tally from the main session).** All five boots
ran kernel 5b17e2ec from mtd0:

| # | Time | Start | Root | Capture | Wi-Fi |
|---|---|---|---|---|---|
| 1 | ~09:35 | warm | card | `nandboot1.log` (from 21 s on: the same 0xa9 dump, `last_event_index = 0`) | **failed** |
| 2 | ~10:05 | warm | card | `nandboot2.log` (nearly empty) | good |
| 3 | ~11:15 | cold | card | `coldboot1.log` | good |
| 4 | ~11:28 | warm | NAND | `nandroot1.log` | **failed** |
| 5 | ~12:05 | cold | NAND | `after_t5hang_boot.log` | **failed** |

- **The card root failed too** (boot 1). So the NAND root isn't the
  common factor. Card root: 1 of 3 failed; NAND root: 2 of 2; warm 2 of
  3; cold 1 of 2.
- Every boot, card roots included, attached and scanned mtd6 at
  ~7–8 s. So some NAND load comes before every insmod. The NAND root
  only adds more (UBIFS recovery, file reads).
- All three failures have the same signature: full download, then no
  command response and **no event of any kind**.

**Candidate order (re-ranked):**

| | Candidate | Fits | Test |
|---|---|---|---|
| **A** | **EP1 IN not serviced after the download.** The vendor reads EP1 at once and waits up to 2 s for INIT_DONE. Mainline sleeps ~500 ms with no IN read pending, then submits the RX URB and sends FUNC_INIT | Card and NAND root, warm and cold: a race, about 50% here. "No event at all" in 10 s fits a firmware whose INIT_DONE wasn't collected in time and that went no further | **The INIT_DONE read (fix item 2), built as a test kernel.** It logs whether INIT_DONE comes, and when. If the failures stop, A is the cause; if INIT_DONE never comes on a failing boot, the firmware didn't start (go to B/C/D) |
| B | Load during the firmware's first second: NAND PIO busy-poll, UBI/UBIFS work, bus or supply load | NAND root 2 of 2 against card root 1 of 3. Too few boots to separate it from chance; at most a contributing factor | T0 below: cold boots on each root. A NAND-root boot with the Wi-Fi insmod delayed until the NAND is idle |
| C | Leftover chip state (a rail not cut) | Cold 1 of 2 failed: weak | How the owner powered off (mains or front key) |
| D | Supply droop during RF start-up | Speculative | A scope on the module's 3.3 V |

### The "T5 hang" was not T5 (correction)

The hard hang reported as T5's turned out to be unrelated to Wi-Fi:
- The Debian root has no kmod, so `rmmod` and `insmod` were "not found"
  (rc 127); only `busybox rmmod/insmod` exist. Nothing touched the
  driver.
- The serial command was never even echoed, so the board was most likely
  hung already. It was the errata kernel's first NAND-root run, idle,
  ~25–30 min after boot.
- That hang is analysed as hang 4 in nandboot_hang_analysis.md: patch
  0010's NAND paths and the remaining errata gaps, not USB.
- The earlier claim here that "USB/8782 activity is in two of the hard
  hangs" is withdrawn. Hang 1's Wi-Fi churn is the only such case.
- T5 itself (does a second download recover the chip?) is still untested.

**All module commands on this root need `busybox`:** `busybox rmmod`,
`busybox insmod`. The command lines in this doc are written that way.


### T5, run properly (2026-11-07, NAND root, kernel 5b17e2ec)

Run on the cold NAND-root boot where Wi-Fi had failed, with `busybox`,
`debug_mask=0x20000037` and netconsole:

1. **`busybox rmmod mwifiex_usb`, then `mwifiex`:** clean, rc 0.
2. **Reload:**
   - `USB is not the winner 0xf00dface`, then `FW download over, size 0
     bytes`. The chip was running firmware, and the first word it sent
     back was a **command-response header** (`MWIFIEX_USB_TYPE_CMD`).
   - `WLAN FW is active`, then `DNLD_CMD: 0xa9 ... seqno 0x1`.
   - After 10 s the timeout: no response, no event, and this time
     **`cmd_sent=1`**. The bulk OUT never completed: the chip NAKs it.
     That differs from the boot failure (`cmd_sent=0`, OUT accepted).
3. **Unload, then `USBDEVFS_RESET` on 2-1.1:** 0.3 s later, an oops in
   softirq context: "Unable to handle kernel paging request at virtual
   address bf034ae4 when execute", PC inside the unloaded module.
   "Fatal exception in interrupt", then `panic=10` rebooted it.
4. **After that warm reboot the 8782 didn't enumerate at all** ("device
   descriptor read/64, error -110", "device not accepting address, error
   -110"). It needs a power cut.

**The oops: a mainline mwifiex_usb bug.** Trace resolved against the
errata build's vmlinux (5b17e2ec):

| Address | Function |
|---|---|
| c0353adc (LR) | `__usb_hcd_giveback_urb` → calls `urb->complete`, which is `bf034ae4` in the unloaded mwifiex_usb |
| c0353eb0 | `usb_giveback_urb_bh` |
| c003aea0, c003b214 | `process_scheduled_works`, `bh_worker` (the BH workqueue) |
| c002a7e8, c002a328, c002a560, c002a640 | `tasklet_action`, `handle_softirqs`, `__irq_exit_rcu`, `irq_exit` |
| c0008ea8 | `__irq_svc` |
| c005486c, c0054afc, c055ac6c, c067ef10 | `do_idle`, `cpu_startup_entry`, `rest_init`, `start_kernel` (CPU0 idle) |

- r0/r4 is the URB (kmalloc-128), and r5 = `0xffffffb9` = **-71
  (-EPROTO)**: the status of a transfer aborted by the port reset.
- **Cause:** `mwifiex_usb_free()` (`usb.c`) kills the RX command URB, the
  RX data URBs and the TX data URBs. For the **TX command URB** it only
  calls `usb_free_urb(card->tx_cmd.urb)`, with **no `usb_kill_urb()`**.
  `usb_free_urb` just drops the driver's reference: the host controller
  keeps its own while the URB is queued.
- In step 2 the FUNC_INIT OUT transfer was NAKed forever (`cmd_sent=1`).
  So its URB was still queued when the failed init unregistered the
  device and when the module was unloaded.
- The port reset finally completed it (-EPROTO), and the HCD called
  `mwifiex_usb_tx_complete` in freed module memory.
- The suspend path (`mwifiex_usb_suspend`) does kill `tx_cmd.urb`. Only
  the free path misses it.
- **Fix (one line, upstream-worthy):** `usb_kill_urb(card->tx_cmd.urb)`
  before `usb_free_urb(card->tx_cmd.urb)` in `mwifiex_usb_free()`.
- A second, harmless leak on the same path: after a failed init,
  `mwifiex_usb_disconnect()` returns early (`card->adapter` is NULL) and
  skips `usb_put_dev()`.

**What T5 says about the chip:**
- **A reload doesn't recover it, and a USB port reset wedges it
  further.** After the reset and a warm reboot it doesn't even answer
  SET_ADDRESS. Only a power cut clears that. So the vendor-style
  recovery (fix item 2's `usb_reset_device()` and re-download) is
  **ruled out** for the 8782 as it stands.
- **The firmware isn't completely dead, though.** It answered the reload's
  probe block with a `0xf00dface` command-response header. Either the
  response was stale, left in its EP1 IN FIFO since boot, or it was a
  fresh reply to the probe. The header alone doesn't say which. Either
  way its USB side moved data 30+ min after the failed boot.
- **If it was stale** (for example the boot's FUNC_INIT response, seqno
  1), then on the failing boot the firmware *did* start and answer,
  and **the host never received the answer**. The RX URB on EP1 IN was
  pending the whole 10 s and only completed when killed (`Card is
  removed: -2`).
  - That points at the USB link right after the firmware takes over
    from the boot ROM, not at the firmware's start.
  - The classic candidate is a **data-toggle mismatch**: the firmware
    re-initialises its endpoints at DATA0, and the host's endpoint state
    still carries the boot ROM's toggle. The host then silently drops the
    first packet as a duplicate, or the exchange stalls.
  - Whether it bites depends on how many packets each side exchanged
    before the switch, which retries and timing can change. That could
    give a 1-in-2 or 1-in-3 failure rate.
  - The vendor driver would hide it: a failed FW_READY read fails the
    probe, then `usb_reset_device()` re-enumerates the device. That
    resets every toggle, and the re-probe finds the firmware running.
- **If it was fresh**, the firmware answers probe blocks but not FUNC_INIT,
  and NAKs the OUT that carries it: a firmware stuck early in its init.

**The one log line that decides it:** the 16 bytes behind
`0xf00dface` on a reload after a failed boot. The second word is the
sequence number, and the command-response header that follows names the
command (`0x80a9` = FUNC_INIT response). This needs the logging patch in
section 5, item 0. It's a modules-only build, so it can be insmodded on
the running 5b17e2ec kernel with no NAND write.

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

## Stock control: 11 of 11, so it's the host side (2026-11-07)

Same printer, same 8782: the stock kernel 3.2.0-g67a8e16 (the rescue
card's copy, RAM boot), the stock root copy, and `mlan.ko` + `usb8xxx.ko`
loaded with no parameters by `install_wifi_drivers.sh`.
- **11 of 11 boots brought Wi-Fi up:** 1 warm from our system (with our
  mwifiex loaded), then 10 warm stock-to-stock reboots. Each scan found
  16–20 networks, with no error, retry or reset line.
- The stock reboot unloads nothing either.
- Our system on the same hardware: cold 1 of 3 failed, warm 2 of 3
  failed.

**So the chip, its firmware and the board are cleared.** What's left is
how our kernel starts the chip: mwifiex's sequence, or our EHCI setup.

### The concrete differences right after the download

From the vendor binaries (`mlan.ko` `wlan_dnld_fw`, `usb8xxx.ko`
`woal_init_fw_dpc`, the 3.2 `Image` `mv61xx_ehci_run`) against mwifiex
6.18 with patch 0004:

| Step | Stock (USB8782, card type 2) | Ours |
|---|---|---|
| Before the image | **No winner probe:** `feature_control` is 0 for card type 2, so `check_winner` = bit 8 = 0 | A 2068-byte all-zero "pseudo block" on EP1 OUT, then a read of the reply on EP1 IN. That's an extra exchange with the boot ROM before the first real block |
| The image | Blocks of header + data + 4 bytes, each followed by a sync read on EP1 (100 ms timeouts, 3 tries) | The same |
| **Right after the last block** | **An EP1 IN read is posted at once:** `read_data_sync`, 2048 bytes, 2000 ms. It must return `0xBEEFFACE` with cause 7 (INIT_DONE), or the download counts as failed | **No IN read for ~500 ms** (`msleep(500)`). Then `rx_init` submits the RX URBs, and INIT_DONE (if it comes) is handled as an ignored event |
| First command | FUNC_INIT after INIT_DONE has been read, and after the RX/TX URBs are set up | FUNC_INIT ~510 ms after the last block, right after the RX URBs |
| Soft reset or USB reset | None on this path (`usb_reset_device` only for the 8797's boot PID, on a failed probe, and on disconnect) | None |
| EHCI tuning | `mv61xx_ehci_run` ends with **`TXFILLTUNING` (controller +0x164) = `0x00100000`**: TX FIFO threshold 16 | generic-ehci leaves `TXFILLTUNING` at its reset value |
| USBMODE | Host mode only (`|= 3`, in `tdi_reset`), no stream-disable | — (the controller runs in host mode) |

The decisive one, given every failure's signature (the image is accepted,
then nothing on EP1 IN, and in T5 a `0xf00dface` reply still waiting in
the chip): **stock reads EP1 the moment the firmware starts, and ours
doesn't for half a second.** The `TXFILLTUNING` difference is the only
EHCI-side one found. A TX FIFO underrun would corrupt OUT packets under
memory load, so it's worth testing alongside.

### Patch 0013: the stock start sequence, measurable

`kernel/m1/patches/0013-mwifiex-usb-8782-vendor-start.patch`, behind
`CONFIG_MWIFIEX_USB_8782_START` (default **n**, so no other image
changes):
- **No winner probe for the 8782:** the whole image, as stock does.
  `mwifiex_usb.usb8782_winner=1` brings the probe back.
- **EP1 read right after the download, up to `usb8782_ready_ms`
  (default 2000), instead of `msleep(500)`.** It logs one of:
  - `8782: INIT_DONE after N ms`;
  - `8782: after N ms, L bytes instead of INIT_DONE: <hex>`;
  - `8782: no INIT_DONE in 2000 ms (-110)`.

  FUNC_INIT follows in every case, so a missing INIT_DONE and a failed
  FUNC_INIT can be told apart. `usb8782_ready_ms=0` brings the sleep back.
- **The winner reply is logged** in hex when the probe is on (the
  `0xf00dface` question from T5).
- With the probe off, a failed download fails the probe instead of
  "assuming the firmware runs".
- **The URB-leak fix:** `usb_kill_urb(card->tx_cmd.urb)` in
  `mwifiex_usb_free()`.

Build: `VARIANT=nandboot HANGTEST=wifidbg ./build.sh`
(`variants/nandboot-wifidbg.config`).
- **Built 2026-11-07:** `m1-nandboot-wifidbg-modules.tar`, md5
  `7b5e745747074cf3a834c1fefe3e0894` (317,440 bytes).
  - `mwifiex_usb.ko` md5 `ef7100b4…`, `mwifiex.ko` md5 `4c2a8c4e…`.
    Use both, as a pair.
  - vermagic `6.18.59 SMP mod_unload ARMv7 p2v8`, the same as 5b17e2ec's.
  - Its full config differs from the errata image's only in the new
    option and the initramfs path.
- Not loaded on the printer yet.
- With the probe off, a chip that already runs firmware (as after T5) is
  sent the whole image anyway, as stock would. The download then fails,
  and the probe with it, cleanly (the URB fix covers the unload).

Only the modules tar is needed. The
kernel config is otherwise the mtd0 one (5b17e2ec) and there's no module
versioning, so the modules `busybox insmod` on the running mtd0 kernel.
No NAND kernel write is needed.

**Measurement** (each run with `debug_mask=0x20000037`, serial capture,
cold and warm mixed). Install the wifidbg `.ko`s next to, not over, the
normal ones (e.g. `/lib/modules/6.18.59/wifidbg/`), and have init.mainline
insmod from there with the parameters under test:

| Run | Parameters | Expected if the missing EP1 read is the cause |
|---|---|---|
| W1 | defaults (stock sequence) | 0 failures in ≥ 10 boots, each with `8782: INIT_DONE after ~N ms` |
| W2 | `usb8782_ready_ms=0` (sleep back, still no probe) | Failures return |
| W3 | `usb8782_winner=1` (probe back, INIT_DONE read kept) | Shows whether the probe matters on its own |

If W1 still fails, look at its log line:
- `no INIT_DONE`: the firmware didn't start even when read the stock way.
  Then the EHCI tuning is next.
- INIT_DONE seen, then a 0xa9 timeout: the start is fine, and the first
  command or its response is lost.

**The EHCI tuning test needs no build.** The 8782 is on bus 2,
`f9048100.usb`, so its controller base is 0xf9048000:

```sh
busybox devmem 0xf9048164        # read TXFILLTUNING first (read-only)
busybox devmem 0xf9048164 32 0x00100000   # stock's value, before the insmod
```

The write changes a live USB controller register, so it gets the owner's OK
like any hardware write. Stock does the same write in `mv61xx_ehci_run`,
on every host controller at start. If it helps, it belongs in the DT or
the EHCI glue, not in a script.

## W1: INIT_DONE arrives, the first command still dies (2026-11-07)

Patch 0013's modules (`mwifiex_usb.ko` ef7100b4), default parameters, NAND
root, warm `busybox reboot -f`: **3 of 3 failed**. Every run showed:
- `FW download over, size 253996 bytes`;
- **`8782: INIT_DONE after 56 ms`** (56 ms all three times);
- `WLAN FW is active`;
- the 0xa9 timeout, then "Card is removed".

The T3 runs before it (unpatched modules) failed 7 of 7 warm.

- **Candidate A (the unread EP1 IN) is answered: no.** Read the stock
  way, the firmware starts and reports INIT_DONE at once, on the same
  boots that then fail.
- So the firmware is alive. The loss is on the first-command path: the
  0xa9 OUT doesn't reach the firmware's command handler, or its response
  on EP1 IN doesn't reach the driver.
- (The first command is 0xa9 = **FUNC_INIT**. GET_HW_SPEC, 0x03, comes
  second.)
- W2 (the sleep back) wasn't run, and isn't needed: the first-command
  loss happens with the INIT_DONE read too.

**What mlan does between INIT_DONE and its first command** (vendor
binaries):
1. `woal_init_fw_dpc` → (cal-data `request_firmware`, unused here) →
   `woal_usb_rx_init`:
   - the RX command URB on EP1, plus `woal_usb_submit_rx_data_urbs` on
     EP2, both before init, as mainline does;
   - then `woal_usb_tx_init`, `mlan_set_init_param`, `mlan_init_fw`.
2. `wlan_adapter_init_cmd`: **FUNC_INIT (0xa9) first**, then 0x8f (cal
   data, only if configured), GET_HW_SPEC (0x03), 0xd9, ... That's
   mainline's order too.
3. No delay, no command or ACK in reply to INIT_DONE, no extra request.
4. Commands go out through `woal_write_data_async`: a **bulk** pipe on
   EP1 (`PIPE_BULK | ep << 15 | devnum << 8`), **`URB_ZERO_PACKET`**, the
   command length as is. That's mainline's `mwifiex_usb_construct_send_urb`
   exactly.

**So the driver sequences now match.** INIT_DONE is read the stock way, the
same first command goes out the same way, and the same RX URBs are
pending. Stock works 11/11 and ours fails ~100% warm. What still differs:
- the **USB host side**: 6.18's generic EHCI with our PHY driver (patch
  0003) against the vendor's `ehci_mv61xx` with
  `TXFILLTUNING = 0x00100000`;
- **USB data toggles after the firmware takes over its endpoints.** If
  the firmware re-initialises EP1 after sending INIT_DONE (back to
  DATA0), the host's next OUT on EP1 can be taken as a duplicate: the
  device ACKs and drops it, which looks exactly like `cmd_sent=0` with
  no answer. Or the response IN can be dropped the same way by the host.
  Stock would hit this too unless its timing differs, so it's a
  candidate to test, not a conclusion.

### Patch 0014: where the first command dies (trace modules)

`kernel/m1/patches/0014-mwifiex-usb-8782-first-command-trace.patch`, on
top of 0013, under the same `CONFIG_MWIFIEX_USB_8782_START`.
`HANGTEST=wifitrace` builds it (`variants/nandboot-wifitrace.config`).
The wifidbg tar that W1 used stays as it was.
- **Built 2026-11-07:** `m1-nandboot-wifitrace-modules.tar`, md5
  `02595f17bffdaf215dda96314ff3d113`. It holds `mwifiex_usb.ko` md5
  `8f941909e18ecd10ec8a004eb9894ace`, and `mwifiex.ko` `4c2a8c4e…`, the same
  as wifidbg's.
- vermagic as 5b17e2ec's, and the config is otherwise the errata one.
  Not loaded on the printer yet.

Logged with no `debug_mask` needed (`dev_info`, prefix `8782 trace:`), for
the first `usb8782_trace` (default 24) EP1 transfers after the download:
- every **EP1 IN submit**: bulk or int, size, pending RX command and data
  URBs;
- every **EP1 IN completion**: status, length, and the first 16 bytes
  (`0c000000 ...` style; a response starts `ce fa 0d f0`);
- every **EP1 OUT submit** (the command): bulk or int, length, first 16
  bytes, pending IN URBs at that moment;
- every **EP1 OUT completion**: status and `actual_length` against the
  length;
- **3 s after the first command**, the state: RX command URB status
  (-115 = still queued), actual length, pending counts, TX command URB
  status, `cmd_sent`, `cmd_resp_received`.

Two experiments, off by default:
- **`mwifiex_usb.usb8782_clear_halt=1`:** after INIT_DONE, before the
  first command, CLEAR_FEATURE(ENDPOINT_HALT) on EP1 IN/OUT and EP2
  IN/OUT. That resets the data toggle on both sides; each result is
  logged.
- **`mwifiex_usb.usb8782_cmd_delay_ms=N`:** a pause after INIT_DONE before
  the first command (try 200 or 1000).

The trace needs `usb8782_ready_ms` left at its default (it's armed by
the INIT_DONE read).

**How to read a failing run:**

| Seen | Means |
|---|---|
| OUT done status 0, length 12 of 12, then no IN done until the 3 s dump shows the IN URB at -115 | The chip took the command at USB level and never answered: a toggle-dropped OUT, or a firmware-side wait. Try `clear_halt=1` next |
| OUT done with an error (-71, -32, -110 ...) | The OUT failed on the bus: USB host/PHY side (TXFILLTUNING, PHY) |
| OUT never completes (dump shows OUT -115) | The chip NAKs the command endpoint, as in T5 step 2 |
| An IN done that's not a response (an event) or has a bad length | The response path, and the bytes say what came |
| `clear_halt=1` makes the boot work | Data-toggle desync after the firmware takes over. The fix is the clear-halt step, 8782-only, after INIT_DONE |

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
**A cold failure followed (`after_t5hang_boot.log`), and a card-root
failure was found in the tally.** The leading suspect is the missing
INIT_DONE read (candidate A). NAND load (B) is at most a contributing
factor, and leftover chip state (C) is weak.

## 4. Telling the hypotheses apart: logging, no rebuild needed

The kernel has no `DYNAMIC_DEBUG` and no `USB_MON`. mwifiex's own module
parameter is enough:

```sh
# init.mainline, for the test boots only (instead of the plain insmod):
busybox insmod mwifiex.ko debug_mask=0x20000037   # MSG|FATAL|ERROR|CMD|EVENT|WARN
busybox insmod mwifiex_usb.ko
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

### Exact settings for the next test boots

Nothing here needs a rebuild: kernel 5b17e2ec has `NETCONSOLE=y`,
`NETCONSOLE_DYNAMIC=y`, `CONFIGFS_FS=y`, `MAGIC_SYSRQ=y` and
`MAGIC_SYSRQ_SERIAL=y`.

1. **Serial capture of the whole boot, from U-Boot on.** This is the
   primary record:
   - The kernel log buffer is only 32 KB, and a boot already fills ~30 KB.
     `CMDLINE_FORCE` rules out `log_buf_len=`, so `dmesg` afterwards can
     lose the early lines.
   - mwifiex's lines are `dev_info`. They reach the console at the default
     console log level (7).
2. **mwifiex debug mask.** In init.mainline, for the test boots only:

   ```sh
   echo "dp200-init: wifi: insmod (debug_mask 0x20000037)" > /dev/kmsg
   busybox insmod .../mwifiex.ko debug_mask=0x20000037   # MSG FATAL ERROR CMD EVENT WARN
   busybox insmod .../mwifiex_usb.ko
   echo "dp200-init: wifi: insmod done" > /dev/kmsg
   ```

   On every boot, good or bad, that adds:
   - `cmd: DNLD_CMD: 0xa9 ...` and `cmd: CMD_RESP: 0xa9 ...`;
   - each `event_cause 0x...`, in particular whether `0x7` (INIT_DONE)
     ever comes on a good boot, and when;
   - the winner-check value if the firmware is ever reused.

   The good boots matter as much as the failures: candidate A predicts
   that a good boot shows `event_cause 0x7` right after the RX URB goes
   in.
3. **A small per-boot Wi-Fi log that survives the reboot.** About 60 s after
   the insmod, init.mainline appends
   `dmesg | grep -E 'usb 2-1|mwifiex|dp200-init|ubi0|UBIFS'` to
   `/var/log/dp200-wifi.log`, with a header line giving the date, the root,
   and how the previous boot ended (written by the reboot path, or
   "unknown" after a power cycle). That's a few KB per boot on the root.
4. **Netconsole**, set up in init.mainline as soon as eth0 has its address:

   ```sh
   mount -t configfs none /sys/kernel/config 2>/dev/null
   d=/sys/kernel/config/netconsole/pc
   mkdir -p $d
   echo eth0           > $d/dev_name
   echo <printer eth0 IP> > $d/local_ip
   echo <PC IP>        > $d/remote_ip
   echo 6666           > $d/remote_port
   # remote_mac stays ff:ff:ff:ff:ff:ff (broadcast) unless set
   echo 1              > $d/enabled
   dmesg -n 8                       # every level to the consoles
   echo 1 > /proc/sys/kernel/sysrq
   ```

   On the PC, a UDP listener on port 6666 writing to a file (e.g. `ncat -u
   -l 6666 > netcon.log`, or a 5-line Python socket loop).
   - **Limitation:** eth0's link comes up only at ~19–24 s, after the
     Wi-Fi window (insmod ~10.7 s, timeout ~22 s), and netconsole sends
     only messages logged after it's enabled. So for the boot failure,
     items 1–3 are the record. Netconsole is for the later rmmod/insmod
     steps and for hangs, as long as the CPU and GMAC still run.
   - Don't move the Wi-Fi insmod after eth0 to get it on netconsole: that
     changes the timing under test.
5. **For each boot, note:** warm or cold (and for cold, mains or front
   key), the root, and the result (mlan0 address or the 0xa9 dump).

### Before any more rmmod/insmod tests

A hang leaves no log unless something gets it off the board before the
CPUs stop. In order of value:

1. **The `m1-nandboot-errata-dbg` image** (5685822, md5 `d4350cf0…`):
   - Its timer-0 watchdog warm-resets the board 30 s after a hang.
   - Its ramoops keeps the console log in RAM across that reset, so after
     the reboot `/sys/fs/pstore/console-ramoops-0` holds the hung boot's
     log up to its last line.
   - It's the only option that survives a bus stall: printk writes into
     RAM synchronously, and netconsole needs a working CPU and GMAC to
     send.
   - **It's a debug image with a hardware watchdog, so the owner's OK
     comes first.** Run nandboot_hang_analysis.md's 5-step check first
     (watchdog fires with `hang_wdt_nokick`, and pstore survives).
   - It's a different kernel from mtd0's, booted from the SD card or by
     kexec. Its modules tar must match it, so don't reuse mtd0's
     modules.
2. **Netconsole to the PC** (planned), plus `dmesg -n 8` so every level
   goes out, and `echo 1 > /proc/sys/kernel/sysrq`. If serial still takes
   a BREAK, send BREAK + `l` (backtrace of all CPUs) and BREAK + `w` before
   power-cycling.
3. **One step per command, each marked in the kernel log**, waiting and
   checking that the board still answers before the next:

   ```sh
   m() { echo "T5: $*" > /dev/kmsg; }
   m "state"; cat /sys/bus/usb/devices/2-1.1/bcdDevice \
       /sys/bus/usb/devices/2-1.1/authorized; grep -i ehci /proc/interrupts
   m "busybox rmmod mwifiex_usb"; busybox rmmod mwifiex_usb; m "busybox rmmod mwifiex_usb done"; sleep 3
   m "busybox rmmod mwifiex";     busybox rmmod mwifiex;     m "busybox rmmod mwifiex done";     sleep 3
   m "busybox insmod mwifiex";    busybox insmod mwifiex.ko debug_mask=0x20000037; m "done"; sleep 3
   m "busybox insmod mwifiex_usb"; busybox insmod mwifiex_usb.ko; m "busybox insmod mwifiex_usb returned"
   ```

   Ping over Ethernet between steps from the PC. Then the last marker
   in the log, and whether the ping stopped, say which step hung.
4. **Separate USB from the driver** in a second run. Before any mwifiex
   step, take the 8782 off and back on the bus with `echo 0 >
   /sys/bus/usb/devices/2-1.1/authorized` and `echo 1`, with the modules
   not loaded. If that alone hangs, the hang is in the USB host/hub path,
   not in mwifiex.

Not wanted until a hang log exists: the `USBDEVFS_RESET` part of T5 (a
port reset on a chip that just failed is the riskiest step).

For the Wi-Fi failure itself, the most informative cheap test is
**candidate B: cold boots from the SD root against the NAND root**, with
`debug_mask=0x20000037`. It needs no rmmod at all.

### The reboot-loop matrix

The main session runs it. N is each test's run count. For each run, record
whether `CMD_RESP: 0xa9` came, and whether `event_cause 0x7` came.

| Test | How the previous boot ends | N | Expected, if the leftover chip state is the cause |
|---|---|---|---|
| T0 | **Cold boots, SD root against NAND root** (candidate B), no rmmod | 5 + 5 | Tests B, not leftover state: if only the NAND-root boots fail, B. A delayed insmod on the NAND root (after the UBIFS recovery, NAND idle) is the follow-up |
| T1 | Power cycle (cold) | 10 | All good, with `event_cause 0x7` before or around the first command |
| T2 | `reboot -f` with mlan0 associated | 20 | About 2 of 3 fail as in `nandroot1.log`: a full download, then no event and no response |
| T3 | `ip link set mlan0 down; busybox rmmod mwifiex_usb mwifiex; reboot -f` (FUNC_SHUTDOWN sent, radio off) | 20 | **All good, or clearly fewer failures** than T2 |
| T4 | `reboot -f` with mlan0 down but the modules loaded | 10 | Between T2 and T3: shows whether association or power save matters |
| T5 | **After a failed boot**, without rebooting: `busybox rmmod mwifiex_usb mwifiex; insmod ...` (3 times), then the same with a USB reset of the 8782 in between (`USBDEVFS_RESET`, below) | each failure | Shows whether **a second download recovers** the chip, so whether a driver-level retry is a usable fix |

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

**After T5 (2026-11-07), first:**

0. **Logging, modules only** (mwifiex.ko + mwifiex_usb.ko built against
   5b17e2ec, insmodded with `busybox insmod`; the kernel in mtd0 is
   unchanged):
   - hex-dump the first 32 bytes of the winner-check response and of
     every command response or event during init (MSG level);
   - read EP1 right after a real download for up to 2 s, and log
     whatever comes: INIT_DONE (`0xBEEFFACE`, cause 7), something
     else, or nothing. This replaces `msleep(500)`, as in item 2;
   - log the endpoint toggle/halt state (`usb_gettoggle`) for EP1 IN/OUT
     before and after the download.

   On the next failing boot this tells "the firmware answered and the host
   lost it" from "the firmware never answered".
1. **Fix the URB leak:** `usb_kill_urb(card->tx_cmd.urb)` in
   `mwifiex_usb_free()`. Without it, any later USB reset or disconnect
   after a failed init can oops.
2. **If the host lost the answer (toggle):** after a real download, and
   before the RX URBs go in, resynchronise EP1 IN/OUT (and the data
   endpoints) with `usb_clear_halt()`. CLEAR_FEATURE(ENDPOINT_HALT)
   resets the toggle on both sides, a far gentler step than a port reset.
   Test it on failing boots first, as a module option.
3. **Never `usb_reset_device()` the 8782** (T5 step 3 wedged it until a
   power cut). Drop the vendor-style reset from fix item 2 and 4 below.

**Revised order after the cold failure:**
- **Item 2's INIT_DONE read comes first.** It's cheap and matches the
  vendor. It services EP1 IN from the moment the download ends
  (candidate A), and its log line says whether the firmware ever
  started: no INIT_DONE within 2 s means it didn't.
- Then, only if T0 shows a clear root difference (candidate B), defer the Wi-Fi insmod until the
  NAND root is idle (init.mainline), as a workaround with a known cause,
  and look at the NAND path's load.
- Item 1 (shutdown hook) stays worth doing, but it no longer explains
  the failures by itself.

1. **Shut the firmware down at reboot** (if T3 confirms it).
   - Add `.shutdown = mwifiex_usb_shutdown` to `mwifiex_usb_driver`. It
     does what disconnect does while the device is still attached:
     `mwifiex_deauthenticate_all()`, then FUNC_SHUTDOWN.
   - `reboot`, `reboot -f` and `poweroff` all run `device_shutdown()`,
     so the radio is off and the firmware stopped before the warm
     restart.
   - It doesn't cover a panic or watchdog reset; item 2 does.
   - Until it's built: put
     `ip link set mlan0 down; busybox rmmod mwifiex_usb mwifiex` in init.mainline's
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
