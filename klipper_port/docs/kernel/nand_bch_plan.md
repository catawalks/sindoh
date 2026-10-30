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

## Next step (a separate change, for review)

A variant of marvell_nand for this controller (an `mv61x0` caps entry):
- BCH 4-bit / 2 KiB pages with the stock layout;
- 3-word commands only: no LEN_OVRD, no NDCB3 through NDCB0, and a single monolithic read of 2048 + 32 + 30 bytes with BCH enabled, as the vendor reads;
- the read-only guard extended to every word written to NDCB0.

Then the md5s compare directly against `nanddump`. Reading the vendor's BBT (read-only) needs custom descriptors and is optional, since mtd0/mtd3 have no bad blocks.
