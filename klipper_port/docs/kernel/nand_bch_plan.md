# NAND: stock ECC, and what reading it under mainline needs (2026-10-30)

## Stock ECC: BCH, 4 bits per 512 bytes, one 2 KiB chunk

The raw T48 dump (`NAND_Dump/MX30LF4G18AC@TSOP48.BIN`, 2048 + 64 bytes per page) shows, in every written page's OOB:

| OOB bytes | Contents |
|---|---|
| 0-23 | 0xff (free spare) |
| 24-31 | "programz" (a vendor marker) |
| 32-61 | 30 ECC bytes |
| 62-63 | 0xff |

That is exactly mainline marvell_nand's layout `MARVELL_LAYOUT(2048, 512, 4, 1, 1, 2048, 32, 30, 0, 0, 0)`: BCH, 4-bit strength per 512 bytes, one 2048-byte chunk, 32 spare bytes, then 30 ECC bytes.

The vendor driver (mv61x0_nand_do_cmd):
- enables it with NDECCCTRL (+0x28) = 0x21 and NDCR bit 30 (ECC_EN);
- issues every command with **three** NDCB0 writes, never four.

Its on-flash BBT descriptor is custom: pattern length 3 at OOB offset 20, version at 23, LASTBLOCK, PERCHIP, 2 bits per block. That is not mainline's marvell_nand "MVBbt0" format.

## Why mainline can't just use it

- **BCH needs `is_nfcv2`.** marvell_nand allows BCH only when `caps->is_nfcv2`, i.e. on the Armada 370 and 8K compatibles.
- **The NFCv2 data path writes a fourth NDCB0 word.** Its data operations set LEN_OVRD and write NDCB0 four times (ndcb[3] = the transfer length). On a controller with a three-word command buffer, which is what the vendor driver suggests, that fourth word would start a new command.
- **The guard wouldn't see it.** The read-only guard inspects ndcb[0] only, so the fourth word's low bytes (a length such as 16, 96, 128 or 208) would be sent as an unchecked command byte. With only the guard between the NAND and a stray PAGEPROG/ERASE2 opcode, that is not acceptable.

## What m1-nand does now (read-only bring-up)

- ECC off (raw page reads, data area contiguous as in the raw dump).
- No BBT, no bad-block markers read: NAND_SKIP_BBTSCAN and NAND_NO_BBM_QUIRK under CONFIG_MTD_RAW_NAND_READ_ONLY. The probe then needs no OOB access, which ECC "none" cannot provide on this controller (nand_bbt scan failed with -ENOTSUPP).
- **Verification:** per 128 KiB block of mtd0, each block is graded against the ECC-corrected dump and the raw T48 dump. The raw dump has 73 uncorrected bitflips in 40 of mtd0's 64 blocks, so raw reads can only fully match on clean blocks.

## Retry 3 result (2026-10-30)

On-host Hamming raw reads through mtdraw work:
- mtd3 = 8357ce02 exactly;
- mtd0: 58 of 64 blocks equal the ECC-corrected dump, and 6 differ (likely raw bitflips);
- the first page matches.

So raw reads are already good for most data. BCH is needed for exact md5s and for reading the UBI partitions reliably.

## Review: can the vendor's 3-word BCH mode be driven safely for reads?

Yes, and it needs none of mainline's NFCv2 machinery. From the vendor driver
(mv61x0_nand_cmdfunc, prepare_read_prog_cmd, mv61x0_nand_do_cmd, 3.2):

- **Read page:** NDCB0 = CMD1 0x00 | CMD2 0x30 | DBC | ADDR_CYC 5, type READ (0), with NDCB1/NDCB2 holding the column/page address, written as three words. The transfer is 2048 + 32 = 0x820 bytes with ECC on (data + spare; the 30 ECC bytes go to the engine), or 2048 + 64 = 0x840 with ECC off.
- **ECC on:** NDECCCTRL (+0x28) = 0x21 (BCH_EN plus a threshold field), and NDCR bit 30 (ECC_EN). ECC off: NDECCCTRL = 0.
- **Program:** the same build, plus TYPE_WRITE and AUTO_RS (|= 0x2200000). **Erase:** ADDR_CYC | 0x2400000 (TYPE_ERASE + AUTO_RS) | DBC | 0xd060. READID is type 3 and STATUS type 4. Every command is written as three NDCB0 words; NDCB3 is written once, directly, at probe.

That read is exactly what mainline already issues in
`marvell_nfc_hw_ecc_hmg_do_read_page()`: one three-word, type-READ, monolithic
command (it adds XTYPE and LEN_OVRD only when `is_nfcv2`). It already runs
safely on this controller as the raw path in retry 3. So the change is small
and read-only:

