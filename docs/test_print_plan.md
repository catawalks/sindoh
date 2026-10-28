# First test print: action items

Work through these **one at a time, in order**. Each item says who does what
and what "done" looks like. Items with heat or motion only happen with the
user at the printer.

Prepared 2026-10-22 (unattended, no heat, no motion):
- `[exclude_object]`, `[gcode_arcs]` and a `PRIME_LINE` macro in
  `dp200_printer.cfg`.
- `PRINT_START` now pushes back the 15 mm that `CLEAN_NOZZLE` retracts,
  wipes, and ends over the bed centre at Z 10. It used to end at Y 5.5, over
  the front grip handle.
- Deployed to the printer; Klipper restarted and is ready.
- Two test files on the printer (Mainsail → G-code files), made by
  `tools/gen_test_prints.py` (PLA 210 °C / bed 60 °C, centred, inside the
  mesh area):
  - `dp200_first_layer.gcode`: one 0.25 mm layer, 50×50 mm, ~0.24 m
    filament;
  - `dp200_box_20mm.gcode`: 20×20×10 mm open box, 2 walls, ~0.35 m.
- A PrusaSlicer profile: `install/slicer/DP200_Klipper_PrusaSlicer.ini`.

## Status 2026-10-27

- Steps 1, 2, 4, 5, 6 done; 3 (thermocouple) skipped. Clutch stays off while
  extruding (plastic came out with it off).
- Step 5: PROBE_ACCURACY range 0.019 mm (std dev 0.005); 4x4 mesh spread
  0.34 mm. G28 failed after parking at the purge bin: fixed (homing backs X off
  the switch first).
- Step 6: first layer good after -0.05 mm; z_offset saved as 2.58.
- Step 7: the first box leaned ~1 mm right/back over 10 mm. Cause: X/Y lost
  ~0.2 step per direction change (step-engine CTRL rewritten mid-pulse); fixed
  in the FM firmware, drift test 0.000 mm after. Reprint running.
- Found while watching the mesh: the probe's X offset looks ~6-8 mm larger than
  configured (see HANDOFF open items).

## 1. Filament choice (user, 2 min)

Use **PLA, 1.75 mm**, ideally fresh or dried (the old spool snapped on
2026-10-18). Open filament through the inlet; the cartridge chip doesn't
matter for this. The test values assume PLA at 210 °C nozzle, 60 °C bed.

## 2. Clutch check, cold (user present, motion: extruder only, no heat)

**Unknown that can stop a print:** the stock firmware turns the clutch
(pwm6) on only for load and unload. During a print it's off. We have never
moved filament with the extruder while the clutch is off.

1. Push the filament into the inlet until the feeder gears grab it, and put
   a mark on it at the inlet.
2. With the clutch **off**, feed 20 mm cold:
   `FORCE_MOVE STEPPER=extruder DISTANCE=20 VELOCITY=5`. Does the mark move
   20 mm?
3. Repeat with `SET_PIN PIN=clutch VALUE=1` first, then `VALUE=0` after.

Possible outcomes:
- **Moves with the clutch off:** fine, printing works as configured.
- **Moves only with the clutch on:** add `SET_PIN PIN=clutch VALUE=1` to
  `PRINT_START`, and `VALUE=0` to `PRINT_END` and `CANCEL_PRINT`. Check that
  the clutch can stay on for an hour (does the solenoid or coil get hot?).

## 3. Nozzle thermocouple check (user present, heat)

The bed table was 5–15 °C off; the nozzle table comes from the same stock
firmware. Overnight at room temperature (2026-10-22) the nozzle read
**26.3 °C** while the TC-calibrated bed read **19.0 °C**, so the nozzle
probably reads ~7 °C high too.

1. Fix the K thermocouple bead against the nozzle tip or heater block with
   kapton (as close to the melt zone as possible).
2. Soak at `M104 S150`, `S190`, `S220` (3 min each after reaching target).
   Note Klipper's reading and the TC each time, plus one cold pair.
