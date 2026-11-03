# DP200 Klipper port - active task list

Rewritten 2026-11-02 from TODO.md (10-28), PROJECTS.md, the docs and the
session notes. "(user)" = needs the owner at a printer (heat, motion,
measurements). Larger, self-contained projects are in
[PROJECTS.md](PROJECTS.md). Finished items are at the end.
**Keep it current:** edit this file (and PROJECTS.md) in the same commit as
the work; it is how open items survive between sessions.

## Next (user at a printer)

1. **Work printer upgrade (user):** the stick's `_update_rodin_KlipperInstall`
   (rename to `_update_rodin`). First install of this build: also checks the
   Wi-Fi power-save fix, 208 mm/s X/Y homing and the firmware-tagged backup
   (its backup folder predates FIRMWARE files, so it gets tagged).
2. **Screen features not yet used on hardware (user):** the calibration
   wizards (Z HEIGHT paper test, PROBE OFFSET, PID TUNE, SAVE Z OFFSET), the
   HOME button, LOAD switching the heater off, OBJECTS (skip one object in a
   print with two or more), WiFi -> SAVED (PREFER / FORGET).
3. **PRINT_START pause-and-ask, YES (user):** a real print answered YES on
   the screen (NO was tested: nothing moved, the print was cancelled).
4. **A real Mainsail update** from SYSTEM -> UPDATE (only CHECK NOW tried).
5. **Dryer leftovers (user):** STOP DRYING, PRINT_START during drying,
   FORCE=1 above the 70 C sheet limit.

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

11. **Updates and NAND space, options A/B/C** (PROJECTS.md #10): Klipper
    and Moonraker from upstream through Moonraker without image publishing.

## Agent (no user needed)

12. **Wi-Fi drops:** watching the test printer's log. 68 deauths total,
    none since power saving went off (checked 2026-11-03 ~01:50 and again
    ~02:40). Check again after a day; then the work printer.
13. **Faster stepping** (docs/faster_stepping_plan.md, phases 1-3 approved
    11-02): done so far: engine register map (COM_STP +0x78 candidate),
    `CONFIG_UPC_STEP_SINGLE` (fork branch fast-stepping, default off) halves
    step interrupts, emulator-identical; engine run 11-03 (driver off):
    +0x78 = 24-bit edge down-counter, engine clock 197.9 MHz. Phase 2b/3b
    done: `CONFIG_UPC_STEP_BATCH` (constant blocks as engine moves, default
    off) passes the kemu engine model (25 steps: 1 engine start instead of
    25, steps 40 ticks after schedule instead of 840). Next: phase 4 at the
    printer (user): SINGLE, then BATCH - homing, drift test, probing, cube.
14. **Prebuilt (zig) UPC images, motion:** loaded and run 2026-11-02 (see
    Done); still untested with motion (homing/moves need the owner). They
    are the fallback; the printer runs the gcc builds from /opt/dp200.

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
