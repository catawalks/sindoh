# Progress checkpoint (2026-10-18 morning)

Printer state: UPC cores HELD, all outputs off (since 2026-10-17 night).
Stock app killed for this boot; no NAND changes. COM3 serial; printer WiFi 10.10.0.21.
/mnt/sd/dp200/ holds upctool, probe_*.bin and the CURRENT klipper_fm.bin /
klipper_io.bin (with PWM config bits + dsens pins). Filament is still loaded.

## Done overnight (desk work, no printer motion)
- Stock routines decoded: unload, load, nozzle clean/purge bin, LV sensor
  toggle/probe -> docs/stock_routines.md.
- karas.db: row NO=4 is the live row; parameter blocks mapped to DTCM.
- Engine clock = 198.01 MHz; engine +0x64 bit8 busy, +0x88 bit8 done.
- CORRECTION: X endstop is 1 = triggered (`xena42`), like Y and Z. The carriage was
  parked on the switch during the hand test.
- Extruder DIR 1 = retract -> `dir_pin: !smot_dir3`.
- Filament sensor xena46 (0 = present); LV sensor = dec_sensor +0x210 bit 8 (`dsens8`).
- Port: PWM blocks get their stock ctrl config bits; new dsens0..31 input pins.
  Builds: FM 15904 B, IO 15920 B; FM emulation regression passes.
- New klipper/config/dp200_macros.cfg: CLEAN_NOZZLE, UNLOAD_FILAMENT,
  LOAD_FILAMENT (+_FINISH), BIN_EMPTIED, LV_TOGGLE, clutch/solenoid pins,
  filament sensor, probe (commented). 14 templates compile; 29 pins valid.
- printer_dp200.cfg: includes macros; X max 233.6, Z max 195, Y current 0.60.

## Next (needs the user at the printer)
1. DONE 10-18: new firmware loaded; sensors read as expected; X homing works.
   (was: Load the new firmware (`upctool load klipper_io.bin klipper_fm.bin` + bridge).
   Verify the X endstop reads 1 when parked/triggered, filament sensor (xena46)
   reads 0 with filament loaded, and dsens8 state.
2. DONE: slow X homing (tools/ktest_home.py X).
3. ATTEMPTED 10-18 (tools/ktest_unload.py): heating OK (27->210 C in 130 s at 60 % cap),
   but after 430 mm of E 'retract' (DIR 1, clutch pwm6 on) xena46 still read 0 (present).
   RESULT: filament DID retract (DIR 1 + clutch OK) but old brittle filament snapped in the
   feed tube; broken piece left at the sensor. User clears the tube by hand. Retest with fresh filament.
   (was: Unload test: real klippy needed for macros -> OR scripted equivalent via the
   khost client (heat to 230, clutch on, retract in chunks while watching xena46).
3b. DONE 10-18 (afternoon): the tube was cleared by hand. tools/kwatch.py (watches all
   96 inputs) showed that **xena46 is the cartridge-detect lever** (1 = lever down/no cartridge),
   not a filament sensor; it was taped up, hence the constant "present". tools/ktest_feed.py:
   cold feed with the tube off: inlet -> gear-train exit ~100 mm; 100 mm extra stuck out
   (E steps/mm OK); 200 mm retract OK.
3c. DONE 10-18: full load with the tube reattached. Cold 400 mm, then heated (tools/ktest_load.py,
   210 C) 80 + 35-40 mm until first plastic: **inlet -> nozzle ~518 mm**. The filament is now LOADED
   (PLA assumed). dp200_macros.cfg LOAD/UNLOAD rewritten for open filament with fixed measured
   lengths (load over the bin + wipe, as the user asked); lever = info only.
4. DONE 10-18: filament encoder = **dsens7** (+0x210 bit 7), ~16.5 mm/pulse -> filament_motion_sensor.
   FM build now has CONFIG_WANT_BUTTONS (15432 B, emulator regression OK). LOADED on the printer
   10-18 (/mnt/sd/dp200/klipper_fm.bin md5 80fbe712...; old image kept as klipper_fm_nobtn.bin);
   buttons verified with tools/kbuttons.py.
4c. DONE 10-18 (unattended, user approved): probe Z test, tools/ktest_probe.py. Trigger Z 4.385 (Z switch 3.1),
   repeat 0.0006 mm, pin stays deployed between touches, no noise. Left: paper test (user) for
   z_offset/position_endstop; X/Y offset by bed edge: jog the nozzle to the bed's left/front edge (user
   eyeballs), then probe-step across the same edge in 0.5 mm steps; offset = probe edge - nozzle edge.
   PAPER TEST (needs the user; head already at X110/Y100): run
   `ktest_zgo.py KL IP <Z>` for Z = 3.1, 2.0, 1.0, 0.5, then 0.1 steps while the user slides paper.
   First drag = nozzle zero Z0. Then position_endstop_new = 3.1 - Z0, and probe z_offset = 4.385 - Z0
   (both in the current coordinates). Pick old plastic off the nozzle tip first.
5. DONE 10-18 (evening): Debian rootfs built ON THE PRINTER (install/build_rootfs_native.sh). Took
   ~2.5 h incl. failures: armhf impossible (no CONFIG_ARM_THUMB) -> trixie armel; 2013 clock; stock
   /dev 0660 nodes -> own chroot /dev; build stole the serial tty -> setsid; OOM (no swap support,
   appBrowser 98 MB) -> killed appBrowser + SKIP_CYTHON. gcc UPC images 11580/11764 B.
   DONE: gcc firmware verified read-only (khost.py); stack started by hand -> klippy READY,
   Moonraker OK, Mainsail on http://10.10.0.21/. Hook not installed yet (stock on reboot).
6. 10-18 evening/night: bed mesh via wrapped probe commands works (+ reference-probe guard); a
   transient 1.1-1.5 mm probe offset was seen but not reproduced. Step-engine limit ~20k steps/s
   found and capped. NAND runtime measured (fits mtd5). Step diagnostics firmware built, not deployed.
   USB installer scripts written + .she packing verified (docs/usb_installer.md).
7. 10-20 (unattended, no motion/heat): webcam (ustreamer MJPEG + time32 shim with frame repair),
   lamp macros, touch-panel study + framebuffer status PoC (docs/touchscreen_options.md).
9. 10-21: bed sensor calibrated to the surface + bed/nozzle PID, filament unloaded, cartridge chip
   (DS28E22 via DS2465) identified and dumped, boot ROM console speed found (~120000 baud).
8. 10-20 evening: touch UI service, MCU-warning fix, NAND installer + dry run, Klipper fork patches,
   kernel and SD-boot research, owner install guide (see HANDOFF "10-20 EVENING").
4b. DONE 10-18: Y homing (110.95 mm to the switch; repeat 9.96/9.99 mm after a 10 mm back-off).
5. Debian rootfs build (needs a Linux PC or WSL) -> real klippy + Moonraker + Mainsail.
