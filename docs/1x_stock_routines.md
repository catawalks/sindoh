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
- **X home sensor and dump station, measured 2026-11-22** (X with the
  left wall at 262.7, the program's X maximum): the home sensor
  switches on about 20 mm before the wall (19.3 mm with the head pushed
  to the wall by hand, 20.3 mm from where stock parks it after homing;
  the same within the method's error) and stays on from there. The Y
  sensor switches on 5.5 mm from where stock parks the bed. The owner,
  jogging: dump bin center 246.5; the cleaning flap is the right-hand
  one, at 237.5, and the nozzle lets go of it at 250 moving left and at
  225.5 moving right. The taller left flap at 253.5 is not for
  cleaning: it folds over under the nozzle when the head is at rest (a
  cap against dripping, our reading).
- **The database's X positions** are not plain positions in this frame;
  see the move-by-move recording below for where stock really goes.
- **Home sensor inputs:** X is GPIO 99, Y is GPIO 82, both high at home
  (found by moving the head and bed by hand); Z is GPIO 83, high at
  home too (it changes once in each stock Z homing, and Klipper homed
  all three axes on these inputs, 2026-11-21). Neither door has a sensor.
- **Order of a stock "home all", as recorded:** Z, then Y, then X.

## Motors as the stock firmware drives them (recorded 2026-11-21)

Recorded read-only with `regwatch` (sindoh-klipper `host/regwatch.c`)
while the owner homed and jogged from the stock screen.

| Axis | Stepper engine | Step | Dir | Enable (our reading) | Home | Checked scale |
|---|---|---|---|---|---|---|
| X | 0 (0xF8150000) | GPIO 162 | 163 | 164 | 99 | 10 mm = 800 steps |
| Y | 1 (0xF8151000) | GPIO 168 | 169 | 170 | 82 | 10 mm = 804 steps |
| Z | 2 (0xF8152000) | GPIO 36 | 37 | 38 | 83 | 10 mm = 25600 steps |

- X, Y and Z are the three hardware pulse engines, used as on the DP200
  with every register 0x28 higher: control at +0x6C (0x33224, direction
  is bit 4), busy in bit 8 of +0x8C, and a 24-bit edge counter at +0xA0
  that counts two per step, up or down with the direction. The engines
  idle at 0x444444 in the control register until the first move.
- **Extruder and cartridge motors** (recorded during a stock filament
  load from a Sindoh cartridge): the extruder is engine 3 (step GPIO 42,
  dir 43, enable 44 by the pattern), the cartridge feeder is engine 4
  (step GPIO 48, dir 49, enable 50). The cartridge motor feeds alone
  first, then both run with the extruder at about twice the cartridge's
  step rate (console: "PressToOffMovedStep, E:4296, C:2062"). Engine 5
  never changed (the 2X's second set, our reading; pins 54-58).
- **The extruder has a press and a clutch worked by the motors.** The
  stock program has `StepperPressPositionToOn`, `StepperPressPositionToOff`,
  `StepperPressClutchOn`, `StepperPressClutchOff`, `engine_extrPressRelease`
  and `engine_extrPressAdjust` (with a `_flexUnload` variant), and at
  wake-up it prints "PressToOffMovedStep, E:4296, C:2062" and
  "PressToOnMovedStep, E:5075, C:2436" while both motors run briefly.
  A normal feed does not use them (no such output changed during
  recorded stock feeds). Decoded from the FM microcode: the press
  clutch is GPIO 148 (argument bit 0) and GPIO 191 (bit 1); the four
  solenoids are PWM blocks 18, 8, 24 and 26.
- **Feeding, as recorded from stock (two 10 mm feeds, one retract):**
  the extruder engine runs exactly 4588 steps per 10 mm (**458.8
  steps/mm**) and the cartridge feeder about 2203 (220.35 steps/mm),
  always together. The extruder engine's control register is 0x33024
  for feed and 0x33034 for retract, the cartridge engine's 0x30224 and
  0x30334; X, Y and Z use 0x33224/0x33234. With the axis value on the
  extruder engine its driver counts steps but the motor does not turn.
  Klipper extruded with the stock values (2026-11-21).
- **Two feed motors at the rear, in series** (owner, with the rear
  gear train open, 2026-11-21): engine 4 is the initial feed motor at
  the cartridge bay; engine 3 is **the extruder motor**. It sits at the
  rear too and pushes the filament through the tube to the head; there
  is no motor after it.
- **The cartridge-bay switch is GPIO 80, one signal for two things**
  (watched live under Klipper while the owner tried each): it goes low
  when filament is pushed in through the filament opening port, and
  equally when its arm is lifted to the top as a cartridge does. An even
  lower path into the feeder passes under the arm and does not trip it.
  GPIO 76 (`gp_cartFilaSensor[0]`) never changed: by the pattern of the
  other "[0]" signals it belongs to the 2X's other bay (our reading, and
  the owner's), as GPIO 121 does to the other extruder.
- **How the stock load is sequenced** (console and pin recordings):
  the first motor starts alone; check "411" passes when the
  cartridge-bay filament switch (GPIO 80) changes, within a second;
  when the filament reaches GPIO 120, about 8 s later, the rear motor
  starts in that same second and both run on. If GPIO 80 never changes
  (loose filament fed past the switch in open-filament mode) the
  sequence waits at check 411, the rear motor is never started, the
  first motor keeps pushing into a stationary gear, and the load ends
  in a jam and "Load 411Error". The switch also reports a cartridge.
- **A good open-filament load** (PLA, console log only, 2026-11-21):
  start LOAD first, then push the filament in through the opening port.
  Filament already in the switch before LOAD is taken for a cartridge
  and the screen asks to remove it (owner). Console times from the
  start of the load: "Pass411" at 0 s, "Pass412" at 0.9 s, "Pass413" at
  7.7 s ("-L3-"), "Pass414" at 12.4 s, "-L4-" and "-L5-" at 36.7 s; the
  nozzle goes to 200 °C at the start and 220 °C for the purge.
- **The same load and an unload with the pins recorded** (PLA, open
  filament, 2026-11-21; step-pin edges counted, two edges a step,
  lengths from 458.8 and 220.35 steps/mm):
  - Load: the initial feed motor alone at 59 mm/s for 7 s (412 mm)
    until GPIO 120 trips; then both motors at 29.7 mm/s for 29 s
    (857 mm on the extruder); a 2 s pause; then the purge, both at
    2.0 mm/s for 30 s (60 mm); last a fast 18.6 mm retract.
  - Unload: both motors back at 29.7 mm/s for 34 s (914 mm on the
    extruder) until GPIO 120 releases; then the initial feed motor
    alone at 59 mm/s for 15 s (789 mm). GPIO 80 released 11 s into
    that, 4 s before the motor stopped.
  - The two motors always run at the same filament speed when both run
    (extruder 13627 steps/s, initial feed 6540 steps/s).
- **Filament sensors:** GPIO 120 (`gp_extrFilaSensor[1]`) is low while
  filament is at the extruder's entry and high when it is gone (seen
  during a retract). From the cartridge bay to the extruder the
  filament path is about a meter long.
- **Filament motion encoder:** GPIO 65 and 67 pulse while filament is
  fed (about 31 changes a second at the load speed).
- A sixth line of each axis group (GPIO 167 for X, 173 for Y, 41 for Z)
  carries a fast signal from the moment the axis is first used; not
  identified.
- **Under Klipper (2026-11-21, owner watching):** all three axes moved
  through the same engines, 5 mm out and back. With the direction pin
  high, X goes left (toward its home), Y comes forward (away from its
  home at the back) and Z goes down (away from its home at the top).
  The Z engine counted 12800 steps for 5 mm.
- The TMC2224 UART is GPIO 154/155, with select lines 146/147/149 and
  152; it is used at the start of each Z homing (the Z `TPWMTHRS`).
- The beeper is PWM block 19 (period 250, 90 high).
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
- **Seen on the machine (2026-11-21, owner ran the stock routine while
  the pins were recorded):**
  - **The contact input is GPIO 81** (next to the home sensors on 82 and
    83). It changes, with some bounce, at every touch. The enable line
    (GPIO 153) switches on just before the first approach.
  - Each of the three points is touched **three times**, about four
    seconds apart; the points follow each other after a re-home of X
    and Y.
  - It starts with a nozzle-wipe routine: the hot nozzle tip is pressed
    into the bed's edge strip and run along several paths (the console
    prints "ZigZag manuever Start").
  - The nozzle is held at 150 °C for the measurement (bed about 46 °C,
    unheated by the routine).
  - Result screen: "Assisting Bed Leveling... Turn the screw wheels in
    the direction of the arrow", one figure per wheel in clicks and
    degrees. One click is 45 degrees (seen: "1 click(s) (45 degrees)"
    left, "3 click(s) (135 degrees)" right).
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
  stock way to let it cool: after the set time it switches off the
  heaters, the case lights and the motors (owner).
- **Reading the temperatures:** the microcode publishes them in
  milli-degrees in the shared memory (offset 0xAF40: nozzle 1, nozzle 2,
  bed). ADC mux select 1 is the nozzle thermistor, 2 and 3 both read the
  bed, 4 is open on the 1X. The lookup tables are the DP200's with the
  same index bases (index = 11-bit code - 110 for the nozzle, - 381 for
  the bed).
- **Start-up heater test:** each nozzle heater is switched fully on for a
  moment at boot ("FULL Heater 1 is Enabled as 1000", the reading climbs
  about 35 °C in 13 s). Heater 0 reports -60 (no sensor) on this 1X; the
  code is shared with the two-nozzle 2X. Whether the 1X's hot end has
  one heater cartridge or two is open (owner's guess: two).
- The microcode, not the Linux program, runs the temperature loops: it
  goes on holding the targets when the Linux program is stopped. It has
  its own cut-out ("over 270*1000mC, SAFE FUNCTION PWM = 0") and
  "Out Of Control Loop" errors.

## Fans, lights and beeper (switched one at a time, 2026-11-21)

| Output | What it is (owner watching, 2026-11-21) |
|---|---|
| PWM block 2 | part cooling fan |
| PWM block 10 | power supply fan (80 % whenever stock is up; enable GPIO 127) |
| PWM block 20 | back right exhaust fan |
| GPIO 188 (`gp_En_NozzleFan[1]`) | extruder (hot end) fan, on/off |
| GPIO 112 (`gp_En_MainFan[1]`) | back left exhaust fan, on/off |
| PWM block 7 | case lights (static level) |
| PWM block 19 | beeper (period 250 = 4 kHz, duty 0.36 as stock) |
| PWM blocks 14, 22; GPIO 225 | nothing on the 1X (the 2X's second head, our reading) |

- The power supply fan seems to run whenever the heaters can be on
  (owner).
- **Heater outputs** (worked out 2026-11-21 from the recorded cartridge
  load, matching each PWM block's on/off times with the console's
  heater messages):

  | PWM block | Heater | Evidence |
  |---|---|---|
  | 5 | **nozzle** (the stock "heater 1" / EX2) | off and on again within a second of each "N:1 ... En:0" and "N:1, T:240, En:1"; full on, then 99 % duty, on the way to 240 °C |
  | 28 | **bed** (heater 2) | switched on at wake-up, 95 % duty until "BD Target Reached" |
  | 25 | heater 0: the 2X's other nozzle | no sensor on the 1X (reads -60 °C), and the stock firmware leaves this output switched fully on whenever heaters are enabled. Nothing can be connected to it on a 1X. **On a 2X this is a real heater: never give it a heater without its sensor.** |

  Confirmed under Klipper the same day: block 5 heated only the
  nozzle, block 28 only the bed.
- The fan "lock" inputs in the GPIO table of [1x.md](1x.md) are the
  matching tach or stall signals; not checked yet.

## The speaker (voice messages)

Besides the beeper the 1X has a real speaker (owner, 2026-11-21: it
speaks when buttons are pressed). Read from the running stock system:
- It is a **USB audio device** ("CONEXANT USB AUDIO"), ALSA card 0 with
  playback and capture (`/dev/snd/pcmC0D0p`, `pcmC0D0c`).
- The stock app plays MP3 files with `/bin/mplayer`: about 410 files in
  `/app/TTS/` in four languages (`eng`, `kor`, `chn`, `jpn`), named by
  the menu or error they belong to.
- **The amplifier has its own enable: GPIO 180** (`/app/audio_amp.sh`:
  set = on, clear = off). Stock switches it by the "speech" settings
  in its database (`CONF_PLAYBACK`: `SpeechEnable`, `AMPAutoTurnOFF`).
- For Klipper this means any sound can be played from Linux (tones,
  tunes, spoken messages) with an ALSA player and GPIO 180 high; no
  firmware work is needed. Not tried yet.

## Unload, load and "clean bin" recorded move by move (2026-11-22)

Recorded on the stock firmware with `movewatch` (sindoh-klipper
`host/movewatch.c`: read-only, follows each motor's step and direction
pins and prints one line per move) while the owner ran the three
routines from the screen; PLA, open filament. X positions below are in
the frame where stock's home is 262.7 (the X maximum) and the home
sensor's edge 242.35; X grows to the left. Z is given from the bed's
rest position after homing (stock's Z 3.1, our reading).

**How stock homes.**
- X, from on the sensor: right 35.00 mm; left until the sensor trips
  (it runs about 4.9 mm past the edge); right 4.90 mm, which releases
  it; left 20.35 mm (1628 steps), tripping at once. Home is therefore
  20.35 mm past the edge, at the left wall. From off the sensor the
  first move is left out.
- Y: forward 10.00, back until it trips (7.28), forward 2.79, back
  5.50: home is 5.50 mm past the edge.
- Z: up until the sensor trips plus about 1.5 mm, then down 7.24 mm to
  rest. The sensor is released again after the first 0.3 s of that.

**Unload** (27 s of heating between positioning and the first pull).
1. Part fan on. Home X. Home Z, then down to rest + 20.0 mm. Home X
   again, then right 50.00 mm: the head waits at **X 212.7**, right of
   the dump station.
2. Extruder and feed motor pull together (5 s at 10 mm/s, then
   29.7 mm/s) until the extruder's entry sensor releases; the extruder
   stops 0.7 s later (913.7 mm in 34.1 s). The feed motor goes on alone
   at 59 mm/s and stops 4.1 s after the bay switch releases (1685 mm
   in all, 47.3 s).
3. Part fan off. 3.3 s later PWM block 8 (a solenoid) is on for 9.9 s.

**Load** (the nozzle target goes to 200 C at the start: stock feeds
while it heats).
1. Part fan on. Home Z, home X, then right 70.33 mm: the head waits at
   **X 192.4**. Bed down 13.1 mm from rest.
2. Feed motor alone at 59 mm/s until the entry sensor trips (7.7 s,
   about 453 mm); then both for 28.8 s (extruder 854.5 mm).
3. 10 s wait, ended by the nozzle reaching its target.
4. **The head moves to the bin: left 60.44 mm to 252.8, then right
   5.00 mm to 247.8.** It reaches the purge position from the left.
5. Purge 60.0 mm in 30.3 s (1.98 mm/s), both motors. 0.5 s pause.
   Retract 20.0 mm in 0.53 s. 3.0 s pause.
6. Wipe: left 14.9 to the wall (262.7); right 35.9 to 226.8; left 26.0
   to 252.8; right 26.0; left 26.0; right 5.00. It ends at **247.8**,
   again reached from the left. Each 26 mm pass takes 0.66 s.
7. Part fan off.

**Clean bin.** Home Z; home X; right 130.35 mm to **X 132.4**; bed
down 118.1 mm from rest. It waits for the owner. On "done": home Z,
home Y, home X, home Y and X once more, then Z.

**Against the database:** the wipe ends are `PositionX1` 257.3 and
`PositionX2` 231.3, 4.5 mm above the recorded 252.8 and 226.8, and the
pass count is `AutoCleaningMoveCnt` 2. The recorded waiting positions
(212.7 unload, 192.4 load) and the purge position 247.8 are not the
table's 256.4 and 243.4: the tables are not used as plain positions.
The owner's readings of the same day agree with the recording: bin
center about 246.5 to 247.5, the cleaning flap released at 250 moving
left and 225.5 moving right.

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
- **A cartridge load as recorded:** console "Load ext: 1, FilaType:6"
  for a Sindoh TPU cartridge (the screen then shows "FLEX"), stages
  "Load Pass411" to "414" and "-L0-" to "-L5-", nozzle to 240 °C. (The
  cartridge was a DP200 one the owner modified to fit: the 1X's
  cartridge shell is slightly different.)
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
