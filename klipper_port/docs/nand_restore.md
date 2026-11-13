# NAND restore images

Made 2026-10-27 from the development DP200 with `nanddump -o -b` (no OOB,
bad blocks omitted). The data is **ECC-corrected by the NAND controller**.
Kept outside git (size, vendor content) in `D:\DP200\backup\nand_images\`:

| File | Partition | Size | md5 |
|---|---|---|---|
| mtd0.bin | kernel (boot table, signed U-Boot, kernel) | 8 MiB | 298b7390ccb500998661949c02ea68f8 |
| mtd1.bin | u-boot-env | 128 KiB | fdadaa344aa2eb6304cd438906a321a0 |
| mtd3.bin | boot-logo | 1 MiB | e106bfe3be8f2e08044222c71a982c28 |
| mtd4.bin | backup (UBI, point.db) | 8 MiB | f7146c8256f658b4ecb33dee0e34e96f |
| mtd5.bin | recovery (UBI, factory files) | 200 MiB | 9a14a0cad1043419214eded3dbd7645a |
| mtd6.bin | filesystem (UBI, stock root **with our boot hook**) | 294 MiB* | 2cb7384cc99b90c6b6a56caa2f8ccbfe |

\* 5 bad blocks omitted (UBI reports 5 bad PEBs). mtd6 was read while
mounted: a snapshot of a lightly used filesystem.

Why not from the T48 dump (`NAND_Dump/MX30LF4G18AC@TSOP48.BIN`)? It's raw:
2048-byte pages + 64 OOB, so the layout is simple, but it carries the flash's
uncorrected bit errors (3 single-bit flips in the first 206 KiB against the
ECC-corrected mtd0). It is **not** this printer's chip (2026-10-31): its only factory-marked
block, and its own BBT, are block 3497 (0x1B520000). This printer's chip has
block 3404 (0x1A980000) marked instead, in the marker and in the BBT
(history/kernel/nand_bch_plan.md, stage 2). Use it for layout and format only,
never for bad blocks.

## Restoring (from the rescue card, root on SD, NAND not mounted)

Copy the needed images to the card (e.g. /restore), then:

```
# raw partitions
flash_erase /dev/mtd0 0 0 && nandwrite -p /dev/mtd0 /restore/mtd0.bin   # only if mtd0 is damaged
flash_erase /dev/mtd1 0 0 && nandwrite -p /dev/mtd1 /restore/mtd1.bin
flash_erase /dev/mtd3 0 0 && nandwrite -p /dev/mtd3 /restore/mtd3.bin
# UBI partitions: image = sequence of PEBs, ubiformat skips the target's bad blocks
ubiformat /dev/mtd4 -f /restore/mtd4.bin
ubiformat /dev/mtd5 -f /restore/mtd5.bin
ubiformat /dev/mtd6 -f /restore/mtd6.bin
```

mtd6 brings back the stock root as it was on 2026-10-27, including the
Klipper boot hook (`/etc/profile` line, `/etc/dp200-boot.sh`,
`/DEBUG_MACHINE`). For a pure stock root, run `hook_remove.sh` afterwards, or
use Sindoh's factory procedure: `Sindoh_raw_dump/recovery/nand_write.sh` with
`nandrootfs.ubifs` and `update.tar.bz2`. Don't run its `eFuse_program.elf`
step.

## Recovery boot: the stock kernel from the SD card (proven 2026-11-01)

**When:** mtd0's kernel area is broken (U-Boot then stops at its prompt
after the failed `bootm`). U-Boot itself (mtd0 blocks 0-1) and the env are
never written by our tools.

**What it does:** boots Sindoh's own kernel from RAM, with its own NAND
driver and tools. RAM only: no NAND write, no saveenv.

**The image:**
- the stock uImage (pa6170_rodin_nand.bin from 0x40000; 6928784 bytes,
  crc32 9f0bc791, md5 d6c40b8a);
- stored as the contiguous, immutable (`chattr +i`) file
  /var/backups/stock_kernel.uimg on the 4 GB card;
- raw sector 4296704, 13533 sectors.

**Steps (tools/sd_stock_boot.sh):**
1. Catch U-Boot.
2. `--pinmux-sd`.
3. `mmc read 2000000 419000 34dd`, then `crc32 2000000 69b990` must be
   9f0bc791.
4. `uboot_cmd.py --stock-bootargs`: `run setbootargs_nand` in RAM, then a
   check for `ubi.mtd=filesystem root=ubi0:filesystem rootfstype=ubifs
   mtdparts=...`.
5. `--bootm 2000000`.

**Why step 4 matters:** U-Boot's saved `bootargs` is only `console=ttyS0`.
With that, the stock initramfs can't mount the root and would fall back to
/etc/system_recovery.sh.

**Result:** "Booting kernel from Legacy Image at 02000000", Linux 3.2.0,
the stock root mounted, "Root Console".
- Stock has flash_erase, flash_eraseall, nandwrite and nanddump, so mtd0's
  kernel area can be rewritten from there, using Sindoh's driver.
- **Command:** `flash_erase /dev/mtd0 0x40000 62`, then `nandwrite -p -s
  0x40000 /dev/mtd0` with the kernel part of pa6170_rodin_nand.bin.

**Requirement:** this needs a stock root in mtd6. Once our root is
installed, the same boot path loads our kernel from the SD card instead
(tools/sd_raw_boot.sh).
