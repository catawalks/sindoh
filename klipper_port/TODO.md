# DP200 Klipper port - active task list

Updated 2026-10-28. Ordered roughly by what's next. "(user)" = needs
the user at the printer (heat, motion, measurements, decisions).
Larger, self-contained projects (kernel, SD boot, NAND install, camera
check, faster stepping, other models) are in [PROJECTS.md](PROJECTS.md),
written so they can be handed to another agent.

## Next session

1. **XYZ cube results (user):** measured 10-28: X 20.1, Y 20.0, Z 20.2 mm
   (target 20.0). Within normal print/caliper tolerance: no
   rotation_distance change. X +0.1 is typical wall bulge; Z +0.2 is more
   likely a constant first-layer offset (z_offset/babystep) than a scale
   error (a 1 % Z scale error would need a 40+ mm print to confirm).
   Diagonals of the top 27.8/27.9 (skew ~0.2 deg, no correction). Photos:
   side walls very clean (even layers, no ringing or banding visible),
   corners sharp, no stringing (but nothing on the cube tests it). Faults:
   small blobs where the X and Y cut-outs meet in a point (tiny islands
   start there; no pressure advance configured yet), top face rough with
   scuff marks, a dragged scar and a blob at one corner (profile has
   retract_lift = 0, so the nozzle travels over finished top layers).
   DONE 10-28: z-hop 0.2 in all three slicer profiles; PA tower
   (make_pa_tower.py): best corners ~15 mm, walls thin/split from 35-40 mm
   -> pressure_advance 0.30 in dp200_printer.cfg (live, verified). The
   tower changed little below 35 mm, so recheck with dry filament.
   Dryer done; cube reprinted 10-28 (z-hop + PA, user to measure... the
   cube was then crushed: see the Z-homing incident below). Next: reprint
   the cube, then a retraction test with two towers.
1b. **Z-homing incident 10-28:** bed_pose_sweep.sh homed with the cube on
   the bed (PRINT_END's M84 had dropped homing); Z homes UPWARD, so the
   cube was crushed against the top until the user's emergency stop. User
   found no damage. Fix: every Z homing now needs BED_CLEAR (homing_override
   -> Mainsail prompt + screen YES/NO dialog, valid 5 min, one homing);
   tested live (G28 refused, nothing moved; dialog on the panel). Cold 4x4
   mesh after: front-left 0.23 mm lower and back-right 0.15 mm higher than
   the 60 C mesh before the cube print (same grid). Confirmed at 60 C:
   -0.23/+0.02 front, -0.05/+0.13 back (L/R). Lead screws are back-left
   and back-right, belt-coupled: the left side is ~0.2 mm lower front and
   back = the belt likely skipped on the left pulley. FIXED 10-28: lead =
   1 mm per screw turn (2 mm bed = 2 turns; bed down = CCW from above);
   user loosened the belt and turned the left screw 1/5 turn CW. Mesh
   after (cold): left-right within +0.05/-0.02 mm on every row (before
   the crush: up to -0.13), range 0.23 mm, mostly front-to-back (front
   screws). Check the first layer on the next print.
   Spring-loaded part hanging under the bed: watched all XENA inputs,
   dec_sensor and GPIO banks 0-7 (regwatch, bit-level noise filter) while
   the user pressed it - no input changed. Mechanical, or not wired to
   anything we read.
2. **Filament dryer.** DONE 10-28, first run (screen FILAMENT -> DRYER,
   PLA 4 h, 15:55-19:59): bed down + forward, head parked, extruder off;
   bed 22 -> 50 C in 8 min, then 50.0 C for the whole 4 h at 18-46 %
   power; idle timeout 15300 s during, 600 s after; vent 0.6 for 1 min at
   15 min; halfway message at 17:57; "Drying finished" + bed off at 19:59.
   Not tested yet: STOP DRYING, PRINT_START cancelling drying, FORCE=1
   above the 70 C sheet limit.
3. **Beeper (user):** dec_pwm block 10. Add `[output_pin beeper]
   pin: io:pwm10`, test a short beep, find a sensible PWM value. The dryer
   (_DRY_SIGNAL) uses it automatically once it exists. Then M300 for
   slicers / end-of-print beep.
4. DONE 10-27: "Timer too close" after a restart - UPC_WAIT_CLOCK
   (upc_clockcheck) waits until the MCU clock estimates are within 0.3 %;
   the homing override calls it first. Tested: 1.2 % off at ready, settled
   after 19 s. (A plain RESTART doesn't reload changed extras: use
   rc.dp200 restart-klipper.)
5. DONE 10-27: config dir chowned to klipper:klipper (Moonraker could not
   write root-owned files). Keep copying with `cat >` or chown after.

## Input shaping (sensor ordered: HOCENWAY ADXL345 USB)

6. When it arrives: plug into a PC first, read VID:PID (Device Manager ->
   Hardware Ids) and the chip (RP2040 = good; CH340 = won't work here).
   Pins for dp200_adxl.cfg from the seller's docs.
7. Test the generic usb-serial binding (/dev/ttyUSB0), SENSOR ON, TEST X/Y,
   SAVE. If the binding fails: cdc-acm.ko is built and verified offline
   (install/kernel_modules/README.md has the insmod test plan).
8. Mounts (user measurements): head clip (head width, side notch position /
   size) and bed clamp (plate thickness at the front edge, space under it);
   board hole spacing. Then finalise the OpenSCAD files and print them.
9. Rebuild the USB payload once a real sensor works.

## Screen app

10. **BED LEVEL page** (mockup done): probe, draw the mesh, per-screw hints
    for the 2 front screws (fixed back support), learn the thread pitch
    with one full turn + re-probe, confirm which way "raise" is. The probe
    offset is fixed now, so this is unblocked.
11. Exclude-object (cancel one object) from the screen during a print.
12. Screen app crash (once, 10-27): it now restarts itself and logs to
    /var/log/dp200_screen.log - look there if the screen freezes again.

## Camera, NAND install -> PROJECTS.md

13. Object-on-bed check: PROJECTS.md #4. Spaghetti detection: #7.
15. NAND size and install: PROJECTS.md #3.
17. Test the zig-built prebuilt images on the printer (only emulator-checked).

## Smaller items

18. Cura: verify the back-corner disallowed areas show at the back.
19. Mesh Y minimum: the front grip handle's depth (user) - maybe lower
    mesh_min Y from 30.
20. Slicer profiles: update speeds/retraction after the cube; PA value.
21. hardware_notes / README: document tonight's results (probe offset scan
    method, lever zone, clock-settle issue).

## Later

22. Other models, cartridge writing, kernel, SD boot, faster stepping:
    PROJECTS.md.
