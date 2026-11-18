# Input shaping with a USB accelerometer

Status 2026-11-16: **X and Y measured on the dev printer** (results at the
end). Klipper's picks are in the dev printer's printer.cfg since
11-16 (last section below); no print with them yet. The work printer has no shaper yet.
The first sections describe the stick install on the stock
kernel and are older; "Dev printer, 2026-11-16" below is what was really
done.

Input shaping cancels the ringing (ghost echoes after corners) that limits
print speed. Klipper measures it with an accelerometer shaken by the
printer, once for each axis, and saves an `[input_shaper]` setting.

## What you need

- **A USB accelerometer running Klipper firmware**, RP2040-based: BTT
  ADXL345 V2.0, Mellow Fly-ADXL345 USB, or a Raspberry Pi Pico wired to an
  ADXL345 module. **Avoid boards with a CH340/CH341 USB chip**: this kernel
  can't drive them.
- A USB cable from the front USB port (the one used for firmware update
  sticks) long enough to reach the print head and the bed.
- Mounts: `install/input_shaping/mounts/` (see below).
- numpy, once, with internet on the printer:
  `chroot /mnt/sd sh /usr/src/dp200/klipper_port/install/input_shaping/setup_numpy.sh`
  (Debian's python3-numpy, ~25 MB, exposed to Klipper's virtualenv).

## How the sensor is connected

The vendor kernel (3.2) has no USB CDC-ACM driver, which Klipper's USB boards
use. It does have the generic USB serial driver, and `dp200-start.sh` gives it
Klipper's USB ID at boot:

    echo 1d50 614e > /sys/bus/usb-serial/drivers/generic/new_id

so the board appears as `/dev/ttyUSB0` (`dp200-mounts.sh` creates the
ttyUSB0-3 nodes in the chroot). If that turns out not to work with a real
board, the fallback is `cdc-acm.ko`, built for this kernel and verified
offline (install/kernel_modules/README.md; not loaded yet).

To check by hand after plugging the board in (stock shell):

    dmesg | tail; ls -l /dev/ttyUSB0

## Config

`dp200_adxl.cfg.off` ships disabled; `dp200_printer.cfg` has
`[include dp200_adxl*.cfg]`, which matches only the enabled name
`dp200_adxl.cfg`. Klipper won't start with a configured MCU missing, so the
config is enabled only while the sensor is plugged in. The file has the pins
for the BTT ADXL345 V2.0; other boards need their own pins (see the file).

The resonance test is set gentler than Klipper's default (`accel_per_hz: 50`,
`max_freq: 100`) because of the stock-current A4982 drivers.

## Running it from the touch screen

MOVE -> CALIBRATE -> INPUT SHAPING:

1. Plug the sensor into the front USB port, press **SENSOR ON** (renames the
   config, restarts Klipper).
2. Clip the sensor on the **print head**, press **TEST X**: homes if needed,
   then `SHAPER_CALIBRATE AXIS=X` (about 2 min of buzzing).
3. Move the sensor to the **bed** (this printer moves the bed in Y), press
   **TEST Y**.
4. The page shows the recommended shaper per axis. **SAVE** runs
   `SAVE_CONFIG` (Klipper restarts).
5. **SENSOR OFF**, then unplug the sensor.

If Klipper doesn't start because the sensor is configured but unplugged, the
error page has a **SENSOR OFF** button.

From Mainsail the same works with `SHAPER_CALIBRATE AXIS=X` /
`AXIS=Y` and `SAVE_CONFIG`, after renaming the file by hand.

## Mounts

In `install/input_shaping/mounts/`:

