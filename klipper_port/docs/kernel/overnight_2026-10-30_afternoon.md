# Kernel tests, 2026-10-30 afternoon (fast path; the user away; read-only)

## m1-full (zImage built 03:29): the proven pieces together

- SMP (CPUs 0-1), consoleblank=0 on the command line.
- **USB CDC-ACM on mainline:** the FLY-ADXL345 (Klipper firmware) on the front
  port appears as `cdc_acm 1-1:1.0: ttyACM0`.
- UPC: the 5 XENA input pads set behind the safety check, "cores held, outputs
  safe", XIRD1 0x00004000 (= stock).
- SD (mmcblk0, 1.84 GiB, not mounted), i2c-2, input event0, webcam, Wi-Fi scan.
- RTC (read-only driver): control 0x000000ff, counter stuck at 0xFFFFFFFF
  (2106-02-07): not running until the vendor setup (proposal) is approved.

## m1-ubi (9914e54): the stock root UBIFS, read-only

- `ubiattach -m 6`: attached mtd6 "filesystem" (294 MiB), ro_mode 1.
- 485 "fixable bit-flip detected" PEB messages. UBI schedules scrubbing but
  can't write (ro_mode, no MTD_WRITEABLE, and 0 "read-only: refused" from the
  guard). One read timed out once (-110, PEB 2337), then was retried.
- `mount -t ubifs -o ro ubi0:filesystem`: mounted, R/O mode, format w4/r0.
- Stock files byte-identical to the rootfs dumps: lib/libc-2.15.so, app/upc.ko,
  bin/busybox, etc/inittab.
- mtd6 ECC: 7239 corrected, 0 failed. That's many correctable flips. Stock's
  own UBI scrubs them in normal use; worth keeping in mind for NAND wear.
