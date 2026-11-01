# Step 3: back to stock from our kernel - plan (2026-11-01)

Planning only. Nothing here has been written to NAND. Each write test below
needs the owner's OK on its own.

## What Sindoh's scripts actually do (read from the files)

**/etc/system_recovery.sh** is the same in the stock root, the 2020 update and
the stock kernel's initramfs. It runs when the root is broken, from the
initramfs rcS (no /etc/profile or no /app/shiloh_pinetree_mech-debug.elf).
Its steps:
1. attach mtd5 as ubi2, mount `ubi2:recovery`, untar update.tar* to `/`;
2. wait for a key (`tinydebug keywait`);
3. mtd0: `flash_eraseall`, then `nandwrite -m` **/recovery/pa6170_karas_nand.bin**;
4. mtd3: `flash_eraseall`, then `nandwrite -p` **/recovery/boot-logo.bin**;
5. mtd6: `flash_eraseall`, `ubiformat`, attach, `ubimkvol -N filesystem -m`,
   `ubiupdatevol` nandrootfs.ubifs;
6. mount ubi0:filesystem and untar update.tar* into it.

**It cannot work on a DP200 as written.** The file names are the KARA-S
model's. This printer's mtd5 has `pa6170_rodin_nand.bin` and
`boot-logo_rodin.bin`, so step 3 stops with "Failed... Please Reboot" before
writing anything. Sindoh's manual service function `rodin_util.sh
--system-recovery` erases mtd6 first and relies on that script. On a DP200 it
would leave the printer without a root.

This is from reading the scripts only. Don't test it: the manual function
erases mtd6.

**The script that does work for the DP200** is the factory one in mtd5,
`nand_write.sh`. It uses the rodin names and writes from /data. It also
erases mtd1, mtd4 and mtd5 and runs `eFuse_program.elf`. We never run those
parts.

## What our revert does

Sindoh's sequence with the rodin names, run from our kernel, without the
dangerous parts:

| Area | Action | Source |
|---|---|---|
| mtd0 0x00000-0x3FFFF (U-Boot) | **never written** | - |
| mtd0 0x40000-0x7FFFFF (kernel) | erase blocks 2-63, write the kernel part of the image | pa6170_rodin_nand.bin from offset 0x40000 (6.6 MB) |
| mtd1 env, mtd2 bbt, mtd4 backup, mtd5 recovery | **never written** | - |
| mtd3 boot logo | left as it is by default (our system uses it the same way); optional: factory logo | boot-logo_rodin.bin |
| mtd6 root | `ubiformat` keeping erase counters, `ubimkvol filesystem -m`, `ubiupdatevol`, then untar the apps | nandrootfs.ubifs, update.tar.bz2 |

**Why the U-Boot blocks can be skipped:** the 10-26 dump of mtd0 is identical
to pa6170_rodin_nand.bin: all 0x6E0000 bytes, U-Boot block included, and the
rest is erased. Rewriting blocks 0-1 would put back what is already there.

**Version:** the recovery set is the factory firmware (the GUI says 1.2.51,
from 2017). The printer runs RODIN_200730_2. The kernel is the same build
(mtd0 is byte-identical), so a revert gives the factory apps. The owner then
runs Sindoh's normal 2020 USB update. Optional later: the revert stick also
carries the 2020 update.tar and the revert extracts it instead.

**Write order and power loss:** mtd6 first, mtd0 last.
- **Power lost during the mtd6 part:** our kernel is still in mtd0. Its
  initramfs (see below) sees the revert marker and starts again.
- **mtd0 first instead would be worse:** the stock kernel would find our root.
  It has no `/init`, so the initramfs would run system_recovery.sh, and that
  fails on the file names.
- **The mtd0 write itself:** it takes a few seconds. If power is lost then,
  U-Boot is untouched, so the serial or SD fast path can boot our kernel
  again. That is the same exposure as Sindoh's own kernel updates.

## What has to be built

1. **Guard, patch 0010 v2.**
   - **Hard-allowed blocks:** mtd0 2-63, mtd3 69-76 and mtd6 1741-4091. The
     write window still has to be opened, and must stay inside these blocks.
   - **Always refused:** U-Boot (0-1), env (64), the bbt partition (65-68),
     backup and recovery (77-1740) and the vendor BBT (4092-4095).
   - **DT:** in the NANDW images only, mtd0 and mtd3 lose `read-only`, like mtd6.
2. **Initramfs in our kernel** (busybox + mtd-utils, ~2 MB). The stock kernel
   has one too.
   - **Normal boot:** mount the root and `switch_root`.
   - **Revert or recovery:** run from RAM, because mtd6 can't be rewritten
     while it is the root.
   - **The rcS behaviour:** a broken root offers the recovery from mtd5. The
     prompt is "touch to recover", where stock waits for a key.
3. **dp200-revert.sh.** The table above:
   - checks first that every file in ubi2:recovery has the right size and md5;
   - takes its `-O` (VID header offset) from the EC header of mtd6 PEB 0;
   - shows progress on the panel;
   - has `--dry-run`, which prints every erase and write with the window
     closed.
4. **Trigger:**
   - a revert stick: a marker file in `_update_rodin/`, checked by the
     initramfs at boot;
   - a "Back to stock" button in the screen app, which sets a marker and
     reboots.

## Test sequence (each write stage needs the owner's OK)

**3a. Read-only checks (from the SD kernel):**
- attach mtd5 read-only, mount it, md5 every recovery file;
- compare mtd0 with pa6170_rodin_nand.bin;
- save raw dumps (data + OOB) of mtd0 and mtd3 to the PC as the
  byte-for-byte baseline.

Also: the PC copy `Sindoh_raw_dump/recovery/update.tar.bz2` is damaged (a
bzip2 CRC error in 5 of its 4 KB blocks, a copy error). The flash copy is
fine. Rebuilt from the 10-26 mtd5 dump it passes `bzip2 -t`; saved as
`nand_images/update.tar.bz2.from_mtd5`. Take the PC copies from the
read-only mount from now on.

**3b. Dry run.** dp200-revert.sh --dry-run on the nandw kernel, window
`none`. It has to list exactly the operations in the table.

**3c. mtd0 kernel area, same contents** (approval A).
- **Write:** erase blocks 2-63 and write back the same stock kernel.
- **Check:**
  - the corrected read equals the file;
  - raw data and OOB equal the 3a baseline byte for byte (stage 3 showed our
    ECC bytes are identical);
  - any difference stops the test before a reboot;
  - then a normal stock boot from NAND.
- **If it doesn't boot:** U-Boot is untouched. Boot our kernel from the SD
  card's gap over serial (already proven) and write the kernel again.

**3d. mtd6 full revert** (approval B).
- **Backup first:**
  - a raw nanddump of mtd6 (308 MB) to the PC;
  - a tar of the stock root's settings (`/app/nvram`, Wi-Fi config, G-codes).
- **Revert:** from the SD kernel (root on the SD card, mtd6 unused), run the
  mtd6 half of dp200-revert.sh.
- **Check:** stock boots to the touchscreen app.
- **Then:**
  - put the settings back;
  - optionally, the owner runs the 2020 USB update to return to RODIN_200730_2.
- **Fallback:** restore the nanddump through the same path.

**3e, later, with the installer.** The full sequence from our NAND
initramfs, including a power cut during the mtd6 part.

## Not covered

- Writing U-Boot or the env: never.
- Sindoh's eFuse step: never.
- The DIP-switch SD boot. It isn't needed for any of this: the fallback is
  U-Boot's serial and SD path.

## Results, 3a and 3b (2026-11-01, m1-debian-nandw from the SD card)

**Guard v2** (patch 0010):
- **Hard-allowed blocks:** mtd0 2-63, mtd3 69-76, mtd6 1741-4091.
- **NANDW device tree:** mtd0, mtd3 and mtd6 are writable at the MTD layer;
  mtd1, mtd2, mtd4 and mtd5 stay read-only.
- The write window stayed `none` through every test.

**3a, read-only checks** (`install/nand/dp200-revert.sh --check`): all pass.

| Check | Result |
|---|---|
| Recovery set in mtd5 | `install/nand/recovery.md5`, all 4 files match |
| update.tar.bz2 | bzip2 test OK: the flash copy is good |
| mtd0 | equals pa6170_rodin_nand.bin, U-Boot block included |
| mtd6 | VID header offset 2048, data offset 4096; 2355 blocks, 1 bad (3404) |
| Raw baselines (data + OOB, stock nanddump -n) | on the 4 GB card in /var/backups/: nand_raw_oob_mtd0.bin `ba163ead`, nand_raw_oob_mtd3.bin `dfcd63a1`. Two raw reads of mtd0 were identical. |

**3b, dry run** (`--dry-run --with-logo`): it prints exactly the operations
in the table above, with the window closed:
- **Root:** window 1741,4091; `ubiformat -O 2048`; `ubimkvol`;
  `ubiupdatevol`; untar the apps.
- **Logo:** window 69,76; `flash_erase` and `nandwrite -p` on mtd3.
- **Kernel:** window 2,63; `flash_erase /dev/mtd0 0x40000 62`;
  `nandwrite -s 0x40000`.

**A read bug found on the way.** The fix (patch 0010, section 9) is in both
m1-debian and m1-debian-nandw. See nand_bch_plan.md, "Early UNCERR".

**Not done yet:**
- the initramfs (needed for 3e, not for 3c/3d);
- 3c and 3d, which need the owner's OK.
