# Installing Klipper on a Sindoh 3DWOX DP200

> **Status: preview.** Klipper runs on the developer's printer. The one-stick
> installer described here has been rehearsed (dry run) but not yet run end to
> end on a printer. Read "Getting back to stock" before you start.

## What you get

- **Klipper** firmware running on the printer itself. The two motion and I/O
  coprocessors of the DP200's Marvell chip become Klipper MCUs; nothing
  extra to buy.
- **Mainsail** web interface at `http://<printer-ip>/`, with the built-in
  camera.
- **The touch screen:**
  - temperatures and job progress;
  - lamp, preheat, filament load/unload, home, lower bed;
  - pause/resume/cancel and first-layer Z adjustment;
  - an emergency STOP (hold 1 s).
- **Before every print:** automatic bed mesh with the printer's own levelling
  probe, plus nozzle purge and wipe over the purge bin.

What changes on the printer:
- Klipper goes into the **internal "recovery" flash area**, which the
  Sindoh firmware doesn't use. Its old content is saved to your USB stick
  first.
- One line is added to the start-up script.

The Sindoh kernel and system stay installed, so you can switch back.

## You need

- A DP200 on Sindoh firmware **RODIN_200730_2** (the 2020 update).
  Other versions are untested.
- A **USB stick**, FAT32, with **at least 400 MB free**. It holds the
  installer and receives a 200 MB backup of the flash area.
- The printer on **WiFi or Ethernet**, so you can reach the web interface.
  Find its IP on the Sindoh screen before installing, or in your router.

## Install

1. Copy the release's `_update_rodin` folder to the top level of the USB
   stick. It contains:
   ```
   _update_rodin/unmistakable_klipper_install.she
   _update_rodin/dp200_klipper_payload.tar.gz
   _update_rodin/dp200_klipper_payload.tar.gz.md5
   ```
2. Switch the printer on and wait for the Sindoh home screen. Plug the stick
   into the printer's USB port.
3. The screen shows **"Klipper install"** and checks the files (about a
   minute). **Touch the screen** to start.
4. It saves the flash backup to the stick, formats the recovery area and
   unpacks Klipper. This takes 5–20 minutes. **Do not switch the printer
   off.**
5. When the screen shows **"DONE - remove stick"**, remove the stick, then
   touch the screen. The printer restarts into Klipper.
6. Open `http://<printer-ip>/` in a browser. Mainsail should show
   "Printer is ready".

**Keep the stick and the file `mtd5_recovery_backup.bin` on it.** You'll
need them to restore the flash area later.

If the screen shows **FAILED**, note the message, touch to reboot, and look at
`_update_rodin/dp200_klipper_install.log` on the stick. Nothing has been
changed if it failed before "Formatting NAND".

## First-time setup (in Mainsail)

All of these are done from Mainsail's console. Clear the bed first.

1. **Z endstop and probe offset (paper test):**
   1. home with `G28`;
   2. run `LV_PROBE_CALIBRATE`;
   3. follow the prompts with a sheet of paper under the nozzle;
   4. `ACCEPT`;
   5. `LV_PROBE_CALIBRATE_SAVE Z=<value shown>`;
   6. `SAVE_CONFIG`.
2. **Heater tuning:** run these, with `SAVE_CONFIG` after each:
   - `PID_CALIBRATE HEATER=heater_bed TARGET=60`;
   - `PID_CALIBRATE HEATER=extruder TARGET=210`.
3. **Bed mesh:** `BED_MESH_CALIBRATE`, then `SAVE_CONFIG`. A quick 4×4 mesh
   also runs automatically at the start of every print.
4. **Filament:** feed filament into the inlet, then run
   `LOAD_FILAMENT MATERIAL=PLA` (or use the touch screen).

Slicer start/end G-code:
```
PRINT_START BED=[first_layer_bed_temperature] EXTRUDER=[first_layer_temperature]
...
PRINT_END
```

## Everyday use

- **Touch screen:** after 10 minutes idle the screen goes dark; tap once to
  wake it.
- **Lamp:** `LAMP_ON`, `LAMP_OFF`, `LAMP_TOGGLE` (or `M355 S1/S0`).
- **Purge bin:** empty it when the console asks, then run `BIN_EMPTIED`.
- **Your settings** live in `printer.cfg` (Mainsail → Machine). Don't edit
  `dp200_printer.cfg` or `dp200_macros.cfg`: they are replaced on updates.

## Updating

Put a newer release's `_update_rodin` folder on a stick and plug it in. The
installer sees the existing installation and offers **UPGRADE**. Your
`printer.cfg` (calibration, mesh, PID) is kept.

## Getting back to stock

- **Back to the Sindoh firmware:** put `unmistakable_klipper_remove.she` in
  `_update_rodin/` on a stick, together with the `mtd5_recovery_backup.bin`
  (+ `.md5`) the installer saved. Plug it in and touch to confirm. It
  restores the Sindoh start-up and writes the flash backup back.
- **Full factory reflash:** put the remove script next to Sindoh's own
  RODIN_200730_2 update files in `_update_rodin/`. The remove script runs
  first, then the Sindoh update reflashes the printer as usual.

## For maintainers: building a release

On a printer running the development setup (Debian root on the SD card):

```
sh /mnt/sd/usr/src/dp200/klipper_port/install/usb/make_payload.sh /mnt/sda1/_update_rodin
sh install/usb/pack_she.sh /app/crypto_key.dat install/usb/unmistakable_klipper_install.sh /mnt/sda1/_update_rodin
```

`pack_she.sh` encrypts the installer the way Sindoh's update mechanism
expects, using the printer's own `crypto_key.dat`. The key is not part of
this repository. Whether to publish pre-packed `.she` files is an open
project decision.

Rehearse an installer without touching the flash (no screen, no reboot; it
unpacks into `/mnt/sd/dryrun_root`):

```
DRY_RUN=1 sh install/usb/unmistakable_klipper_install.sh /mnt/sd/payload
```

Details: [usb_installer.md](usb_installer.md),
[internal_firmware_plan.md](internal_firmware_plan.md),
[touchscreen_options.md](touchscreen_options.md),
[sd_boot_plan.md](sd_boot_plan.md), [kernel_research.md](kernel_research.md).
