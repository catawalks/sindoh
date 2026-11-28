# Sindoh 2X: the two heads' stock routines

**Source:** the motion program of the owner's 2X (`PRIME_210419_2`,
`marvell_lspsdk_3dp_granite2-debug_stripped.elf`), disassembled on the
PC on 2026-11-28, and its settings database (`karas.db`, row NO=4).
Each routine was outlined with sindoh-klipper
`tools/sindoh_engine_trace.py` (calls with their constant arguments,
and the database value behind each variable). **Nothing here was
watched on the 2X.** Where the same routine was recorded move by move
on the 1X ([1x_stock_routines.md](1x_stock_routines.md)), the 1X's
numbers come out of this reading exactly; those lines are marked
"(= 1X recording)". "(our reading)" marks inferences. The machine:
[2x.md](2x.md).

## Frame and names

- Stock X is 0 at the bed's left edge and grows to the right, 80
  steps per mm. Y is 80.4 steps per mm (0 = bed at the back), Z 2560
  steps per mm (the bed, down as Z grows), the extruders 458.8.
- **Head 1** is the right one: carriage "X1", nozzle index 0 in the
  program, `T0`. **Head 2** is the left one: carriage "X2", nozzle
  index 1, `T1`; it is the 1X's only head.
- The program keeps per-nozzle positions in arrays. For head 1 they
  come from the database; **for head 2 they are constants in the
  program** (the database has no column for them).

## Limits and homing

| | Head 1 (X1, right) | Head 2 (X2, left) |
|---|---|---|
| Travel | -3.10 to 262.70 mm | -38.20 to 232.50 mm |
| Home position | **262.70** (21016 steps), at the right wall | -38.20 (-3056), at the left wall |
| Home sensor edge | **243.35** (19468) | -17.85 (-1428) |
| Move off the sensor first, if it is on | 35.00 mm to the left | 35.00 mm to the right |
| From the edge to home | 19.35 mm right (1548 steps) + `HomeXOffset` | 20.35 mm left (1628) + `HomeXOffset` |
| Enable bit in the core's motor command | 1 | 256 |

- `engine_initGoX1` is `engine_initGoX2` mirrored: move off the
  sensor if on it (still on afterwards: error 501); a fast run toward
  home until the sensor trips; the slow search for the edge, where
  the position is set to the edge value above (error 504 if that
  fails); the last move to home. Speeds are the same commands for
  both heads (1X recording: fast about 102 mm/s, search 10.2 mm/s).
- **Both heads** (`engine_initGoX1X2`): it reads both home sensors
  first. Both on or both off: X1, then X2. Only X1's on: X2 first,
  then X1. Only X2's on: X1 first, then X2. A failure of the first
  stops the second.
- A full home is `engine_initCombinedZYX`; the load routine homes in
  the order Y, Z, then both X.
- The home sensor of X1 has its own board connector ("X-HOME",
  "X2-HOME"); its GPIO line is not found yet.

## Where each head waits and works

All in mm, stock frame (steps in brackets).

| Position | Head 1 | Head 2 | Used by |
|---|---|---|---|
| Wait / parked | 262.70 (21016) | -38.20 (-3056) | tool change, warm-up before cleaning, leveling start |
| Wipe, outer end | 257.30 (20584, database `PositionX1`) | -28.30 (-2264) | cleaning (= 1X recording) |
| Wipe, inner end | 231.30 (18504, database `PositionX2`) | -2.30 (-184) | cleaning (= 1X recording) |
| Purge, over the bin | 252.30 (20184) | -23.30 (-1864) | cleaning, after a load (= 1X recording) |
| Load: wait while feeding | 193.35 (15468) | 32.15 (2572) | load (= 1X recording) |
| Unload: wait | 212.70 (home - 50 mm) | 11.80 (home + 50 mm) | unload (= 1X recording) |
| Empty the bin | 133.35 (10668) | 92.15 (7372) | "clean bin": Z to 128.1 mm (= 1X recording) |
| Bed center | 114.00 (9120) | 114.00 (9120) | leveling retry; head 1's place in tandem mode |
| Tandem mode | 114.00 (9120) | 0.00 | `M605 S2` |

- Each head's stations are at its own end, mirrored: the two wipe
  ends and the purge position add up to 229.0 for the two heads, the
  load and bin positions and the sensor edges to 225.5, the homes
  and the unload positions to 224.5.
- Other heights: cleaning `CleaningPositionZ` 10.0 mm (25600) after a
  Z home, with Y at 5.3 mm (427); 3.0 mm (7680) between the steps of
  leveling; load at 23.1 mm (59136); unload at home + 20.0 mm.

## Cleaning (`engine_cleaningXMove(nozzle, type)`)

1. Enable the axes and this head's extruder and cartridge feed.
2. The head goes to its wait position; the nozzle is heated (the
   target depends on the type; type 7 keeps the temperature).
