# DP200 Klipper port - active task list

Rewritten 2026-11-02 from TODO.md (10-28), PROJECTS.md, the docs and the
session notes. "(user)" = needs the owner at a printer (heat, motion,
measurements). Larger, self-contained projects are in
[PROJECTS.md](PROJECTS.md). Finished items are at the end.
**Keep it current:** edit this file (and PROJECTS.md) in the same commit as
the work; it is how open items survive between sessions.

## Next (user at a printer)

1. **Work printer failed test print: diagnosed + fixed (2026-11-06).**
   Logs + G-code on the stick (Work_Printer_Logs/). Cause: UPC_STEP_BATCH
   bug - `MCU 'mcu' shutdown: Stepper too far in past` ~19 min in, on the
   first-layer solid infill (PrusaSlicer, 20 mm/s: the extruder at ~425
   steps/s, ~2.3 ms per step). After a batched block's last rising edge the
   STEP line stayed high for half an interval (~1.2 ms), so the next block
   started >1 ms late. Fix (fork 8d4fb4d8): the engine move leaves out the
   block's last step, which is stepped normally. kemu reproduces it (old
   build: shutdown; new: clean) and the test printer runs the fix
   (fm c313d379). **Left:** a real print on the test printer (user present),
   then a new payload for the stick - the stick's 60316e4 payload has the
   bug: don't print on the work printer with it.
1b. **New payload needed (agent, then user):** rebuild after the real print
   test of the stepping fix. It must also carry 2026-11-06's fixes: no Wi-Fi
   networks from the build printer (runtime.exclude: etc/dp200/
   wpa_supplicant.conf - the owner's HOME SSIDs and passwords had landed on
   the work printer; the current stick payload 60316e4 still contains them,
   never publish it), and the generic reboot text ("Rebooting now." instead
   of "The Sindoh logo comes next." - the logo may be the owner's own).
   Both edits are committed, not yet on a printer.
   **Built 2026-11-07 (night):** payload 5f3336e1 (84,402,575 B, unpacked
   241,909 KiB, BUILD 59134b5): fm.bin c313d379 (the batch fix), no Wi-Fi
   networks (checked: no etc/dp200/wpa_supplicant.conf), the new screen
   app; with a fresh unmistakable_klipper_install.she (d41963d2), on the
   stick in _update_rodin_KlipperInstall (old 60316e4 overwritten). Not yet
   installed anywhere; the stepping fix still needs its real print test.
1c. **Ethernet doesn't recover after a switch outage (work printer,
   2026-11-06):** the switch lost power/its uplink overnight; after it came
   back other devices got IPs, the printer only after a reboot. Check
   dp200-netd.sh: link down/up handling and DHCP retry (udhcpc restart on
   carrier up, lease renewal when the DHCP server was gone).
   No network log was kept on the work printer. 2026-11-07: dp200-netd.sh
   now restarts udhcpc when eth0 has a cable, DHCP mode and no IPv4
   address for 30 s (whatever the cause); syntax-checked, on the dev card,
   not yet exercised (an outage test needs the owner or a cable pull).
2. **Screen features not yet used on hardware (user):** the calibration
   wizards (Z HEIGHT paper test, PROBE OFFSET, PID TUNE, SAVE Z OFFSET),
   LOAD switching the heater off, OBJECTS (skip one object in a print with
   two or more), WiFi -> SAVED (PREFER / FORGET).
3. **PRINT_START pause-and-ask, YES (user):** a real print answered YES on
   the screen (NO was tested: nothing moved, the print was cancelled).
4. **A real Mainsail update** from SYSTEM -> UPDATE (only CHECK NOW tried).
5. **Dryer leftovers (user):** STOP DRYING, PRINT_START during drying,
   FORCE=1 above the 70 C sheet limit.
6. **Homing clearance (code + user validation):** investigate changing the
   HOME ALL sequence to create a few mm of Z clearance before X homing, so
   the nozzle is less likely to drag across failed-print material left on
   the bed. Confirm the safe direction and coordinates for this bed-moving
   Z axis, then validate the sequence on the printer.

## Needs the user, longer

6. **Input shaping:** the FLY-ADXL345 runs Klipper and was read on the PC;
   cdc-acm.ko loads on the printer (docs/input_shaping.md). Left: head and
   bed mounts (measurements, then print them), then SHAPER_CALIBRATE on the
   printer, then rebuild the payload.
7. **Beeper:** `[output_pin beeper] pin: io:pwm10`, a short test beep, pick
   the PWM value; the dryer's end signal uses it automatically; then M300.
8. **Retraction test** (two towers), then the slicer profiles' speeds and
   retraction; recheck pressure advance (0.30) with dry filament.
9. **Mesh front limit:** depth of the bed's front grip handle (maybe lower
   mesh_min Y from 30).
10. Optional: a 6-7 mm/s Z lift test (10 stalls lifting; stock is 5.05).

## Decision open

