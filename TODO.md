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
1c. **Ethernet doesn't recover after a switch outage (work printer,
   2026-11-06):** the switch lost power/its uplink overnight; after it came
   back other devices got IPs, the printer only after a reboot. Check
   dp200-netd.sh: link down/up handling and DHCP retry (udhcpc restart on
   carrier up, lease renewal when the DHCP server was gone).
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
    Check stability on the upgraded work printer too.
13. **Wi-Fi summary page accuracy:** SYSTEM -> NETWORK -> WIFI can show
    inaccurate data; the owner saw the Ethernet IP displayed on the WIFI
    summary page on the test printer. Trace the page's data source and state
    updates, then clean it up to display Wi-Fi information only and avoid
    presenting stale or Ethernet values as Wi-Fi details.
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
      scenarios + the tool list. Open: the hardware test (hold on the
      real panel, the popup), and a "Back to stock" button. Wi-Fi: build mwifiex_usb
      as a module, loaded by init.mainline (owner prefers this over the
      re-enumerate, which may be tied to the 11-07 hang).
    - **nandboot hang (2026-11-07, once):** userspace, serial echo and
      Wi-Fi stopped, Ethernet still answered ping; power cycle. No kernel
      message (no lockup detectors/netconsole in the image). Not seen again
      in ~40 min of watched boots. Add SOFTLOCKUP/HUNG_TASK/WQ_WATCHDOG to
      the image.
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
