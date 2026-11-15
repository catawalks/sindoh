# Testing on the dev printer

How to run the standard tests and switch Klipper builds on the dev printer
(serial COM3, Ethernet 10.10.0.147, Moonraker on port 7125). The state of
the printer is in [STATUS.md](STATUS.md); open work is in
[../TODO.md](../TODO.md).

## Rules before anything moves or restarts

1. **Idle check before any restart or deploy** (Klipper, the screen app,
   config upload):
   `curl 'http://10.10.0.147:7125/printer/objects/query?print_stats=state&idle_timeout=state'`
   must show `standby`/`complete`/`cancelled` and `Idle` or `Ready`.
2. **No motion and no heat unless the owner is at the printer and said so**
   for that step. Ask again after a print: the part is still on the bed.
3. **Z homes upward.** Never home Z (G28, PRINT_START, any probe command)
   unless the owner has just confirmed the bed is empty. `BED_CLEAR` then
   tells Klipper so.
4. The printer forgets its homing after 10 idle minutes. A script that
   needs a homed printer must check `toolhead.homed_axes` and home again
   (with rule 3).
5. Use Moonraker on port 7125 directly; nginx on port 80 cuts a G-code
   request off after 60 s.

## Files and how they reach the printer

The PC serves `D:\DP200\kernel\out` on `http://10.10.0.85:8099/`
(`py -3 -I -m http.server 8099 --bind 10.10.0.85 --directory D:/DP200/kernel/out`).
Put a script in `deploy/usb/t/` there, then on the serial console:
`cd /tmp && wget -q -O x.sh http://10.10.0.85:8099/deploy/usb/t/x.sh && . ./x.sh`.
Serial commands longer than one line get cut off, which is why scripts
are fetched this way (`tools/serial_cmd.ps1 -cmd '...' -timeout N`).
Config files and G-code go through Moonraker's upload
(`/server/files/upload`, `root=config` or `root=gcodes`).

## Switching the Klipper build (host code + both firmware images)

The host code (`klippy/`) and the two UPC firmware images must come from
the same fork commit: the protocol dictionary is in the firmware.

1. The NAND root has **no compiler**. If `klippy/chelper/*.c` differs
   between the builds, `c_helper.so` has to be built first:
   `tools/klippy_build_chelper.sh` does it on the printer with the gcc on
   the SD card (mount the card read-only first:
   `mkdir -p /mnt/sd && mount -o ro /dev/mmcblk0p1 /mnt/sd`). It expects
   `klippy-<name>.tgz` on the PC server, made with
   `git archive --format=tar.gz -o klippy-b.tgz <tag> klippy` in the fork.
   The result lands in `/tmp/kb/<name>/klippy` (RAM: gone after a reboot).
   It takes about 3 minutes per build.
2. `tools/klippy_switch.sh` with `N=<name>` copies that klippy into
   `/home/klipper/klipper/klippy`, installs `fm-clean-<name>.bin` and
   `io-clean-<name>.bin` from the PC server into `/opt/dp200`, and runs
   `rc.dp200 restart-klipper`. The first run saves the old build as
   `klippy.cur`, `fm.bin.cur`, `io.bin.cur`; `N=cur` switches back.
3. Check: `/printer/info` shows `state: ready` and the new
   `software_version`; `/printer/objects/query?mcu&mcu%20io` shows the
   firmware commit on both cores.

## The standard motion tests

| Test | Script | What passes |
|---|---|---|
| Homing + X/Y lost steps | `py -3 tools/drift_test.py LOGFILE` (about 30 min, no heat) | Every "shift" within +-0.04 mm and not growing from run to run. The switch readings scatter by 0.02 mm (once 0.04) even with no moves; lost steps would show as a shift that accumulates. |
| A print, watched | `py -3 tools/print_watch.py FILE.gcode LOGFILE` | Ends with `complete`. It sends `BED_CLEAR` itself: only run it after rule 3. |
| Probe settling / left-right slope | `py -3 tools/probe_settle.py` (about 10 min, no heat) | See "Probe" below. |

Test prints come from `py -3 tools/gen_test_prints.py OUTDIR`:
`dp200_box_20mm.gcode` (7 min; measured 20.0 x 19.8 x 10 mm on 11-14) and
`dp200_xy_scale_150mm.gcode` (27 min, an L with 150 mm arms; the X arm is
10 mm wide, the Y arm 15 mm).

## Probe: settling and the false left-right slope (2026-11-14)

- **Settling:** after the pin is deployed, the first touch reads about
  0.03 mm high and it takes about five touches to settle.
  `BED_MESH_CALIBRATE` therefore touches the reference point five times
  first (`variable_warmup` in `dp200_macros.cfg`).
- **False slope along X:** on the dev printer the probe read the right
  side of the bed 0.14-0.19 mm lower than the left, while a nozzle paper
  test showed the bed level within 0.025 mm. With a mesh, the first layer
  was too high on the left and squashed on the right. The pin sits 23.5 mm
  right of and 28 mm in front of the nozzle; the reading also changes by
  0.02-0.04 mm with the direction the carriage arrived from.
- **Fix:** `[axis_twist_compensation]` in that printer's own `printer.cfg`
  (values are per printer). Klipper's calibration command does not work
  with this pin, so the values are entered by hand:
  1. Mesh off (`BED_MESH_CLEAR`, `SET_GCODE_OFFSET Z=0`), home.
  2. Run `tools/probe_settle.py`: settled probe readings at bed X 25, 100,
     175 (Y 30).
  3. Paper test with the **nozzle** at the same three spots: park at
     Z 0.6, the owner jogs Z down until the paper drags, read
     `toolhead.position[2]` each time.
  4. For each spot d = probe - nozzle. `z_compensations` = mean(d) - d,
     left to right. The template `klipper/config/printer.cfg` has the
     section, commented out, with the dev printer's values.
  5. Restart Klipper, run `tools/probe_settle.py` again: the three
     readings should now differ the way the paper test did.

## Scale check (are the steps per mm right?)

Measured 2026-11-14 on `dp200_xy_scale_150mm.gcode`: X 149.60, Y 149.40
(nominal 150); widths 14.90 (X) and 9.90 (Y). That is a fixed loss of
about 0.07 mm plus 0.2-0.4 % shrinkage, normal for PLA. A 1 % step error
would give 148.5. `rotation_distance: 40` on X and Y is right.