3. To the purge position. What is pushed depends on the type
   (which number is which case is only partly decoded): nothing
   (types 2, 5, 7 and 8: "No inserting filament"); 30.0 mm pushed, a
   wait (3 s; 10 s for PVA and flexible material), then a retract of
   20.0 mm ("Filament Eject normal case") or 15.0 mm ("AUTO RESUME"
   case); or the tool change primes below (types 9 and 10).
4. Wipe: `AutoCleaningMoveCnt` (2) passes between the two ends at
   `AutoCleaningSpeed`, then outer end, then the purge position.
5. Back to idle temperature when it was a manual cleaning.

The purge counter for "empty the bin" goes up by 1 per cleaning, or
by 20 in types 4 and 6 when a flag is set (which flag: not decoded).

## Tool change (`T0`/`T1`, also `M135`; in `printing_thread`)

Refused in tandem mode, and for the same tool ("Same Extruder, do
nothing"). Otherwise:

1. The bed drops 5.0 mm (12800 steps); with active leveling a
   second Z move follows (not decoded).
2. The head that is leaving goes to its wait position.
3. If head 2 is leaving, its offsets are taken out again ("Release
   compensation", below). The bed comes back up 5.0 mm (not in
   spiral mode or with active leveling).
4. The leaving cartridge's use is written to its chip and to the
   nozzle history.
5. Motors: the axes stay enabled, the extruder and cartridge feed of
   the new head are enabled (the other head's are released).
6. If head 2 is coming, its offsets are applied ("Make compensation").
7. Cleaning of the new nozzle: type 9 at the first change of a job
   (prime 20.0 mm at the slow speed, then "injection" 2.0 mm); type 8
   at later changes for PLA, ABS and PVA (no priming); type 10 for
   flexible material (17.0 mm and 1.0 mm). The program's own messages
   call these "14.5mm"/"2mm" and "12mm"/"1mm". A `T` before the first
   move of a file ("declaration") gets no cleaning.
8. The new head goes to its wait position, and the print goes on.

## Head 2's offsets (`engine_nozzleX2_Compensation`)

Head 1 is the reference. When head 2 becomes the printing head the
program makes three relative moves ("Compensation"), and the opposite
ones when it stops being it ("Release"):

| Axis | "Compensation" move | This printer |
|---|---|---|
| X (carriage X2) | minus `X2_AXIS_COMPENSATION` steps | -(-56) = +0.70 mm (to the right) |
| Y | minus `Y_AXIS_COMPENSATION` steps | -(32) = -0.40 mm |
| Z | the difference of the two nozzles' Z offsets (`HomeZOffset_NZ2` + its gap, against `HomeZOffset` + its gap); sign not decoded | 3249 against 3213: 36 steps = 0.014 mm |

It keeps a state word so that each axis is compensated or released
once. X and Y come from the screen's XY calibration, Z from leveling.

## Bed leveling with two heads

- Start (`engine_leveling_prepare`): both nozzles to the leveling
  temperature, part fan off, home, both heads to their wait
  positions, Y to -0.2 mm, Z to 3.0 mm, then (under a condition on
  the nozzle offset setting) a cleaning of type 7.
- **Head 1 touches the three leveling points** (`engine_leveling_R`,
  "R1" to "R3"): X 114.0 (`X1_lvPos`), then -3.0 (`X2_lvPos`), then
  231.0 (`X3_lvPos`), with Y 198.0 (`Y1_lvPos`) for the first.
- **Head 2 touches the first point only** (`engine_leveling_L`,
  "L1"), after homing X2, Y and Z again: that gives nozzle 2's own
  height (`HomeZOffset_NZ2`).
- A failed touch is retried after another cleaning; then error 323.

## Load, unload, empty bin (per head)

The sequences are the 1X's
([1x_stock_routines.md](1x_stock_routines.md), recorded there move by
move) with the positions of the table above:

- **Load:** home Y, Z, both X; **both heads** go to their load wait
  positions (193.35 and 32.15) and the bed to 23.1 mm; the head
  being loaded goes to its outer wipe end for the purge and back.
- **Unload:** home Y, Z; bed to home + 20 mm; home both X; **both
  heads** move 50 mm in from their homes.
- **Empty the bin:** home Y, Z, both X; heads to 133.35 and 92.15
  (clear of both bins), bed to 128.1 mm.

## What a Klipper config can take from this

| Macro value | Head 1 (`T0`) | Head 2 (`T1`) |
|---|---|---|
| X home (position_endstop is the sensor edge) | edge 243.35, park 262.70 | edge -17.85, park -38.20 |
| Homing direction | positive | negative |
| Wipe ends | 257.30 and 231.30 | -28.30 and -2.30 |
| Purge / bin | 252.30 | -23.30 |
| Load wait | 193.35 | 32.15 |
| Unload wait | 212.70 | 11.80 |
| Empty-bin position | 133.35 | 92.15 |
| Offsets when active | none (reference) | X +0.70, Y -0.40, Z 0.014 on this printer: calibrate, do not copy |

The head 2 column is what the 1X's macros already use.
