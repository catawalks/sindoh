# Input shaping with a USB accelerometer

Status 2026-10-27: software prepared, **not yet tested with a sensor**. The
untested parts are the USB binding (below) and the mounts.

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

## Mounts (drafts, not printed yet)

Parametric OpenSCAD files in `install/input_shaping/mounts/`. Every
dimension of the printer in them is a placeholder to be measured:

- `adxl_head_clip.scad`: a bridge over the top of the print head with two
  arms that hook into the notches near the top of each side of the head.
  Needed: head width where the arms grip, the notch position, height and
  depth, and the board's hole spacing.
- `adxl_bed_clamp.scad`: a C-clamp on the front edge of the bed plate,
  tightened by an M3 screw from below. Needed: plate thickness at the front
  edge, the free space under it, and how far the jaws may reach in.

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