**Low-priority project - cartridge chip read/write:** reading and writing
the cartridge chip remains work the owner wants to pursue, but it is not a
prerequisite or blocker for other tasks. Do not wait on this project during
a session unless the owner explicitly makes it the current task. Chip writes
still require the owner's explicit OK.

11. **Updates:** decided 11-03 (PROJECTS #10): NAND only = Mainsail and
    Moonraker from upstream, Klipper from our releases; SD card = all
    upstream, built on the printer. To build with the end-goal install.
11a. **First public release** = the current installer, later: after the
    screen/feature work and the faster-stepping tests (PROJECTS #10).
11b. **G-code storage** (PROJECTS.md #11): decided 11-03: optional SD card
    (inside) or USB stick, in tiers; NAND-only stays a full install with
    managed space (~140-150 MB free once our root replaces the stock one).
11c. **Per-printer data for the full mtd6 replacement**
    (internal_firmware_plan.md, 11-03): all Sindoh software is in mtd5
    (factory 2017) or the 2020 update; karas.db (model, serial, calibration)
    rebuilds itself from Sindoh's copy on mtd4 at the first boot after a
    recovery (db_setup), so no backup is required. Optional: the installer
    keeps the live karas.db + network files on the stick for the latest
    calibration and Wi-Fi. mtd4 stays never-written.
11e. **End-goal install sequence** (docs/end_goal_install_plan.md):
    stages 1-9 approved by the owner 11-03; owner at the printer for each
    write stage. **Stage 1 done 2026-11-07** (mtd0 kernel area rewritten
    from our kernel, raw = baseline, stock boot OK). **Stage 2 done
    2026-11-07** (mtd6 revert from mtd5, karas.db back from mtd4, then the
    2020 Sindoh update). The dev printer is plain stock 2020 now: the
    interim /klipper hook is gone, so Klipper runs only from our SD kernel.
    Stage 3 normal path done 11-07 (the card's raw gap now holds
    m1-nandboot; m1-debian-nandw goes back with tools/sd_raw_install.sh).
11d. **End-goal revert = a Sindoh update stick** (owner, 11-03;
    kernel/revert_to_stock_plan.md): our system recognizes a Sindoh DP200
    update stick, asks, restores stock from mtd5 (mtd0 kernel part, mtd6
    root + apps) from RAM, reboots; stock then runs the update from the same
    stick and restores karas.db from mtd4. No backup files from us needed.
    Accepted risk: power loss during the mtd0 write -> serial, as with
    Sindoh's own updates.

## Agent (no user needed)

12. **Wi-Fi stability and saved-network priority:** power saving reduced
    drops on the test printer (68 deauths before the change, none over about
    a day as of 2026-11-03 08:40). **2026-11-06: 125 deauths** (reason 15)
    with power management still off, and the printer is on the
    lower-priority Fios-kVGD7 (192.168.1.204) instead of Niholedotcom; its
    Ethernet (10.10.0.147) is plugged in now, and 10.10.0.21 answers pings
    from another device. Separate open bug: after falling back to
    a lower-priority SSID, the printer does not rejoin a higher-priority
    SSID when it becomes available. Reproduce and trace preference/watchdog
    reconnect logic; the displayed ordering alone does not verify priority.
    (2026-11-07: on Niholedotcom, priority 22; Fios-kVGD7 not in the scan,
    so the fallback couldn't be reproduced from here.)
    Check stability on the upgraded work printer too.
13. **Wi-Fi summary page accuracy:** SYSTEM -> NETWORK -> WIFI can show
    inaccurate data; the owner saw the Ethernet IP displayed on the WIFI
    summary page on the test printer. Trace the page's data source and state
    updates, then clean it up to display Wi-Fi information only and avoid
    presenting stale or Ethernet values as Wi-Fi details.
    **Fixed 2026-11-07:** the page's Address came from self.ip (the main
    address, Ethernet's with a cable in); it is now wpa_supplicant's own
    ip_address, "-" when not connected. test_dp200_wifi_screen.py and
    test_dp200_screen.py: 0 failures on the printer.
14. **Faster stepping** (docs/faster_stepping_plan.md, phases 1-3 approved
    11-02): done so far: engine register map (COM_STP +0x78 candidate),
    `CONFIG_UPC_STEP_SINGLE` (fork branch fast-stepping, default off) halves
    step interrupts, emulator-identical; engine run 11-03 (driver off):
    +0x78 = 24-bit edge down-counter, engine clock 197.9 MHz. Phase 2b/3b
    done: `CONFIG_UPC_STEP_BATCH` (constant blocks as engine moves, default
    off) passes the kemu engine model (25 steps: 1 engine start instead of
    25, steps 40 ticks after schedule instead of 840). Phase 4 (11-03):
    both builds home and move with no lost steps (drift 0.000-0.04 =
    measurement steps, 0 busy hits); ABORT resets the edge counter
    (handled). Probe 11-03: batch = gcc build (0.007 spread, means within
    0.0001 mm). Cube with BATCH 11-03: completed, 1,507 s (gcc 1,502),
    0 busy hits; measured X 20.0 / Y 19.9 / Z 20.3 (gcc 20.1/20.0/20.2).
    Surfaces as before -> **BATCH is the default** (fork f035bdbc, test
    printer and the payload rebuilt 11-03). Left: the idle-loop counter;
    the work printer gets it with its upgrade. klippy's mcu_awake doesn't see UPC step load: add an idle-loop
    counter to upc_step_stats. Printer is on the gcc build.
15. **Probe settling after homing:** on either firmware the first ~5 touches
    after G28 read 0.015-0.02 mm high, then repeat to 0.007. Check whether
    BED_MESH_CALIBRATE right after homing is affected; maybe a few warm-up
    touches first.
16. **Prebuilt (zig) UPC images, motion:** loaded and run 2026-11-02 (see
    Done); still untested with motion (homing/moves need the owner). They
    are the fallback; the printer runs the gcc builds from /opt/dp200.
17. **End-goal offline prep (2026-11-06, kernel side session; nothing run
    on hardware):**
    - done: the stock U-Boot command line and size budget
      (docs/kernel/nand_boot_cmdline.md: CONFIG_CMDLINE_FORCE, no
      ubi.mtd, image ~3.2 MB of 7.75 MB); write guard v2 (patch 0010:
      up to 4 window ranges, each inside mtd0 2-63 / mtd3 / mtd6,
      compiled); `VARIANT=nandboot` (full + NAND writes, no 8782
      firmware, USB storage) with the stage-3 initramfs
      (kernel/m1/initramfs/nandboot/init: marked card/stick root, else
      mtd6; Sindoh/revert stick + touch, or the root marker -> revert from
      RAM; broken root -> "touch to recover"), checked offline by
      kernel/m1/tools/test_nandboot_init.sh (9 paths + the initramfs list).
    - mtd-utils (owner OK 11-06): Debian trixie's 1:2.3.0-1 source, by
      apt from deb.debian.org (signed InRelease -> Sources -> .dsc ->
      sha256 d1242d44...; infradead.org didn't resolve from here), in
      D:/DP200/kernel/src/mtd-utils. 11 static tools in the initramfs
      instead of BusyBox's (ubiattach/ubidetach/nandwrite there take other
      options than dp200-revert.sh uses). Image 2,649,276 bytes = 33 % of
      mtd0's 7.75 MB. Their options were checked against the sources'
      getopt strings; qemu-arm can't run these static binaries under WSL,
      so they first run on the printer (stage 3).
    - **stage 3 stick path (2026-11-07):** a queued input event started a
      revert unasked; it failed at its first check (dirname/id missing),
      nothing written. Built 11-07 (m1-nandboot 33d2e5d2): the screen app
      asks on a Sindoh stick (two confirmations -> /.dp200-revert +
      reboot; test_dp200_revert_popup.py, 13 checks, run on the printer's
      Python); the initramfs reverts on the marker (removed first on a
      card root) and asks only with no working root (dp200-hold: drained,
      armed after 0.3 s quiet, 2 frames, 3 s hold; test_dp200_hold.sh 11
      cases); dirname/id/basename added; test_nandboot_init.sh 10
      scenarios + the tool list. Hardware, 11-07: dp200-hold on the real
      panel (no touch: timeout; 0.4 s tap: not counted; hold: "held" after
      3.0 s); the popup with the stick: both questions shown, NO leaves no
      marker and no reboot request. Open: the full YES-YES revert (stage
      7), the broken-root prompt on hardware, a "Back to stock" button,
      maybe better wording for the second question (owner: fine for now). Wi-Fi: build mwifiex_usb
      as a module, loaded by init.mainline (owner prefers this over the
      re-enumerate, which may be tied to the 11-07 hang).
      Boot-time Wi-Fi failure, 11-07 tally: warm reboots (busybox reboot
      -f) 2 of 3 failed (command 0xa9 timed out ~10 s after "WLAN FW is
      active", then unregister / "Card is removed"); 1 cold boot fine.
      Root cause wanted, not a workaround (owner): offline driver
      comparison with the kernel session (docs/kernel/wifi_boot_failure.md),
      then a reboot-loop measurement here (owner's go-ahead first).
      Later 11-07: a NAND-root cold boot failed too (cold 1 of 2, warm 2
      of 3; card root 1 of 3, NAND root 2 of 2). T5 on that failed boot
      (busybox rmmod/insmod: the Debian root has no kmod, plain
      rmmod/insmod are "not found"; netconsole to the PC on UDP 6666):
      unload clean; reload reuses the running firmware ("not the winner
      0xf00dface", 0 bytes), which still doesn't answer cmd 0xa9;
      USBDEVFS_RESET after the unload -> oops in IRQ context (PC in the
      unloaded module: a leftover URB callback), panic, reboot by
      panic=10; after that warm reboot the 8782 doesn't enumerate at all
      (-110). So the chip keeps power and state across warm reboots, and
      a reload or USB reset can't recover a failed start; the fix has to
      make the first start reliable. Needs a power cycle to get Wi-Fi
      back.
      Stock control (11-07 afternoon, 2GB-SD rescue card: the card's
      stock kernel copy RAM-booted with tools/rescue_stock_boot.sh, the
      stock root on the card, no NAND/env writes): **11 of 11 Wi-Fi
      starts OK** (1 warm from ours, 10 warm stock-to-stock; scan 16-20
      networks; no error lines). Same firmware and hardware, so the
      firmware is cleared: the cause is our host side (mainline mwifiex's
      start sequence or our USB). Ours right after: **7 of 7 warm boots
      failed**, every one a full download then no answer (leftover chip
      state ruled out for these); T3's clean shutdown untestable while
      nothing starts. Kernel session asked for a measurable driver patch
      (mlan's post-download sequence + the URB-kill fix).
      **Correction (same day): my test loops graded wrongly**: the serial
      echo of the check command contains "Card is removed", so every boot
      counted as FAIL. Re-graded on kernel lines only: unpatched warm boots
      ~7 of 10 failed (t3c r1-r5: 3 of 5), not 7 of 7.
      **Fixed by patch 0013** (stock-like start: no winner probe, EP1
      read right after the download, FUNC_INIT after INIT_DONE, plus the
      URB-kill fix): **19 of 19 warm boots OK** (0013: 13, 0014 trace: 6),
      INIT_DONE after 56 ms every time. The 0013 mwifiex_usb.ko
      (ef7100b4) is installed on the dev printer's NAND root (originals in
      /var/backups/mwifiex-5b17e2ec/). Next: CONFIG_MWIFIEX_USB_8782_START
      on by default (kernel session, 8c9bbd2), then cold boots with the
      owner and a long Wi-Fi soak. TXFILLTUNING (stock 0x00100000, ours
      0x00020000) noted but not needed for this.
      **mtd0 now holds m1-nandboot dc3b5f20** (errata + the Wi-Fi fix as
      defaults; owner's OK 11-07 afternoon), written from the NAND root
      with the new tools/mtd0_kernel_update.sh (window 1741,4091;2,63, put
      back after; readback, U-Boot block and 0xff tail checked), modules
      948b3350 installed. First boot: NAND root, INIT_DONE after 56 ms,
      mlan0 10.10.0.21, Klipper ready.
    - **NAND-root hard hang #2 (11-07 ~14:52), kernel dc3b5f20:** during
      the NAND + Wi-Fi soak (tools/nand_wifi_soak.sh), ~23 min after boot,
      near-idle; no ping, serial or panic; netconsole's last line a normal
      soak ping. Both NAND-root hangs at ~23-30 min uptime; the card-root
      SD soak (82 min) passed on the same errata code. Suspect: patch
      0010's NAND path under UBIFS (PIO, busy-poll) or a periodic UBI/UBIFS
      job. Kernel session analysing; no more NAND-root runs until it has a
      proposal (watchdog + last-NAND-command record). Release blocker.
      The nanddbg debug image (0685c985, watchdog + ramoops + NAND step
      trace, owner's OK) went to mtd0 and **didn't boot**: it stops right
      after "Uncompressing Linux... done" (no console line; the moved DTB
      at 0xAE2748 lies inside the decompressor's target 0x833500-0xAE48A0).
      Recovered: 4GB-SD swapped in, errata 5b17e2ec RAM-booted from its
      gap, dc3b5f20 + modules 948b3350 put back with mtd0_kernel_update.sh;
      boots from mtd0 again (NAND root, Wi-Fi). Owner's rule since: RAM-boot
      every kernel before it goes to NAND. Kernel session fixing nanddbg.
      Meanwhile (11-07 evening) tools/hang_logger.sh runs on dc3b5f20
      (started by hand, stops at reboot): once a second it appends NAND
      read stats, UBI max_ec/avail, dirty/writeback, nr_dirtied/written,
      IRQ counts (nand, mmc, usb2, eth, timer1), IPI resched/function-call
      per CPU and ctxt to the 4GB-SD (/var/log/dp200-hang/<boot>.stat,
      fsynced each line) plus the live dmesg (.dmesg), and copies the
      stat line to the PC (port 9006); netconsole on. First readings: the
      NAND controller raised 4 IRQs since boot (busy-polled), all device
      IRQs on CPU0, CPU1 takes ~3x CPU0's function-call IPIs.
      Hang 6 (dc3b5f20, NAND root, 1337 s): the logger showed no NAND reads
      for 820 s and no erases before it, steady counters, nothing on the
      card after the PC's last line.
      **Hang 7 caught by the nanddbg trace (e6cdb8a6, RAM-booted first per
      the owner's rule):** watchdog checks passed (kicks keep it up, nokick
      resets the board, the ring survives the reset); its second boot
      froze at ~26 s, the watchdog reset it, and the next nanddbg boot
      printed the ring. It ends inside a page read: cmd for page 0x1bd58
      (mtd6 block 1781), then the RDDREQ wait ("rdd") with no end, not even
      a timeout: a CPU stuck in the NDSR access itself (bus stall), all on
      cpu0. Normal reads take ~150 us there. Kernel session analysing
      (what the vendor driver does between stop and the next command).
      mtd0 holds nanddbg for the hunt (owner's OK); dc3b5f20 goes back
      after. nanddbg has no pstore fs (console ramoops not readable).
      Polling vs interrupt: nanddbg (polling) in mtd0 reached trace boot 10
      on its own (I caused boots 3 and 11 only): ~6 unobserved watchdog
      resets in ~40-60 min idle on the NAND root, most likely freezes.
      **Fix candidate: patch 0016** (kernel session, 709334c): reads sleep on
      the controller's read-data/uncorrectable interrupts like the vendor
      driver (it reads NDSR 4-6 times per page; we polled ~150 times).
      nandirq 1f33eb43 RAM-booted from the 4GB-SD gap: rdd_irq Y,
      interrupts counting, Klipper ready. 4-hour read soak running
      (tools/nand_read_soak.sh: drop_caches + full root read every 2 min),
      with nanddbg in mtd0 as the watchdog fallback.
      **Result: nandirq froze too (~490 s), outside any NAND step.** The
      ring ends on a complete read at the end of pass 1 (isr ~155 us after
      cmd, every step balanced), NAND idle for ~1 min before the freeze
      (heartbeat to 490.75 s, read stats unchanged). Like hang 6 (no NAND
      reads for 820 s first). So the freezes aren't the read poll; hang 7's
      ring ending in rdd was probably the read in flight during the boot
      read storm. What separates hangs from no hangs: NAND root (UBI
      attached, UBIFS mounted, mtd6 window open) vs card root (detached,
      window none). Next tests proposed to the kernel session: NAND root
      with the window none; card root with UBIFS on mtd6 mounted rw idle;
      a trace of all controller accesses incl. program/erase.
      **nandpcs 3ec9c45b (nandirq + a PC sample every 10 ms per CPU to
      0x1e101000), RAM-booted on the NAND root, read soak: no freeze in
      14163 s (3 h 56 min, 11-07).** 70 full reads of / after drop_caches,
      NAND stats 7968475,5,1532,0,... (5 corrected, no fail/tmo/unc), UBI
      max_ec 129, dmesg clean apart from boot-time mwifiex CMD_RESP lines.
      The owner called the soak satisfied. The only difference from
      nandirq (froze at 490 s) is the 10 ms per-CPU sampling interrupt, so
      it may hide the hang (WFI/idle time or IPI timing). Sent to the
      kernel session with two splitting builds: nandirq with idle/WFI off
      and no sampler, or the sampler at 100 ms. mtd0 still holds nanddbg
      e6cdb8a6. No normal build goes back in mtd0 until this is understood
      and the build is RAM-booted first.
      **Hang 9 (11-07 ~22:30): the same nandpcs image, written to mtd0
      (owner OK, KUPDATE OK) and booted by U-Boot from NAND, froze at about
      143 s** during the 1-hour read soak's 2-minute idle gap. The
      watchdog reset it, and the next boot printed the trace and the PC
      samples: both CPUs' samples stop within 15 us of each other. cpu0 was
      in do_idle; cpu1's last sample was in xas_next_entry (a page-cache
      fault-around, SVC, IRQs on). The last NAND step was 24 s earlier, a
      complete read, and the SD stat log shows NAND idle until its last
      line. So the sampler doesn't hide the hang. The 3 h 56 min run
      (loaded from the card gap) was most likely luck: nandirq also loaded
      from the card gap and froze at 490 s. Test runs now boot from mtd0,
      the end-goal configuration (the RAM boot is only the pre-write
      check). Console in the shared notes (hang9_mtd0_nandpcs_serial.txt).
      mtd0 now holds nandpcs (3ec9c45b), so every freeze resets and prints
      its own samples.
      **Hang 10 (11-07 23:25): nandtick 9586a6d3 (tick check on timer 3 /
      cpu1), RAM-booted first, then in mtd0 with modules 37b536ff, froze at
      about 825 s from mtd0.** It froze silent: the tick check printed nothing
      (no panic, the watchdog reset), pings and the console probe stopped
      together, and both CPUs' PC samples stop within about 50 us of each
      other. That fits a bus stall with both CPUs stuck. NAND had been idle
      for 73 s (the last ring step was the end of TAR 3). Last samples: cpu0
      in __mmap_region, just after uvc_video_decode_isoc (ustreamer streams
      the USB camera all the time); cpu1 in lock_vma_under_rcu / page-fault
      code. A camera-off soak (ustreamer stopped) was proposed to the
      kernel session. Logs are in the shared notes (hang10_*). mtd0 holds
      nandtick; the old modules are in /var/backups/mods-bfd2c0a7.tar on the
      NAND root.
      **Hang 11 (11-07 23:57): camera-off soak (ustreamer killed, "CAMOFF
      ok"), nandtick from mtd0, froze at about 683 s.** The camera is ruled
      out. Silent again: no tick-check output, console and ping stopped
      together. This time NAND was mid-read: the ring ends on the read's
      ISR entry (status 1802) at 683.148 s, with no rdd-end after it.
      cpu1's last sample was set_pte_range under filemap_map_pages. In
      hangs 9, 10 and 11, one CPU is in page-fault fault-around / PTE code
      at the freeze (a lead for PJ4B page-table-walk coherency, not proof).
      Sent to the kernel session; logs in the shared notes (hang11_*).
      **Hang 12 (11-08 00:39): nandpte 7ee63c26 (page-table writes cleaned
      as the vendor kernel does; patch 0019), RAM-booted first, then in mtd0
      with modules 8f06a39f, froze at about 98 s from mtd0** during the first
      full read. The clean doesn't fix it. Silent again. The NAND ring ends
      exactly like hang 11: the read's ISR entry (status 1802), here on cpu0
      while cpu1 issued the read, with nothing after it. cpu0's last sample
      was set_ptes (fault-around). The ID line: MMFR3 00102211 (the CPU
      claims a coherent table walk and broadcast maintenance). Next per the
      kernel session: nandup d7861757 (one CPU), needs the owner's OK. Logs
      in the shared notes (hang12_*).
      **nandup d7861757 (maxcpus=1), RAM-booted first, then from mtd0 with
      modules dd208ffb: the full 2-hour soak passed (11-08 00:55-02:56).**
      IRQSOAK DONE, 27 passes; NAND 3055430 reads, 27 corrected, no fail,
      tmo or unc; no oops, tick-check or reset; the console answered
      throughout; 9 single lost pings out of about 7,660. So the freeze
      needs both CPUs. Next: nandmb 5f696673 (two CPUs, the DDR
      controller drain write off), under the owner's standing OK for these
      tests.
      **Hang 13 (11-08 03:14): nandmb 5f696673 (two CPUs, mc_drain=0),
      RAM-booted first, then from mtd0 with modules 1a6ec314, froze at about
      172 s.** The drain write isn't it. Silent again. Both CPUs' last
      samples are in page-fault / slab code. NAND had been idle for 22 s
      (the last ring step was a page program at 149.8 s; the SD log shows
      NAND irqs and reads flat after it). Tally from mtd0: two CPUs froze
      in 5 of 5 runs (98 s to 14 min); one CPU ran 2 h clean. Waiting for
      the kernel session's next test image. Logs in the shared notes
      (hang13_*).
      **Hang 14 (11-08 03:31): nandvs 1dd5f02c (both CPUs on the vendor
      kernel's PJ4B setup: ACTLR 41, aux func0 132, dbg0 60001100, dbg1
      927, dbg2 20008208), RAM-booted first, then from mtd0, froze at
      60 s,** the fastest yet. The CPU setup isn't it. The ring ends at the
      NAND read's ISR entry again (cpu0, which had gone idle waiting for
      the read). cpu1 was in folio_add_file_rmap_ptes (an atomic in
      fault-around). Tally from mtd0: two CPUs froze in 6 of 6; one CPU ran
      2 h clean. Logs in the shared notes (hang14_*).
      Correction from the kernel session: patch 0001 already ports the
      vendor PJ4B setup, so nandvs was in effect a rerun of nandtick. Every
      build ran the vendor's CPU register state.
      **Hang 15 (11-08 03:47): nandfa fd2eb360 (fault-around off, checked
      as 1 in both boots), from mtd0, froze at about 70 s.** Fault-around
      isn't it. The ring ends at the NAND read's ISR entry again (4 of 7
      two-CPU runs); cpu1 was in VMA / COW code. **Now running:** the
      same nandfa from mtd0 on the 4GB-SD card root, two CPUs, 2-hour soak
      (11-08 03:50). Marker renamed back to /.dp200-root; the card got the
      nandfa modules, its old set is in /var/backups/mods-card-06f000a0.tar
      on the card. Rename the marker to .dp200-root.off afterwards to go
      back to the NAND root.
      **Hang 16 (11-08 03:51): the card-root run froze too, at 106 s,** with
      NAND untouched since the boot reads (9.4 s; UBI detached, window
      closed). So the NAND root isn't required: two CPUs froze in 8 of 8
      runs on either root, and one CPU ran 2 h clean. cpu1's last samples
      were ehci_urb_enqueue / pcpu_alloc. The earlier clean card-root soaks
      were on 5b17e2ec / dc3b5f20, without the debug additions. The printer
      is left on the card root (marker .dp200-root) until the kernel
      session picks the next test. Logs in the shared notes (hang16_*).
      **nandwdt cf897cd8 (the plain image plus only the hang watchdog: no
      trace, sampler, tick check or ramoops), two CPUs, from mtd0 on the
      card root: the full 2-hour soak passed (11-08 04:05-06:13).** 12
      passes, no reset or errors, the console answered throughout, Wi-Fi
      up. So the debug additions raise the freeze rate a lot (nandfa froze
      at 106 s on the same setup). Owner's proposal: a no-Wi-Fi run
      (mwifiex blacklisted) on a fast-freezing build. The earlier clean
      runs used the older mwifiex_usb, which often failed to start Wi-Fi.
      Sent to the kernel session along with its add-back plan.
      **Hang 17 (11-08 06:23): the no-Wi-Fi test froze at about 329 s.**
      nandfa from mtd0, card root, two CPUs, camera on; the mwifiex .ko
      files were renamed, so nothing loaded (no mlan0). So Wi-Fi isn't
      needed. cpu0's last sample was in sdhci_request_done (the card's I/O
      completion; on the NAND root it was the NAND read ISR), cpu1's in a
      page-cache lookup. Tally: the debug builds froze in 9 of 9 runs on
      two CPUs; nandwdt (only the watchdog) and nandup (one CPU) ran 2 h
      clean. The Wi-Fi modules are renamed back. Without mlan0,
      init.mainline waits 45 s, so a start line sent before that is lost.
      Next: add the debug pieces back to nandwdt one at a time (ramoops
      first). Logs in the shared notes (hang17_*).
      **Hang 18 (11-08 06:36): nandram e2fb8c98 = nandwdt plus ramoops/pstore
      and the two no-map 1 MB areas at 0x1e000000, froze at about 175 s**
      on the card root with two CPUs, Wi-Fi and the camera on, the same
      setup where nandwdt ran 2 h clean. **So ramoops / the reserved areas
      bring the freeze back.** Every fast-freezing build since nanddbg has
      them. pstore shows nothing near the freeze. Next: split ramoops from
      the reserved areas (the kernel session's call). Logs in the shared
      notes (hang18_*).
      nandram also froze while idle in its reset boot, at about 7 min.
      **nandres 70bcc0cf (only the two no-map areas reserved, no pstore):
      2 h clean** in the same setup (11-08 06:54-09:01; 12 passes, the
      console answered throughout). So it's ramoops, not the hole. Next:
      nandrnc 4cdb1676 (ramoops without its run-time console writes).
      **Hang 19 (11-08 09:13): nandrnc 4cdb1676 (ramoops with console and
      pmsg sizes 0) froze at about 123 s** in the same setup, and probably
      once before after its RAM boot (that one wasn't captured). So ramoops'
      setup and mapping of 0x1e000000 alone bring the freeze back, without
      its run-time writes. Sent to the kernel session. Logs in the shared
      notes (hang19_*).
      **Hangs 20-22 (11-08 09:26-10:01): the ramoops mapping type isn't the
      trigger.** nandrso ecc0aa6e (strongly-ordered) froze at about
      20-50 s idle and again at about 6 min; nandrwb 6b077d2a (cacheable)
      froze at 210 s (and probably during its RAM boot). Left: ramoops /
      pstore setup itself (ECC init, old records, region claim, the pstore
      hooks). The reset boots of the ramoops builds also freeze while
      idle. Write mtd0 only from a stable kernel: a write from nandrso
      froze partway through kupdate, before the erase. The card gap now
      holds nandwdt. Logs in the shared notes (hang20_*, hang21_*,
      hang22_*).
      **Hang 23: nandrmv d9122842 (nandram with both areas moved to
      0x10000000) froze in its RAM boot,** idle, at about 26-50 s. So it
      isn't the 0x1e000000 range: what pstore/ramoops sets up is the
      trigger. (Not written to mtd0.) Logs in the shared notes (hang23_*).
      **Hang 24 (11-08 10:22): nandps0 ee5721ca (nandram's pstore config
      with no ramoops backend probed) froze at about 95 s** in its RAM-boot
      run. Compared with the clean nandres it adds only the PSTORE*,
      PSTORE_RAM and REED_SOLOMON options. With no backend, little of that
      code runs, so a kernel layout shift (about 10 KB) is a candidate:
      every fast-freezing build is a bigger one. Sent to the kernel session
      with a padding test idea. Logs in the shared notes (hang24_*).
      **nandpad 0863cdc0 (nandres plus zero padding that gives nandps0's
      exact layout, no pstore): 2 h clean** (11-08 10:42-12:50, RAM boot,
      card root, two CPUs; 12 passes, the console answered throughout). So
      the layout isn't it: pstore's own init is the trigger (compression,
      the fs registration, console/pmsg hooks, or the kmsg dumper). Next
      split is the kernel session's call.
      **nandpad2 ac97d361 (all of .text at nandps0's addresses, no pstore):
      2 h clean.** **nandps2 ea629fc5 (CONFIG_PSTORE alone, the pstore fs
      registered): about 89 min clean.** So registering the pstore fs
      isn't it, and the layout isn't it. What's left is the ramoops platform
      driver registration (nandps0 had it). From now on soaks for this
      quick-freeze phase are 45 min (owner, 11-08; deploy/usb/t/soak45.sh).
    - Wi-Fi power saving: init.mainline's `iw ... power_save off` never ran
      (iw not installed): power save was ON, with drops every ~100 s
      (reason 6). iw 6.9-1 (Debian trixie armel, sha256 12112fa6) installed
      on the dev printer by hand; with power save off: one drop (reason 34)
      at once, then none for 650 s, but 2.8 MB downloads went from 0.6 s
      to 15-18 s and pings lost 5-15%. Mixed; repeat once the hang is
      understood. iw belongs in the root build's package list either way.
    - **Errata kernel hard hang on the NAND root (11-07 ~11:55):** about
      25-30 min after the first NAND-root boot, idle (Klipper ready, Wi-Fi
      down), no ping, no serial echo, no panic. First thought to be the
      T5 test, but its commands never ran (rmmod/insmod "not found", no
      echo). The 82-min soak was on the card root; on the NAND root all
      file I/O goes through patch 0010 (PIO, busy-poll): back in the
      frame. Kernel session told; netconsole on for every run now.
    - **nandboot hard hang (plain image; errata image fixes it so far).** (1) 11-06 ~22:10,
      image 33d2e5d2: userspace, serial echo and Wi-Fi died, eth0 still
      pinged; after the 8782 re-enumerate, during Wi-Fi churn. (2) 11-07
      00:34, image fcba26da (watchdogs on, Wi-Fi as modules): at 1332 s
      uptime, ~30 s into a whole-root tar of the card (heavy SD read) with
      nc streams to the PC; everything died, no ping, no serial, no answer
      to BREAK+SysRq, and no soft-lockup panic: a whole-SoC lockup (bus
      stall?). The owner power-cycles in the morning; NAND was untouched
      (mtd6 detached, window none), so stock boots. Offline analysis + test
      plan handed to the kernel session (m1-debian under the same tar first;
      m1-debian was never put under that load on mainline).
      Night tests 11-07, each 3 passes of the whole-root tar (3.27 GB, ~4.3
      min each) with the nc streams and Wi-Fi up, all PASSED: A m1-debian
      5df089a9 (Nov 1 tree), B m1-debian-nandw f370f49e, E
      m1-nandboot-errata 5b17e2ec (e1ee7e8: the vendor PJ4B cache wrapper +
      erratum 6011). Then N, plain m1-nandboot fcba26da again: passes 1-2
      done, **hung in pass 3** (668 s uptime, ~570 s into the load; no
      ping, serial or SysRq). So plain nandboot hung in 2 of 2 load runs
      (~30 s and ~570 s), the errata image 0 of 1, m1-debian 0 of 2 (each
      ~13 min of load). Day run E2 (11-07): the errata image, 20 passes
      (~82 min of load, 65 GB), no hang and a clean dmesg. So the errata
      image has ~97 min of this load without a hang, plain nandboot hung
      within ~10 min both times: the missing PJ4B errata workarounds are
      the likely cause. The errata patches are the nandboot default now
      (variants/nandboot.config) and the errata image is in mtd0 (stage
      4, 11-07). Open: another thorough soak later (owner), e.g. with
      Wi-Fi traffic; the debug image (hardware watchdog) only if it ever
      hangs; recovery if it does: boot another kernel from the card via
      U-Boot (tools/sd_raw_boot.sh); docs/kernel/nandboot_hang_analysis.md.
    - stage 3 normal path tested 2026-11-07 (end_goal_install_plan.md):
      root from the marked card, mtd-utils run read-only; Wi-Fi fixed in
      init.mainline. Open for the initramfs: keep its log (copy to a
      place init.mainline's /run doesn't cover), close the mtd6 window
      when the root isn't mtd6, the MAC from mtd1 (below), maybe refuse a
      root without init.mainline; then the stick and broken-root paths
      (owner at the printer).
    - open:
      the screen app's "Back to stock" button (writes /.dp200-revert);
      Ethernet MAC from mtd1 (the stock line's ethaddr is ignored now).

## Done (2026-11-02, this round)

- XYZ cube on the work printer: 19.9-20.1 mm; Z offset by paper test.
- Homing at stock speeds: X/Y 208 mm/s seek + 10 mm/s (0.000 mm spread),
  Z stays 5 mm/s (10 stalls lifting); stock values decoded from the FM
  microcode (docs/homing_speed_plan.md).
- Stick backups store the firmware version; a mismatch offers a new backup
  and keeps the old one (docs/usb_installer.md).
- WiFi -> SAVED page (order and forget); power saving off.
- OBJECTS page (exclude_object) on the print screen.
- BED LEVEL page shows screw turns and directions.
- NAND datasheet read: 100K P/E cycles, >= 4016 valid blocks
  (docs/internal_firmware_plan.md).
- Cura cut-outs confirmed at the back corners (slicer README).
- Probe offset method, lever zone, clock settle: in hardware_notes.
- Mainsail stays (no benefit found in Fluidd).
- Mainsail history: the cancelled bedask_test job removed.
- Prebuilt (zig) images 10-27 run on the printer: both cores load, Klipper
  ready, clocks 395.90/395.98 MHz, temperatures and endstops read; the gcc
  builds put back (fork src unchanged since).
- Stick updated: payload build 4d3bcdf (md5 5af91c1e...) + the installer with
  firmware-tagged backups (dry-run tested); not ejected.
- Work printer upgraded to the latest build; the subsequent test print
  failed. Logs are expected after the token reset for diagnosis.
- HOME ALL button verified working; the homing sequence still needs a
  clearance review before X homing (see open item 6).
