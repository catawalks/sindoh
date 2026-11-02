To use this script:

1. Format flash drive as FAT32
2. Create folder on root of flash drive titled `_update_rodin`
3. Paste `unmistakable_Model1Fix.she` into `_update_rodin`
4. Plug flash drive into Stanley Model 1 printer and follow on screen prompts

## Reverting to a Stanley Model 1

`unmistakable_Model1Revert.she` undoes Model1Fix: it sets a converted printer's
model ID back from `3DP200Q` to the stock Stanley Model 1 ID, `ST3DP1`.

Model1Fix changes only the model ID (from `ST3DP1` or `ST3DP1Q` to `3DP200Q`)
and does not keep the old one. `ST3DP1Q` is what Sindoh's open-filament
script makes of the stock ID (it appends a `Q` to any model ID, which enables
open-filament mode with the latest firmware). Use the file you need:

| File | Sets the model ID to |
|---|---|
| `unmistakable_Model1Revert.she` | `ST3DP1`, the stock Model 1 ID |
| `unmistakable_Model1Revert_ST3DP1Q.she` | `ST3DP1Q`, the stock ID with open-filament mode |

1. Create the folder `_update_rodin` on a FAT32 flash drive
2. Put **only one** of the two files in it (the printer runs every
   `unmistakable*.she` in the folder)
3. Plug the flash drive into the printer:
   - it shows the current model ID; touch to continue
   - it reminds you it is only for a Stanley converted by Model1Fix; touch to
     set the Stanley ID
   - pull the flash drive at either prompt to cancel (nothing is changed)
   - at "Model ID set", pull the flash drive: the printer reboots
4. A printer whose ID is not `3DP200Q` is left alone

Notes:
- A genuine Sindoh DP200Q also has the ID `3DP200Q`. Do not use this on one.
- It runs Sindoh's own `karas_pinetree_util.sh --set-tli`, the same command
  Model1Fix runs, so everything Model1Fix changed goes back: the model ID, the
  time zone (US), vendor and user ID (`STANLEY`, `MODEL 1`), the Stanley boot
  logo (written to the boot-logo partition) and its boot-bar color (U-Boot
  environment: `bar_color 1`, `boot_time 17`, `lcd_type 1`), and the backup
  copy of the settings database.
- Tested on a copy of the database with a stand-in for Sindoh's tool:
  3DP200Q -> `--set-tli ST3DP1` / `ST3DP1Q`, other IDs left alone, a pulled
  flash drive cancels. Not yet run on a real converted printer.
- The source is `unmistakable_Model1Revert.sh` (and `_ST3DP1Q.sh`), packed with
  `klipper_port/install/usb/pack_she.sh`.
