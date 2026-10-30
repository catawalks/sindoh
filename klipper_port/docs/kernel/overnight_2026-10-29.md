# Overnight test run, 2026-10-29

Everything ran through the Ethernet fast path, read-only: no heat, no motion and
no new register writes. The printer was returned to stock after each image.

| Image | Result |
|---|---|
| m1-net (be081c20) | **Pass.** SMP (CPUs 0-1), 8782 firmware active, mlan0 up, passive scan sees the nearby networks (names not recorded). The udhcpc fix works: on eth0, the lease 10.10.0.62 is applied to the interface with a default route via 10.10.0.1. Joining Wi-Fi needs the user's credentials, so that's for the morning |
| m1-gpio | **Pass.** 8 gpiochips. sysfs reads of bank 4 lines 1 and 10 and the X endstop pad (bank 5 line 20) equal the input register bits. The Ethernet RGMII pad (bank 1 line 16) is refused ("pin function 1, read-only bank"). `out` is refused, with bank 4 dir unchanged (0x10000000) |
| m1-i2c (ff88b70c) | **No answer at 0x40** (the BU21029 touch controller), as predicted: the chip is most likely held in reset. i2c-2 is registered (DesignWare comp-type 0x44570140). Open question: the stock pin dump has bank 2 pin 3 (GPIO 67) as an output driven high and pin 2 (GPIO 66) as an input, so the reset line may be GPIO 67, not 66. Driving it needs a proposal and the user's OK |
| m1-nand (ac757f18) | **Probe failed safely.** The chip ID reads correctly (Macronix 0xc2/0xdc, 512 MiB SLC, 2 KiB pages, 64 B OOB). During the bad-block scan, the read-only guard refused NDCB0 0x004d3000: CMD1 0x00 / CMD2 0x30 is a page read, but bits 21-23 = 2 decode as TYPE_ERASE. The controller then timed out and the probe returned -110. Nothing reached the flash as a write. The guard is too strict, or the driver builds that read with an odd type: to fix in the kernel session |

## NAND unchanged: checked on stock afterwards

nanddump on stock 3.2 (read-only), compared with nand_images/ (2026-10-26):
- mtd0 "kernel" (boot table, signed U-Boot, kernel): 298b7390..., **identical**.
- mtd3 "boot-logo": 8357ce02..., which differs from the 2026-10-26 dump
  (e106bfe3...) in all 768,000 bytes of the frame. Decoded, it's the
  **"Klipper / Sindoh DP200 / custom boot logo test"** logo that the boot-logo
  tool flashed on 2026-10-27 (sindoh_boot_logo README: "a test logo was
  flashed and read back"). The 10-26 dump has the stock Sindoh logo. So it's
  an earlier, intended change, not tonight's test. m1-nand's reference md5
  for mtd3 should be 8357ce02 while the test logo is installed.

## NAND retry, 2026-10-30 (guard fixed, 85c52c4)

The Ethernet fast path stopped working at about 02:00: stock's eth0 now gets
192.168.1.164 from a DHCP server at 192.168.1.1, on another network from the
PC (10.10.0.85). So the loader's static 10.10.0.250 reaches nothing (ARP gets
no replies). It's a network-side change for the user to look at. m1-nand.uimg
(4f465ecf) went in over the serial uploader instead: 15:54, crc32 verified.

Result: the guard refused nothing. The chip ID is the same as before, then
"nand_bbt: can't scan flash and build the RAM-based BBT", and the probe failed
with -524 (ENOTSUPP). With NAND_ECC_ENGINE_TYPE_NONE this driver can't do the
OOB reads that the bad-block scan needs. Back on stock afterwards: mtd0 md5 is
298b7390 again (unchanged).

## NAND retry 2, 2026-10-30 (f0b31cc: no BBT scan, serial upload 4532b6e1)

The probe now succeeds: 7 fixed partitions (kernel, u-boot-env, bbt,
boot-logo, backup, recovery, filesystem), each with flags 0x0 (MTD_WRITEABLE
clear; the read-only lock checks out). "Block protection check failed" is
logged (Macronix block protection, harmless). But **every data read fails**:
`dd if=/dev/mtd0` gives ENOTSUPP ("No error information"), so all 64 blocks
show "diff" and mtd3 hashes as the empty md5. With NAND_ECC_ENGINE_TYPE_NONE,
marvell_nand on this NFCv1 can't run page reads at all. Next: the on-host
Hamming engine (NFCv1 has it) with raw reads, to compare against the raw T48
dump.