3. Run:
   `python tools/rescale_sensor.py klipper/config/dp200_printer.cfg dp200_nozzle 26.3:19 <k>:<tc> ...`
   It prints the new `[adc_temperature dp200_nozzle]` section. Replace the
   section, deploy, restart.
4. Re-run `PID_CALIBRATE HEATER=extruder TARGET=210` and `SAVE_CONFIG` (the
   gains shift a little with the new scale).

Keep `max_power: 0.6` for now. It reached 210 °C in ~130 s, fast enough.

## 4. Load filament (user present, heat + motion)

`LOAD_FILAMENT TEMP=210`, or the screen: FILAMENT → LOAD. It homes, heats
over the purge bin, feeds the measured 518 mm path, purges and wipes. Done
when clean plastic comes out of the nozzle. Empty the purge bin first
(`BIN_EMPTIED`).

## 5. Bed, probe and Z check (user present, motion)

1. Bed clean and empty; remove anything near the front grip handle.
2. `G28`, then `PROBE_ACCURACY` at the bed centre (`G1 X100 Y100 Z10`
   first). Range should be < 0.02 mm.
3. `BED_MESH_CALIBRATE PROBE_COUNT=4,4`. It must say "Mesh reference check
   OK" (the stability guard). Look at the mesh in Mainsail (Heightmap);
   a range over ~1 mm means something is wrong.
4. Optional: re-check the nozzle zero with `LV_PROBE_CALIBRATE`, paper test,
   `ACCEPT`, `LV_PROBE_CALIBRATE_SAVE Z=...`, then `SAVE_CONFIG`. The
   current z_offset is 2.530 from 2026-10-19.
5. Check that the probe offsets in printer.cfg (x 15, y -30) are right: put
   the nozzle on a mark, then move by the offsets and see if the pin is over
   the same mark. The mesh is placed using these.

## 6. First layer test (user present, print)

Print `dp200_first_layer.gcode`. `PRINT_START` does:
- heat the bed and warm the nozzle to 150 °C;
- home;
- mesh 4×4;
- purge and wipe at the bin;
- heat the nozzle to 210 °C;
- prime, then move to the bed centre.

The file then draws a prime line at Y 67 and the 50 mm square. Watch the
prime line and the first perimeter:
- **too high** (round strands, not sticking): `SET_GCODE_OFFSET Z_ADJUST=-0.05`
  (Mainsail Z-offset buttons), repeat;
- **too low** (transparent, scraping, no flow): `Z_ADJUST=+0.05`.

Done when the square is a single smooth sheet. Save the offset:
`Z_OFFSET_APPLY_PROBE`, then `SAVE_CONFIG`.

Stop at any time with CANCEL (Mainsail), or hold STOP on the touchscreen for
1 s.

## 7. 20 mm box (user present, print)

Print `dp200_box_20mm.gcode`. It checks layer adhesion, retraction (4 mm on
the long bowden) and the part-cooling fan from layer 3. Watch for:
- under-extrusion after travels (retraction not fully undone);
- stringing (more retraction);
- skipped layers or a shifted box (step engine limits: the moves are slow,
  so this shouldn't happen).

## 8. After the first good print (later, one at a time)

- Pressure advance for the long bowden: `TUNING_TOWER` with
  `SET_PRESSURE_ADVANCE` (start 0.3–0.8).
- Retraction tuning (4 mm is a guess; bowden ~435 mm long).
- Flow / extrusion multiplier with a single-wall cube.
- Slice your own models with the PrusaSlicer profile. Its start G-code is
  `PRINT_START BED=... EXTRUDER=...` then `PRIME_LINE`.
- Filament runout: the encoder sensor pauses the print after 50 mm without
  motion. Test by cutting the filament at the inlet during a print.
- Bed above 80 °C (ABS) is extrapolated from the thermocouple fit: check
  with the TC before relying on it.
