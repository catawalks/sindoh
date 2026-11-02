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

## Stage 3: the first writes (2026-10-31, the owner approved block 4084)

Test image m1-debian-nandw: patch 0010, plus the "filesystem" partition
without `read-only` (debian.dts with -DDP200_NANDW; mtd0-mtd5 stay
read-only in the device tree as well). `tools/nand_write_test.py 4084`, on
a free UBI PEB of the stock root (EC header only):

| Step | Result |
|---|---|
| Save the block (ECC data, raw data, raw OOB per page) | /var/backups/nand_block4084.bin on the card |
| Window closed, erase 4084 | refused at the hardware ("refused NDCB0 0x004bd060 NDCB1 0x0003fd00"), block unchanged |
| Window 4084,4084, erase 4083 | refused (NDCB1 0x0003fcc0 = block 4083), unchanged |
| Erase 4084 | reads 0xff (ECC, raw, OOB) |
| Program pages 0, 1, 31, 63 | ECC read equal, 0 raw bitflips, OOB: 0xff x24, "programz", 30 ECC bytes |
| Erase, program the saved EC header page back | **identical to the stock-written page, ECC bytes included**: our BCH output equals the vendor driver's |
| `--verify` | block 4084 equals the saved copy; window none |

Two controller details found on the way, now in patch 0010:
- **AUTO_RS (NDCB0 bit 25) on page programs**, as the vendor sets it
  (prepare_read_prog_cmd |= 0x2200000).