1. **A caps entry** `marvell_mv61x0_nfc_caps` (compatible `marvell,88pa6170-nand-controller`) with a new flag `bch_v1`: NFCv1 command handling (three words, no LEN_OVRD), but BCH allowed for exactly one layout, 2048 / 512 / 4-bit (data 2048, spare 32, ECC 30), i.e. `marvell_nfc_layouts[2]`.
2. **ECC enable:** for that layout `marvell_nfc_enable_hw_ecc()` sets NDCR_ECC_EN and NDECCCTRL_BCH_EN (as mainline already does for BCH). The vendor also writes a threshold (0x21 vs 0x01), which only affects when bitflips are reported.
3. **Read path:** `ecc->read_page`/`read_oob` and their raw variants use the Hamming helpers (`hmg_do_read_page` with the layout's spare_bytes 32 and, raw, ecc_bytes 30), not the BCH chunk helpers, which need LEN_OVRD. Bitflip accounting goes through `marvell_nfc_hw_ecc_check_bitflips()`, which already reads NDSR's error count when the algorithm is BCH.
4. **No write path:** `write_page`/`write_oob` stay unset (or `-EROFS`). The command-byte guard stays, so a 4th NDCB0 word is never written in this mode (no LEN_OVRD), and `marvell_nfc_send_cmd()` can also `WARN` and refuse if LEN_OVRD ever appears with `bch_v1`.

Test (read-only):
- **mtd0:** `dd if=/dev/mtd0` in ECC mode should equal the nanddump md5 298b7390..., with the 6 raw-differing blocks corrected (NDSR reports corrected bits).
- **mtd3:** 8357ce02.
- Then the UBI partitions can be read with ubiattach `--readonly`, only in a later step.

## Next step (a separate change, for review)

A variant of marvell_nand for this controller (an `mv61x0` caps entry):
- BCH 4-bit / 2 KiB pages with the stock layout;
- 3-word commands only: no LEN_OVRD, no NDCB3 through NDCB0, and a single monolithic read of 2048 + 32 + 30 bytes with BCH enabled, as the vendor reads;
- the read-only guard extended to every word written to NDCB0.

Then the md5s compare directly against `nanddump`. Reading the vendor's BBT (read-only) needs custom descriptors and is optional, since mtd0/mtd3 have no bad blocks.

## Write path, stage 1 and 2 (2026-10-31)

**The format the stock chain uses.** Both the 3.2 kernel and U-Boot write
every ECC page the same way:
- BCH on, the same layout as reads;
- spare bytes 0-23 left 0xff;
- the marker "programz" at spare 24-31 (mv61x0_nand_cmdfunc copies it in
  at PAGEPROG, buffer offsets 0x818/0x81c). No read path checks it, but we
  write it anyway so our pages are byte-identical to stock ones.

**The vendor BBT** is the 3.2 driver's own bbt_main_descr / bbt_mirror_descr
(not the generic nand_bbt defaults), and U-Boot has the same patterns:
- options 0x2392: 2 bits per block, LASTBLOCK, PERCHIP, VERSION, CREATE, WRITE;
- pattern "Bbt" (mirror "tbB") at OOB offset 20, version at 23;
- maxblocks 4: main in block 4095, mirror in 4094, with 4092-4093 spare.

Mainline nand_bbt reads these descriptors as they are.

**Patch 0010** (marvell_nand.c, on top of 0006):
- **The guard.** On bch_v1, every flash-changing command is decoded. Only a
  complete program (SEQIN + 5 address cycles + PAGEPROG) or erase (ERASE1 +
  3 row cycles + ERASE2) goes out, and only when its block is inside the
  write window (`/sys/module/marvell_nand/parameters/write_window`,
  "FIRST,LAST" erase blocks, default none). The window itself is limited
  to mtd6 without the last 4 blocks: mtd0-mtd5 can never be programmed or
  erased.
- **Page program** in the stock format (BCH, "programz"). Raw and OOB-only
  writes are refused.
- **The vendor BBT** is read with the vendor descriptors, without CREATE or
  WRITE: we never write it, and new bad blocks are kept in RAM. If it is not
  found, the chip is registered read-only.
- **Builds:** the normal image keeps CONFIG_MTD_RAW_NAND_READ_ONLY.
  `NANDW=1 build.sh` makes the test images (m1-debian-nandw).

**Stage 2 (read-only, m1-debian-nandw, window closed):**
- "Bad block table found at page 262080 / 262016, version 0x01".
- The one bad block is 0x1a980000 = **block 3404**. It carries the factory
  marker (00 00 in pages 0 and 1) and is in both tables (raw and ECC reads
  agree; `tools/nand_bbt_check.py`).
- Block 3497 is clean on this chip. The raw T48 dump marks 3497 instead,
  in its marker and in its own table, so **the T48 dump comes from another
  chip/board**, not this printer.
- **The stock root's UBI on mtd6:** 2245 PEBs used, 105 free (EC header only;
  VID header at 2048). The free ones near the end are 4006, 4008, 4053,
  4081, 4084.

**Stage 3 (needs the owner's OK): one test block, 4084** (a free UBI PEB):
1. save it (all pages, ECC and raw with OOB) to the card;
2. with the window closed, try an erase: it must be refused, and the block
   must stay unchanged;
3. open the window on 4084 only, and try an erase of 4083: it must be
   refused;
4. erase 4084, check it is all 0xff, program test pages, read them back with
   ECC and raw ("programz", ECC bytes present);
5. erase it again and program its saved EC header page back, so it reads
   back identical to the saved copy. That includes the ECC bytes, which
   proves our pages match the stock format;
6. close the window.