- **`adxl_head_clip.py` -> `adxl_head_clip.stl`** (version 4,
  2026-11-16, not printed yet): for the Mellow FLY-ADXL345 USB on the
  print head. A bridge on the flat top of the head's front block, an arm
  down each side face with a hook and lead-in ramp for a slot in that
  face, and two posts for M3 x 6 screws. The script writes the STL itself
  (no OpenSCAD on the dev PC). Print it standing on its front face; hook
  one side in at an angle, press the other side down.
  - Version 3 (printed in PLA 11-16) snapped tightly onto the head, but
    **the printer could not home X with it on**: X homes at the right
    end, where the Bowden tube comes down in front of the head, and the
    clip's front edge hit the tube. A USB cable from a board in the
    middle would also have hit the right side wall. Version 4 starts
    10 mm behind the front face and has the posts at the left end (left
    post flush with the clip's left side); posts 5 mm high so the screws
    don't bottom out.
  - Slots, by calipers (from the front face, down from the top surface):
    left (side-fan side) rear slot 7 long x 3 high, 20 back, 3.8 down;
    right side's only slot 5 long x 6 high, 21 back, 4 down. The left
    side also has a 5 x 5 opening 12 back and 4.5 down with a spring
    behind it: not used.
  - Also by calipers: head width 55.8; board holes 15.5 apart, 3.2 mm
    (M3 screws). From ruler photos, good to about 1 mm: flat top 23
    deep, side face 32 deep.
  Test the fit, correct the numbers at the top of the script, run it
  again.
- **`adxl_bed_bar.py` -> `adxl_bed_bar.stl`** (2026-11-16, printed and
  used for the Y measurement the same day; it fits): for the Y axis. The build plate has two aluminum tabs at its
  front edge per grip, each with a threaded M3 hole; the plastic grip is
  screwed under them from below. The bar replaces one grip, using its two
  screws (M3 x 6): 88 x 12 mm, 4 mm thick, a rib that fills the gap
  between the tabs, and two posts for the board on the rib. Print it
  flat, posts up. Owner's caliper readings: screw holes 73.5 apart and
  3.75 behind the tabs' front edge, tabs 27 wide, 34 apart, 10 out from
  the plate edge, 2 thick; grip 5 thick at the screws. (A binder clip was
  considered: there is no good place for one. The earlier
  `adxl_bed_clamp.scad` draft is removed.)

A mount must be stiff and tight: a loose mount measures its own wobble.

## First hardware test, 2026-10-30 (Mellow FLY-ADXL345 USB)

- The board arrived running only the **Katapult** bootloader: on the front
  port (EHCI 1, `usb 1-1`) it shows as `1d50:6177`, "rp2040" / "katapult",
  full speed. Klipper firmware (`1d50:614e`) still has to be flashed.
- The generic usb-serial route doesn't work on 3.2: writing the ID to
  `/sys/bus/usb-serial/drivers/generic/new_id` is accepted, but
  `usbserial_generic` has no dynamic IDs at the USB level, so nothing binds.
- **`cdc-acm.ko` works** (with the user's OK, runtime only): `insmod` rc 0, then "cdc_acm
  1-1:1.0: ttyACM0: USB ACM device", and `/dev/ttyACM0` (major 166) exists.
  So dp200-start.sh should insmod cdc-acm.ko instead of the new_id line, and
  Klipper's `[mcu adxl]` uses `/dev/ttyACM0` (or the by-id path).

### Klipper flashed and the sensor read (2026-10-30)

- **Firmware:** Klipper a223dabc (the fork) for the RP2040, Katapult offset
  (16 KiB, application at 0x10004000), USB serial, ID 1d50:614e. Built with Arm
  GNU Toolchain 14.2.Rel1 in WSL. klipper.bin is 45,196 B, md5 6c85cb24...
  (kept in D:\DP200\kernel\out\adxl\, not in the repo).
- **Flashing:** from the PC (the board on COM5, WSL1 /dev/ttyS5, run as root)
  with `lib/katapult/flashtool.py`. Katapult v0.0.1-74 reported application
  start 0x10004000. 177 pages written and verified (SHA 73414EF1...). Katapult
  stays on the board.
- **Check on the PC:** klippy with only this board as `[mcu]` and the pins in
  dp200_adxl.cfg.off. The ADXL345 ID check passed, and `ACCELEROMETER_QUERY`
  gave x 740, y -1776, z -9806 mm/s^2 (1.0 g, the board slightly tilted). The
  firmware has config_spi, spi_send, config_adxl345 and query_adxl345.
- **Printer side changed:** dp200-start.sh insmods cdc-acm.ko (from the port
  sources in the root) instead of the new_id line; dp200-mounts.sh creates
  ttyACM0-3 (major 166) in the chroot; dp200_adxl.cfg.off uses /dev/ttyACM0.
  Not yet run on the 4 GB card.

## Dev printer, 2026-11-16: X axis measured

Setup that was needed (dev printer: mainline kernel, NAND root):

- **The board appears as `/dev/ttyACM0`** when plugged into the front USB
  port (the kernel has cdc_acm). The node belongs to root with mode 600 and
  is created again **every time Klipper restarts** (the board resets), so
  each time: `chgrp dialout /dev/ttyACM0; chmod 660 /dev/ttyACM0`. Until
  then klippy.log repeats "Permission denied" and Klipper stays in
  "startup". Open: do this in rc.dp200 (TODO 12b).
- **numpy:** `setup_numpy.sh` does not work on the NAND root (no apt).
  Done by hand instead: numpy 2.2.4 copied from the 4 GB card's root
  (`/usr/lib/python3/dist-packages/numpy`, 32 MB, same Python 3.13.5),
  plus `blas/libblas.so.3*`, `lapack/liblapack.so.3*` and
  `libgfortran.so.5*` into `/usr/lib/arm-linux-gnueabi/`, `ldconfig`, and
  the `.pth` file as in the script. **The Klipper process must be
  restarted** (`rc.dp200 restart-klipper`): RESTART from Mainsail keeps
  the old Python and still says "Failed to import numpy".
- **`rate: 800`** in `[adxl345]`: at the default 3200 the MCU shut down
  with "Timer too close" 34 s into the test (host overloaded).
- The printer cannot home X with the version 3 mount on (see Mounts). So:
  home with the mount off, `G1 Z20`, `G1 X105 Y100`, clip the mount on,
  run the test. If Klipper restarts in between (homing lost), the head is
  still there: `SET_KINEMATIC_POSITION X=105 Y=100 Z=20`, and home
  properly afterward with the mount off.

Result, `SHAPER_CALIBRATE AXIS=X`, two runs (data in
`D:\DP200\kernel\out\adxl\calibration_data_x_20261116_*.csv`):

| Shaper | Run 1 (to 100 Hz) | Run 2 (to 135 Hz) |
|---|---|---|
| zv | 86.2 Hz, 38.9 % left, accel <= 29000 | 104.8 Hz, 38.2 %, <= 42800 |
| mzv | 50.8 Hz, 8.9 %, <= 7600 | 72.2 Hz, 16.5 %, <= 15400 |
| ei | 69.6 Hz, 12.5 %, <= 8800 | 42.2 Hz, 16.6 %, <= 3200 |
| 2hump_ei | 63.4 Hz, 1.7 %, <= 4300 | 84.4 Hz, 5.4 %, <= 7500 |
| 3hump_ei | 80.2 Hz, 1.6 %, <= 4300 | **80.8 Hz, 0.5 %, <= 4300** |

Klipper recommends `3hump_ei` at about 80 Hz both times. Reading of the
spectrum: one broad peak at 44-47 Hz along X (the real X resonance, not
sharp: only about twice the level around it), a narrow peak at 85 Hz on
the sensor's other horizontal axis (the head or the PLA mount rocking),
and a level floor from 70 Hz to the end of the range. The level floor is
why the simple shapers fit badly and move between runs. Candidates:
`3hump_ei` 80.8 Hz (Klipper's pick, max_accel up to 4300) or `mzv` near
50 Hz (less smoothing, aimed at the 45 Hz peak only). Decide with a
ringing test print; not saved yet. The measurement used the version 3
mount in PLA with the board in the middle; repeat it once with the
version 4 mount.

## Dev printer, 2026-11-16: Y axis measured

Bed bar in place of a front grip, board on its posts, cable to the front
USB port. **Homing with the bar on the bed is fine** (owner, 11-16):
the normal sequence, X and Y first and then Z, clears the sensor. (For
this run the head was moved to X 105, Y 150 before `G28 Z` as a
precaution; that is not needed.) The sensor read 1 g on its Z axis
before the test.

Result, `SHAPER_CALIBRATE AXIS=Y`, one run to 135 Hz (data in
`D:\DP200\kernel\out\adxl\calibration_data_y_20261117_011419.csv`;
the printer's clock is UTC):

| Shaper | Frequency | Vibration left | max_accel |
|---|---|---|---|
| zv | 45.4 Hz | 30.4 % | <= 8000 |
| mzv | 29.4 Hz | 7.5 % | <= 2500 |
| ei | 40.0 Hz | 7.8 % | <= 2900 |
| **2hump_ei** | **39.0 Hz** | **2.3 %** | **<= 1500** |
| 3hump_ei | 48.0 Hz | 2.0 % | <= 1400 |

Klipper recommends `2hump_ei` at 39.0 Hz. Reading of the spectrum: one
wide peak along Y from about 27 to 40 Hz (top at 34.8 Hz), far stronger
than anything on X, and a second peak at 48-52 Hz on the sensor's
vertical axis (the plate's front edge or the bar moving up and down).
Above 60 Hz there is almost nothing. This is the heavy bed on its belt:
the Y axis limits the printer. With `2hump_ei` the acceleration stays at
today's 1500; `ei` 40 Hz or `mzv` 29.4 Hz would allow 2500-2900 with more
ringing left (about 8 %). Decide with a ringing test print; not saved.

## Dev printer, 2026-11-16: X repeated with the version 4 head mount

The version 4 clip (printed in PLA) lets the printer home X with the
board and cable on: the owner checked by hand, and `G28 X Y` then ran
with the mount fitted. Third X run, to 135 Hz (data in
`D:\DP200\kernel\out\adxl\calibration_data_x_20261117_014840.csv`):

| Shaper | Frequency | Vibration left | max_accel |
|---|---|---|---|
| zv | 42.8 Hz | 30.9 % | <= 7100 |
| mzv | 33.2 Hz | 14.6 % | <= 3200 |
| ei | 41.8 Hz | 11.6 % | <= 3200 |
| 2hump_ei | 87.4 Hz | 7.4 % | <= 8100 |
| **3hump_ei** | **82.6 Hz** | **1.5 %** | **<= 4500** |

Klipper recommends `3hump_ei` again (80.2, 80.8, 82.6 Hz over three
runs and two mounts): that result is solid. The spectrum changed with
the mount: the X peak is now sharp at 38 Hz (it was wide at 44-47 Hz
with version 3), the 80-85 Hz peak on the other horizontal axis is still
there, and the level rises again above 110 Hz. In version 4 the board
sits on posts at the clip's left end, so part of this is the mount
itself; the X resonance of the head is somewhere in 38-47 Hz.

**Unplugging the board while Klipper runs shuts Klipper down** ("Lost
communication with MCU 'adxl'"), and the board then comes back as
`/dev/ttyACM1`, because Klipper still holds the old node. Recovery
without touching the plug: find the USB device
(`basename $(dirname $(readlink -f /sys/class/tty/ttyACM1/device))`,
here `1-1`), write that name to `/sys/bus/usb/drivers/usb/unbind` and
then `.../bind`, fix the permissions on `/dev/ttyACM0`, FIRMWARE_RESTART.
Homing is lost. With the bed untouched, Z needs no new homing:
`G28 X Y`, then `SET_KINEMATIC_POSITION Z=20`. Better: turn the sensor
config off (or stop Klipper) before moving the board.

## Dev printer, 2026-11-16: shapers saved

Owner's OK. Added to the dev printer's printer.cfg above the SAVE_CONFIG
block (backup `printer.cfg.bak-1116-shaper`):

    [input_shaper]
    shaper_type_x: 3hump_ei
    shaper_freq_x: 82.6
    shaper_type_y: 2hump_ei
    shaper_freq_y: 39.0

Klipper loaded it (checked in the config it reports). `max_accel` is
still 1500, which is also what the Y shaper allows. The sensor config is
off again (`dp200_adxl.cfg` removed, `.off` kept), so the board can be
unplugged. Next: a ringing test print to judge the result, then decide
on a lighter Y shaper (`ei` 40 Hz allows 2900) and on `max_accel`.

## Ringing test print (started 2026-11-16 on the dev printer)

File `dp200_ringing_tower.gcode` (on the dev printer and in
`D:\DP200\kernel\out\ringing\`). How it was made:

- Model: Klipper's `docs/prints/ringing_tower.stl` (an L shape, two
  120 mm walls, 60 mm tall).
- Sliced with `prusa-slicer-console.exe`, settings taken from the
  owner's last g-code (the config block at its end, saved as
  `owner.ini`), with: no infill, no top layers, 2 perimeters, all
  perimeter speeds 80 mm/s, slicer acceleration control off, slow-down
  only below 3 s per layer, centered at 105, 100. PLA, 1 h 27 min, 11 m.
- Added after the start g-code:
  `SET_VELOCITY_LIMIT MINIMUM_CRUISE_RATIO=0`,
  `SET_PRESSURE_ADVANCE ADVANCE=0`,
  `TUNING_TOWER COMMAND=SET_VELOCITY_LIMIT PARAMETER=ACCEL START=1500 STEP_DELTA=250 STEP_HEIGHT=5`;
  before `PRINT_END`: back to `ACCEL=1500 MINIMUM_CRUISE_RATIO=0.5` and
  pressure advance 0.3. (If the print is canceled, these stay changed
  until Klipper restarts.)

Reading it: acceleration is 1500 for the lowest 5 mm and rises by 250
every 5 mm, to 4250 in the top band (band n from the bottom, counting
from 0: 1500 + 250 n). The wall marked X shows ringing from the X axis,
the wall marked Y from the bed. Look for echoes after the notches and
for the height where corners start to round or layers shift. The highest
clean band gives `max_accel`.

**Result (owner, 11-16; print took 84 min):** both walls are far better
than before shaping.
- Y (`2hump_ei` 39.0): good all the way up, slight ringing above the
  6th band, so clean to 2750.
- X (`3hump_ei` 82.6): ringing after the sharp corners from bottom to
  top; after the softer turns only above the 5th band (clean to 2500).
  So this shaper leaves an X resonance uncovered, most likely the
  38-47 Hz peak, which sits at the low edge of what 3hump_ei at 82.6 Hz
  cancels. The owner also suspects slack in the X belt or drive.

**`dp200_x_shaper_compare.gcode`** (same tower and slicing, made
11-16, printed 11-17): acceleration fixed at 2500, the X
shaper changes every 10 mm with `SET_INPUT_SHAPER` (Y stays 2hump_ei
39.0). Bands from the bottom: 1 `3hump_ei` 82.6 (reference), 2 `ei`
41.8, 3 `2hump_ei` 48, 4 `mzv` 38, 5 `3hump_ei` 60, 6 `2hump_ei` 87.4.
The band with the cleanest X wall and still crisp notches wins. The
ringing frequency can also be read off the part: ripple spacing in mm
at 80 mm/s gives 80 / spacing in Hz.

**Result (printed 11-17 on our system, owner's photos):** no visible
difference between the six bands. The printer's log shows every
`SET_INPUT_SHAPER` applied at its height, so the shapers did change.
The X ripples after the sharp corners look the same with shapers
aimed at 38, 42, 48, 60, 83 and 87 Hz, all of which cover the
measured 38 Hz X peak. So what is visible is not that peak:
- either a different frequency the shapers don't cover (read it off the
  part: ripple spacing at 80 mm/s, 80 / spacing in Hz: 2.1 mm = 38 Hz,
  4 mm = 20 Hz, 1 mm = 80 Hz),
- or a non-linear effect no shaper can cancel: backlash / slack in
  the X belt, a loose pulley, play in the carriage (the owner's
  suspicion), or extrusion at the corner (the tower runs with PA 0).
Next: measure the ripple spacing; check the X belt tension, the motor
pulley set screw and carriage play; one band with shaping off
(`SHAPER_FREQ_X=0`) next to one with the saved shaper shows whether
shaping does anything visible at all.

**Cause and decision (owner, 11-17):** the print head has play: it is
held only by strong magnets on a loose dovetail. The ripple spacing is
about 4 mm, i.e. about 20 Hz at 80 mm/s, below every shaper tried and
far below the measured 38 Hz peak, so no shaper removes it; a new
carriage mount is a future project. Since the ripple stays either way,
X gets the shaper that costs least speed: band 6, **`2hump_ei` 87.4 Hz**,
set in the dev printer's printer.cfg 11-17 (backup
`printer.cfg.bak-1117-shaper`). Klipper's own limits for the bands
(`find_shaper_max_accel`, scv 5, computed on the printer):

| Band | Shaper | max_accel | smoothing |
|---|---|---|---|
| 1 | 3hump_ei 82.6 | 4528 | 0.133 |
| 2 | ei 41.8 | 3182 | 0.189 |
| 3 | 2hump_ei 48 | 2417 | 0.246 |
| 4 | mzv 38 | 4254 | 0.141 |
| 5 | 3hump_ei 60 | 2368 | 0.251 |
| 6 | **2hump_ei 87.4** | **8094** | **0.074** |
| Y (saved) | 2hump_ei 39.0 | 1476 | 0.372 |

Y is now what limits `max_accel` (1500 today). The ringing tower
showed Y clean to 2750 and this print ran X at 2500 without trouble.
