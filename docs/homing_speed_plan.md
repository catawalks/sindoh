# Homing closer to stock speed (draft, 2026-11-02)

The owner, after going back to stock firmware for a while: stock homes much
faster than our config. What we have, and what limits it:

| Axis | Now | Steps/mm | Notes |
|---|---|---|---|
| X | homing_speed 10, second 5 mm/s | 80 | 10 mm/s is stock's *slow* final approach (10.4 mm/s, measured: hardware_notes 2026-10-18); stock must seek faster first |
| Y | homing_speed 10, second 5 mm/s | 80 | same |
| Z | homing_speed 5, second 2 mm/s; max_z_velocity 5 | 3200 | up to ~194 mm of travel: ~40 s from the bottom |

Limits found earlier (hardware_notes):
- X/Y: 50 mm/s is 4000 steps/s, far below what the UPC engines step
  cleanly (32k steps/s tested on Z). max_velocity is 150.
- Z: the 2026-10-19 retest stepped Z cleanly at 6/8/10 mm/s (up to 32k
  steps/s, busy_hits 0). max_z_velocity stayed at 5 because the 10-18 run
  lost steps at 8-10 mm/s, which pointed to a mechanical cause (Z motor
  coupler or leadscrew grub screw slipping). The owner (2026-11-02): not
  seen again since that first test, so taken as a one-off; no coupler
  check needed before this test.

## Proposed values (to test at the printer, bed EMPTY)

```
[stepper_x]
homing_speed: 50            # fast seek
second_homing_speed: 10     # stock's fine approach (10.4)
homing_retract_dist: 5

[stepper_y]
homing_speed: 50
second_homing_speed: 10
homing_retract_dist: 5

[stepper_z]
homing_speed: 10            # 32k steps/s: clean in the 10-19 retest
second_homing_speed: 2      # repeatability of Z zero matters most
homing_retract_dist: 2

[printer]
max_z_velocity: 10          # bed moves (LOWER BED, park) too
```

## Test (owner present)

1. X/Y: home 10 times (`G28 X`, `G28 Y`), then the drift test
   (scratchpad drift_test.py / UPC_STEP_STATS): the trigger position must
   repeat to the step, busy_hits 0.
2. Z: with BED_CLEAR, home from the bottom 5 times; LV probe reference at
   one point before and after (as in the 10-19 retest): <= 0.01 mm shift.
3. Time each against stock if possible (owner's stopwatch / video).
4. Commit the values to dp200_printer.cfg (port-owned) if all pass.
