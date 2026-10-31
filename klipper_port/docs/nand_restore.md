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
(docs/kernel/nand_bch_plan.md, stage 2). Use it for layout and format only,
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
