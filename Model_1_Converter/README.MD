To use this script:

1. Format flash drive as FAT32
2. Create folder on root of flash drive titled `_update_rodin`
3. Paste `unmistakable_Model1Fix.she` into `_update_rodin`
4. Plug flash drive into Stanley Model 1 printer and follow on screen prompts

## Reverting to a Stanley Model 1

`unmistakable_Model1Revert.she` undoes Model1Fix: it sets a converted printer's
model ID back from `3DP200Q` to the Stanley `ST3DP1Q`.

Model1Fix changes only the model ID (from `ST3DP1` or `ST3DP1Q` to `3DP200Q`)
and does not keep the old one, so use the file that matches your printer:

| File | Sets the model ID to |
|---|---|
| `unmistakable_Model1Revert.she` | `ST3DP1Q` (the "Q" ID; use this one unless you know your printer was an `ST3DP1`) |
| `unmistakable_Model1Revert_ST3DP1.she` | `ST3DP1` |

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
- The script changes only the `MachineTLI` row in `/app/nvram/karas.db` (like
  the first step of Sindoh's `karas_pinetree_util.sh --set-tli`). It does not
  touch the U-Boot environment.
- Tested on a copy of the database: 3DP200Q -> ST3DP1Q / ST3DP1, other IDs
  left alone, a pulled flash drive cancels.
- The source is `unmistakable_Model1Revert.sh` (and `_ST3DP1.sh`), packed with
  `klipper_port/install/usb/pack_she.sh`.
