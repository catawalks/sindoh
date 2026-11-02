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

## Result (2026-11-02, Stanley test printer, bed empty, owner present)

- **X/Y at 50/10 mm/s: pass.** 10 homes each; the slow-creep trigger point
  moved 0.02 mm (one 0.02 mm search step: X 216.02 -> 216.00, Y 5.50 ->
  5.52). G28 X from X20: 5.7 s, G28 Y from Y200: 5.4 s.
- **Z at 10 mm/s: fail.** Lowering the bed at 10 mm/s worked, but lifting
  it stalled twice from Z150: "No trigger on stepper_z after full movement",
  and on the retest a loud buzz about halfway up (owner stopped it). A short
  climb from near the top worked. Lifting needs more torque than the
  10-19 retest (downward) showed, which also explains the 10-18 losses.
  Z stays at homing_speed 5 / max_z_velocity 5 (G28 Z from halfway: 31 s).
- Possible later: 6-7 mm/s lift test, or more Z current (driver/motor limits
  unknown).

## Stock homing speeds (decoded 2026-11-02)

The FM microcode is the `fm_ucode_data_P` array (16192 bytes) in the main
program (`upc_driver_init` loads it to /dev/upc1). Extracted locally
(RE_analysis/stock_fm.bin, Marvell code: never published) and run in
`tools/fmseq.py` with the karas.db parameter blocks. Each axis homes with a
"long jump" (fast, ramped, toward the switch until it triggers), then a
"find home" (back off until the switch releases):

| Axis | Long jump (seek) | Find home (back-off) |
|---|---|---|
| X (cmd 0x23 / 0x24) | **208 mm/s** (16.7k steps/s), ramped (~4500 mm/s²) | 10.4 mm/s, at most 22.6 mm |
| Y (cmd 0x21 / 0x22) | **208 mm/s**, ramped | 10.4 mm/s, at most 12.3 mm |
| Z (cmd 0x1f / 0x20) | **5.05 mm/s** (16.2k steps/s), ramped from 0.5 over ~0.3 mm | **0.39 mm/s** (1250 steps/s), at most 1.26 mm, then Z = 9920 steps (3.1 mm) |

Z back-off: the code writes period 400 and **engine +0x50 = 200** (X/Y/E
moves write 1; the probe's single Z steps, cmd 0x2a, also write 200). +0x50
is read as a clock divider: the main program adds the probe's move count 1:1
to the Z step position (StepperFindLVSC311), so it is no repeat count, and
400 ticks alone would be 78 mm/s. Inferred, not measured. (The 3DWOX
stepper-mod-b0.ko register names did not help: a different register layout.)

So stock Z homing is the same 5 mm/s as ours: the 10 mm/s stall is
consistent with stock never going faster. Stock X/Y seek much faster than
our 50 mm/s (our max_velocity is 150); a 100 mm/s seek test is possible.
