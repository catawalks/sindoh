# Sindoh 1X: axes, limits, homing, bed leveling and stock routines

**Source:** the owner's 1X (`ROD1X_200916_2`), 2026-11-21. Read from its
settings database (`karas.db`, live row NO=4), from Sindoh's motion
program (`marvell_lspsdk_3dp_granite2-debug_stripped.elf`: constants and
call order, disassembled on the PC) and from the stock touch-screen app's
pages (`/app/SVN_GUI`, copied to the PC). Nothing was moved, heated or
changed on the printer; **none of this has been checked by watching the
machine**. "(our reading)" marks inferences. Hardware background:
[1x.md](1x.md).

## Axes and limits (compiled into the motion program)

The program prints these at start-up (`engine_init`); the numbers are
constants in its code.

| Axis | Min | Max | Steps per mm | In steps |
|---|---|---|---|---|
| X | -3.10 mm | 262.70 mm | 80 | -248 ... 21016 |
| Y | about -0.6 mm | 200.02 mm | 80.4 | ... 16082 |
| Z | (not decoded) | 310.00 mm | 2560 | ... 793600 |

- The printable area Sindoh advertises is 228 x 200 x 300 mm. X travel
  goes about 35 mm past the bed, to where the nozzle cleaning and filament
  stations are (below). (our reading)
- **Z is the bed, and it moves down as Z grows:** the app's "Bed is being
  lowered ... to the bottom" page, and Z home at the top. As on the DP200,
  **homing Z brings the bed up to the nozzle.**
- Jerk settings (database): XY 20, Z 0.1, E 5 mm/s.
- Motor current offsets (database, this printer): X -15, Y +40, Z +40,
  E +50.
- Axis names in the program: X1, X2, Y, Z, E, C (C = cartridge feed
  motor), plus a clutch and a solenoid. The code is shared with the
  two-carriage 2X; on the 1X the carriage is "X2" in several routines.

## Homing

Each of X, Y and Z has a home sensor ("HomeTouch X1,X2,Y,Z"). The
routines `engine_initGoZ`, `engine_initGoX2`, `engine_initGoY` all work
the same way, like the DP200's:

1. If the sensor is already on, move off it by a set distance; still on
   afterwards is error 501 (X) or 503 (Z).
2. A long move toward home until the sensor trips (`StepperHome*LongJump`).
3. A slow search for the exact edge (`StepperHome*FindHome`).
4. A final move by an offset to the working zero.

- Order for a full home: `engine_initCombinedZYX` (Z, then Y, then X, by
  its name; not traced).
- Stored offsets: `HomeZOffset` 1233 steps = 0.48 mm, `gapAdjust`
  1792 steps = 0.70 mm. The app's "Home Position" page lets the user set
  the nozzle-to-bed gap (its text: default 0.25 mm) and has buttons to
  home all axes or X, Y, Z alone.
- **Where home is** (owner, at the printer, 2026-11-21): the head parks
  at the **left**, the bed at the **back** and at the **top**; the
  cleaning and filament stations are on the left too (owner homed the
  machine and checked). The stations sit at X 231...257 mm in the stock
  numbers, so (our reading) the stock X coordinate grows toward the
  left and home is at its high end: the 1X's single head is the 2X's
  "X2" carriage. The X travel is this long because the chassis is the
  2X's, with one head parked at each end; the right-hand parking spot
  is unused on the 1X. On the 2X each head has its own filament dump
  station and cleaning area at its own end (owner).
  Y is the bed moving front to back, and Z is the bed going up.
- The homing moves themselves run inside the FM microcode (commands 0x1A
  to 0x1F: Z long move, Z find, Y long move, Y find, X long move, X
  find); the Linux program only starts them. After them it sets Y to
  427 steps (5.3 mm) and Z to 7936 steps (3.1 mm).

## Bed leveling: the nozzle is the probe

There is no deployable pin as on the DP200.

- **Sensing:** the program switches on a level sensor enable (GPIO 153,
  `gp_En_LevelSensor`) and a line it calls "nozzle voltage" (GPIO 69,
  `gp_Nozzle_Voltage_On`; `engine_leveling_setVolt`), then
  `StepperGetZOffset` has the FM core raise the bed until it reports
  contact ("Contact OK" / "Contact Fail") and returns the height.
  (our reading) An electrical contact between the nozzle tip and the
  metal bed plate; that is why the nozzle is cleaned first.
