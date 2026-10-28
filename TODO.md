# DP200 Klipper port - active task list

Updated 2026-10-27, late. Ordered roughly by what's next. "(user)" = needs
the user at the printer (heat, motion, measurements, decisions).
Larger, self-contained projects (kernel, SD boot, NAND install, camera
check, faster stepping, other models) are in [PROJECTS.md](PROJECTS.md),
written so they can be handed to another agent.

## Next session

1. **XYZ cube results (user):** measure X/Y/Z (target 20.0 mm), check
   squareness, corners, letters, stringing (filament is damp). Tune from
   there: retraction, pressure advance, flow.
2. **Filament dryer: first run (user, heat + motion).** Code is on the
   printer (FILAMENT_DRY / FILAMENT_DRY_STOP, screen FILAMENT -> DRYER).
   Check: bed lowers + comes forward with the head parked off the bed, bed
   holds temperature for hours (idle timeout raised), exhaust fan vents for
   1 min every 15 min, flip reminder at halfway, lamp flashes at the end,
   STOP DRYING, PRINT_START cancels drying. Sheet limit 70 C (test printer);
   higher presets warn and need FORCE=1.
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
   SAVE. If the binding fails: build cdc-acm.ko for kernel 3.2.
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