- **No STATUS command after a program.** The program itself ends with CMDD
  after ~7.6 ms (NDSR 0x1d00). A separate STATUS command (mainline's
  nand_status_op) is then never answered, which is what timed out
  ("Timeout on CMDD"). With AUTO_RS the controller has already read the
  status: a failed program sets BBD (NDSR bit 6). So bch_v1 waits for
  CMDD/BBD (200 ms, the vendor's timeout) and stops there.

Other notes:
- The raw OOB read fills 62 bytes (32 spare + 30 ECC). Bytes 62-63 are
  whatever the buffer held, so comparisons stop at 61.
- A refused command leaves the controller waiting for command words. The
  next command recovers it ("Timeout on CMDD" once, then normal).
- `kernel/m1/tools/regen_0010.sh` rebuilds patch 0010 from
  `tools/nandw_edit.py` (vanilla + 0006 + the edits).
- **Not yet tested:** UBI/UBIFS writing through this path (many pages,
  erase counters, wear leveling), and the first write of a whole partition.
  Both come before an installer.

## Step 2: UBI + UBIFS writes on the stock root (2026-10-31, the owner approved)

`tools/ubi_write_test.sh` on m1-debian-nandw: window 1741-4091 (all of mtd6
except the BBT blocks), attach mtd6 read-write as ubi1, mount
ubi1:filesystem, write a 16 MB random file, sync, unmount, remount, check
the md5, delete the file, unmount, detach.

**Run 1:** UBI tried to erase PEB 2351 = chip block 4092, a spare BBT block.
The guard refused it, and UBI went read-only. Nothing was written. Cause: the
vendor kernel reserves the whole BBT area (blocks 4092-4095, as its
descriptor has NAND_BBT_WRITE), so stock UBI counts 5 bad PEBs. Mainline's
nand_bbt without NAND_BBT_WRITE reserves only the 2 blocks that hold a
table. Fix (patch 0010): after the scan, all 4 are reserved in the in-RAM
BBT (nothing written). Then 3404 and 4092-4095 read as bad, 5 bad PEBs as on
stock.

**Run 2:** the test itself passed. Attached with 2350 PEBs and 5 bad,
mounted read-write, 16 MB written, md5 equal after the remount, deleted
(free space back to 53772 KB from 53780 KB), detached. But while attached,
UBI logged 312 "fixable bit-flip" reports and scrubbed 189 PEBs, some
back and forth (LEB 0:917 between PEB 232 and 1706). The window was closed
by hand, UBI went read-only, and UBIFS logged one EROFS write at unmount.
Cause: mainline's BCH bitflip count is NDSR ERRCNT (bits 16-20) on
CORERR. On this controller that field reads 16 even when idle, which is
above UBI's scrub threshold (12 for strength 16). Fix (patch 0010): bch_v1
counts the corrected bits itself, as the difference between its raw read
and the BCH read (data + spare).

**The stock root after it:**
- the 3.2 kernel attached mtd6 with 5 bad PEBs and 0 corrupted;
- UBIFS "recovery needed / recovery completed" (the unclean unmount), mounted;
- every file read back: 2974 of 2975, the 1 being /app/nvram/PJL, a temp
  file the stock app deleted during the check;
- no UBI/UBIFS errors.

The UBI moves are CRC-checked, and they kept the data intact.

**Next:** rerun with the bitflip fix. The test now has a watchdog that closes
the window after more than 20 scrubs.

**Run 3 (with the bitflip fix):**
- Attached with 2350 PEBs and 5 bad.
- 16 MB written; md5 equal after the remount; deleted; free 53972 KB after.
- **0 scrubs, 0 "fixable bit-flip" reports** (the watchdog had nothing to do).
- On the 3.2 kernel afterwards: mounted with no recovery needed (our
  kernel unmounted cleanly). 5 bad PEBs, 0 corrupted, no UBI/UBIFS errors.
  Every file read (the one miss is the same temp file, /app/nvram/PJL).

**So the mainline write path works for UBI/UBIFS on the stock root**, and
the stock kernel reads what it wrote. The card's boot slot holds the normal
read-only m1-debian again (with the bitflip fix).

## Early UNCERR on pages with bitflips (2026-11-01)

**Symptom.** Attaching mtd5 logged ~90 "BCH read failed (-74)" messages,
and UBI retried each one. Full page-by-page passes of mtd5 (102,400 pages)
gave ~100-125 errors per pass, on different pages each time.

**Measured:**

| Test | Our kernel, before the fix | Stock 3.2 (same reads, via the SD chroot) |
|---|---|---|
| Page with 1 bitflip, read 1000 times | ~5.5% fail | 1000/1000 OK |
| Same page, back to back | 16% of reads returned the **uncorrected data** through /dev/mtd5, with no error to the reader (mtdchar passes the data on -EBADMSG) | |
| Clean pages | never fail | |
| Full pass of mtd5 | ~100 errors | 0 errors (36 s) |

So the flash is fine and our driver was wrong.

**Cause.** On pages that need correction, the 88PA6170 sometimes raises
UNCERR without RDDREQ, and RDDREQ never follows. A fresh read of the page
works.
- **Waiting longer for RDDREQ doesn't help:** it times out. A diagnostic
  build only looked fixed because the timeout went through the old
  timeout retry.
- **NDECCCTRL makes no difference:** the vendor's 0x21 behaves the same as
  mainline's 0x01.

**Fix (patch 0010 section 9).**
- An UNCERR or a timeout repeats the BCH read, up to 4 tries.
- A really uncorrectable page fails all 4 tries and is still reported.
- Counters: /sys/module/marvell_nand/parameters/early_uncerr and
  reread_ok.

**After the fix:**
- 6000 back-to-back reads: all correct;
- 3 full passes of mtd5: 0 errors (~990 early UNCERRs, all recovered);
- 0 UBI retries.

**Still open, speed only:**
- Our passes take 70-86 s, stock's 36 s.
- About 300 reads per pass end in a timeout (no RDDREQ and no UNCERR), and
  the retry recovers them. Each one waits POLL_TIMEOUT.
- Likely related to the raw-then-BCH double read, which the vendor driver
  doesn't do.

**Tools:**
- tools/bulkread.py: page-by-page passes;
- tools/pagetest.sh: repeated nanddump of a page;
- tools/nand_hammer.py: back-to-back reads of one page, md5s counted.

## Read path rework, part 1 (2026-11-01, measurements, nothing written)

**Vendor 3.2 driver (disassembled mv61x0_nand_irq):**
- UNCERR counts only when it comes with RDDREQ. Earlier status bits are
  written back to NDSR (acknowledged).
- Reads are 0x820 bytes with ECC on and 0x840 raw.

**Our raw OOB bytes 62-63:** the FIFO delivered all 64 bytes, but we
copied only 62. Fixed: raw reads keep all 64 (patch 0010 section 10).

**Switches** (tools/bch_v1_read.c, m1-debian-nandw fc02567d). All four
runs read correctly: mtd0, mtd3 and mtd5 matched the stock dumps' md5s,
with 0 failures.

| read_mode / ack_early | mtd5 pass | Timeouts | Early UNCERR | Note |
|---|---|---|---|---|
| 0 (raw, then BCH) / N | 54 s | 72 | 72 | |
| 0 / Y | 51 s | 156 | 156 | acknowledging doesn't bring data: an UNCERR without RDDREQ is an abandoned command |
| 1 (BCH first) / N | 191 s | 1 | 1013 | every erased page (26209) ends with UNCERR after its data |
| 1 / Y | 99 s | 763 | 1008 | |

**Stock's controller state is different** (devmem, idle):

| Register | Ours | Stock |
|---|---|---|
| NDCR | 0x81079fff | 0xC184DFFF |
| NDECCCTRL | 0 | 0xF21 |
| NDSR (idle) | 0x1c02, RDDREQ still set | 0 |

- **NDCR:** stock also sets bit 14 (64 pages per block) and bit 23
  (SEQ_DIS in the PXA3xx driver), and has RD_ID_CNT 4 where ours is 7.
- **NDECCCTRL:** 0xF21 is BCH_EN, threshold 16, and 30 in bits 7-14 (our
  ECC byte count).
- **Next test:** these values, as the `eccctrl` and `ndcr_set` switches
  (build e19c8f39, not run yet).

## Stock kernel write failure on mtd6 (2026-11-01, stock 3.2 from NAND)

During a normal stock boot, Sindoh's driver logged `UBI error: ubi_io_write:
error -5 while writing 2048 bytes to PEB 541:88064`. UBI started moving the
block to PEB 51, then switched to read-only, and UBIFS went read-only too.
After that, lookups under /usr failed with EINVAL (wget, md5sum and head
"not found"). That also explains today's failed SD installs from stock.

**State:**
- **PEB 541** (chip block 2282): pages 0-42 are written in the normal stock
  format, and page 43 (the failed write) onward is erased.
- **PEB 51:** only its EC header page was written; the move never finished.
- Nothing from pages 0-42 was lost.

**Our kernel's role:** it wrote nothing to mtd6 today (window 69,76 only,
for mtd3) and never attached it. Whether a state left by our kernel before
`reboot -f` played any part isn't known.

**Evidence on the 4 GB card**, /var/backups:
- dmesg_stock_ubi_write_error_20261101.txt;
- mtd6_peb541_raw_20261101.bin, mtd6_peb51_raw_20261101.bin (Debian
  nanddump -n -o run on the stock kernel; its OOB layout is shifted by 4
  bytes).

## Read path rework, part 2 (2026-11-01, read-only; md5s against the stock dumps)

**Vendor driver, disassembled:**
- writes NDECCCTRL = 0x21 per command (the 0xF00 that reads back is status);
- builds NDCR from a probe-time value with bits 14 and 23 set;
- reads 0x820 bytes with ECC and 0x840 raw.

The labelled disassembly (private, derived from the vendor image) is in
D:\DP200\backup\vendor_disasm\mv61x0_nand_3.2.S.

**Results:**

| Build / setting | Raw, then BCH | BCH first | Note |
|---|---|---|---|
| fc02567d, bits off | OK, 72 timeouts | OK, 1013 early UNCERR | |
| bits 14+23 set in reset (37214ad3) | **wrong data** | **wrong data** | bit 14 changes how our page addresses are taken |
| NDCR rewritten at each read start (dfb0bf2a) | **wrong data** | OK | stale FIFO bytes ("ramz") at the start of the data |
| 411725bf, bits off, drain 0 | OK, 48 timeouts | | RDDREQ is set after **every** BCH read (86799/86799) |
| drain 1 (read the extra bytes) | **wrong data** | | 15170 failures: the extra bytes aren't this page's |
| bit 23 (SEQ_DIS) poked once while idle | OK, 103 timeouts | OK, 1843 early UNCERR | no improvement; RDDREQ still set after every read |

So:
- **The NDCR fix is ruled out:** stock's bits alone don't fix anything, and
  bit 14 breaks addressing.
- **Never rewrite NDCR mid-sequence:** it corrupts the next read.
- **The stalls aren't explained yet:** early UNCERR and timeouts remain in
  every setting. The best order is still raw first, then BCH (0 failures,
  correct data, ~50 s per mtd5 pass against stock's 36 s).
- **Open question:** how the vendor's interrupt-driven command sequence
  ends each read, against our polled one.

**Monitoring:**
- tools/klog.sh (`mark` / `check`) runs before and after every test.
- Tool downloads are size-checked: an empty klog.sh once went unnoticed.

## Read path rework, part 3 (2026-11-01): the vendor's order, and a tool artifact

**The 4-byte shift was caused by our own tool.** tools/nfcregs.py dumped
registers 0x00-0x7c, including +0x40 (NDDB, the data FIFO). Each dump
took one word out of the FIFO, so every later page read started with the
previous read's last 4 bytes ("ramz" / 0xff). It persisted until the next
dump.

That invalidates part 2's conclusions that "NDCR bits 14/23 break
addressing", "an NDCR rewrite breaks reads", "the NDSR pre-clear breaks
reads" and "draining corrupts". Those were second runs started in the
shifted state, after the read test's closing register dump. It is also
what made UBI report "layout volume not found". nfcregs.py now never reads
NDDB.

**Final read path** (patch 0010, tools/bch_v1_read.c):
- **one BCH read per page** (2080 bytes, like the vendor);
- **UNCERR counts only with the data**; an UNCERR before RDDREQ means read
  again;
- **erased page:** UNCERR after the data with data and spare all 0xff (no
  raw read needed);
- **CORERR:** read the page raw to count the corrected bits, and reject
  more than 4 per step;
- **every command starts from a stopped controller** (NDSR cleared, ND_RUN
  off), as the vendor's does;
- **at shutdown/reboot** the controller is left idle and clean.

**Validation** on the read-only kernel m1-debian (519243ae), two rounds:

| Check | Result |
|---|---|
| mtd0 / mtd3 / mtd5 md5s against the stock dumps | equal |
| mtd5 pass | 31-37 s (stock 36 s) |
| 6000 random reads with pauses (tools/nand_gapcheck.py, against nand_images/mtd0.bin) | 0 wrong |
| UBI headers of all 2355 mtd6 blocks, read twice | identical |
| Read-only UBI attach + UBIFS mount of the stock root, every file read | 2974 files, 1 error: /app/nvram/PJL, a special file that also fails on stock |
| Failures | 0 |

**Still open:**
- "Timeout on CMDD" in the raw re-read after CORERR: ~160 in round 1 and 2
  in round 2, each 100 ms, and the data is still correct. Next: test
  whether NDSR ERRCNT at RDDREQ gives the corrected-bit count (the
  "ERRCNT reads 16 idle" finding may predate the clean measurements). That
  would drop the raw re-read, as the vendor never does one.
- The UBI write test (mtd6) still has to be re-run with this read path.

## Read path rework, part 4 (2026-11-01): ERRCNT, no raw re-reads, write test

**ERRCNT is the corrected-bit count when read after CMDD.** On 5535 of
5543 corrected pages it equalled the count from a raw re-read. Most of
the other 8 were flips in the ECC bytes: ERRCNT sees those, while
raw-against-corrected can't. At RDDREQ it reads 0, and idle it reads 16:
only use it after CMDD.

So corrected pages no longer get a raw re-read; the vendor driver never
does one either. A raw read now happens only for an UNCERR that comes with
the data, to tell an erased page from a failed one. An UNCERR before the
data is simply read again.

**Validation**, read-only kernel m1-debian 5df089a9, two rounds:
- md5s equal to the stock dumps; 6000 random reads with pauses: 0 wrong;
- UBI headers identical twice; read-only UBIFS mount with all 2974 files
  read (only /app/nvram/PJL, a special file, fails, as on stock);
- mtd5 pass 31 s (stock 36 s);
- **0 retries, 0 timeouts, 0 early UNCERR, 0 failures** in ~225000 reads.
  The early UNCERRs and CMDD timeouts were side effects of the raw
  re-read.

**UBI write test re-run** (step 2, owner-approved), m1-debian-nandw
f370f49e:
- 16 MB written through UBI/UBIFS on the stock root; md5 equal after a
  remount; deleted;
- 0 scrubs, 0 bitflip reports; driver counters with 0 retries, timeouts
  or failures; window back to none.

**Stock 3.2 afterwards:**
- 5 bad PEBs, 0 corrupted;
- UBIFS mounted without recovery;
- 2974 files read (only PJL fails, as always); root rw; kernel log clean.

UBI's "cannot reserve enough PEBs for bad PEB handling, reserved 23, need
75" comes from stock's own layout: mainline asks for 20 per 1024 PEBs.