- **Sequence** (`engine_leveling_prepare`, then `engine_leveling_L` or
  `_R`, then `engine_leveling_check`):
  1. Home X, Y, Z. Bring the nozzle to a set temperature (cool down or
     warm up), part fan off.
  2. For each of three points: wipe the nozzle at the cleaning station,
     home Z, X and Y again, move to the point, measure (with retries).
  3. Compare the three heights. Inside the allowed range
     (`ZErrorRange` 256 steps = 0.10 mm): "Leveling is OK". Otherwise the
     screen says how far to turn the **two screw wheels** ("TURN screw
     L: .. Deg, R: .. Deg"; app text: "Turn the screw wheels in the
     direction of the arrow", in turns and clicks), and it measures again.
- **The three points** on this printer (database, steps, then mm at the
  scales above): (9120, 16080) = (114.0, 200.0), (-320, 0) = (-4.0, 0)
  and (18560, 0) = (232.0, 0). (our reading) One point at the back
  center, which is the fixed one, and one at each front corner over a
  screw. The X values are in the leveling routine's own carriage
  coordinates (-4 mm is outside the X limit above), so check them on the
  machine before using them.
- Heights used: start 20800 steps = 8.1 mm, `Z2_lvPos` -5920 steps
  = -2.3 mm.
- **Active leveling** is a second, optional mode: ten stored factors
  (`CONF_ENGINE_ACTIVELEVELING`) correct Z in software during a print
  when both the machine setting and the G-code ask for it. It is off on
  this printer (all factors 0).
- A print start checks that leveling has been done at least once ("Leveling
  is not executed at all, required").

## Heat at idle and at start-up (seen on the machine, 2026-11-21)

- **The stock firmware keeps the printer warm all the time:** nozzle
  80 °C and bed 50 °C on the screen whenever it is idle (owner). The boot
  log shows the settings going to the IO microcode: heaters 0 and 1 to
  80, heater 2 (the bed) to 50. The screen's power saving setting is the
  stock way to let it cool.
- **Start-up heater test:** each nozzle heater is switched fully on for a
  moment at boot ("FULL Heater 1 is Enabled as 1000", the reading climbs
  about 35 °C in 13 s). Heater 0 reports -60 (no sensor) on this 1X; the
  code is shared with the two-nozzle 2X. Whether the 1X's hot end has
  one heater cartridge or two is open (owner's guess: two).
- The microcode, not the Linux program, runs the temperature loops: it
  goes on holding the targets when the Linux program is stopped. It has
  its own cut-out ("over 270*1000mC, SAFE FUNCTION PWM = 0") and
  "Out Of Control Loop" errors.

## Nozzle cleaning, load and unload (database, this printer)

X positions at 80 steps/mm, Z at 2560 steps/mm.

| Routine | Where | What |
|---|---|---|
| Nozzle cleaning | X 257.3 and 231.3 mm (wipe between them, 2 passes), Z 10.0 mm | Heat to 200 °C (PLA) or 230 °C (ABS), push some filament, wipe, retract |
| Load | X 256.4 mm, Z 23.1 mm | Heat to 230 °C (PLA) or 250 °C (ABS), feed in stages, purge, then to X 243.4 mm |
| Unload | X 256.4 mm, Z 23.1 mm | Heat as for load, short push, fast retract in stages |
| Pipe cleaning | X 275.7 mm (beyond the X limit above: its own coordinates) | A separate purge routine |

- Preset temperatures: PLA 210 °C first layer, 200 °C after, 150 °C
  preheat; ABS 250 / 230 / 200 °C. Bed preheat presets are 0.
- Filament runout is watched by step counts against an encoder
  (`CONF_ENGINE_FILACHECK`), and the camera-based "object detect" check
  before a print is enabled.

## The stock app's menus (for a Klipper screen app later)

Pages in `/app/SVN_GUI/html`: main, print (USB, file list, job list,
history), printing (with bed move and settings during a print),
cartridge and open-material ("openspool") pages, load, unload, extruder,
X/Y/Z jog (0.1, 1, 10, 100 mm steps), home position, bed leveling,
active leveling, nozzle cleaning, nozzle calibration (XY and Z), nozzle
replacement, lamp, beep, speech, energy save, language, time, network,
cloud, security, and a service menu (`sp_*`: sensors, fans, auto
leveling, machine Z offset, preheat, error log, stored-and-print).

## What a Klipper config can take from this

- `rotation_distance` from 80 steps/mm (X), 80.4 (Y) and 2560 (Z), once
  the microstep setting of the TMC2224s is known.
- `position_min`/`position_max` from the limits above; Z homes toward the
  nozzle, so the same "is the bed empty?" guard as on the DP200.
- Bed leveling as a nozzle-contact probe: Klipper's `[probe]` with the
  contact input as the pin and `z_offset` near 0, three points for
  `[screws_tilt_adjust]` (the stock routine's own advice in turns), and
  optionally a mesh. Which input carries the contact signal is still to
  find (stage 4 of the port plan).
- Cleaning, load and unload positions and temperatures for the macros.
