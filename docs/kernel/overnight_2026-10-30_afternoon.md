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

## The three proposals, the user approved them ("Ok to all"), run on m1-full

- **Touch reset (touch-pins.sh):** bank 2 out/dir bit 3 = 1 (GPIO 67 high),
  sel3 = 0x300, sel2 = 0x320 (stock values). `i2cdetect -y -r 2 0x40 0x40`
  -> **40**: the BU21029 answers. No command bytes sent yet.
- **RTC setup:** step 1's mask, found by comparing 0xf8000200: stock 0x80000080,
  U-Boot/mainline 0xC0000080, so the mask is **bit 30 (0x40000000)**. Then
  +0x20 = 3, +0x1c = 0 (500 ms), +0x04/0x10/0x08/0x14 = 0, +0x00 = 3. After
  that, control reads 0xFC (= stock) and the counter moves, but its reads look
  wrong: 0x6A18C8FF -> 0x6A18CBFF in 3 s (low byte always FF, +0x300). Stock
  reads a clean 32-bit seconds count (0x6AE51847 = 2026-10-30, +2 in 2 s, and it
  kept the date over reboots). To investigate: access width or bus timing.
- **UPC output pads (upc-pinmux.sh all):** 36 pad selects set to the stock
  values (banks 4, 5, 6), with the safety check passing before and after (cores
  held, PWM run/level 0, stepper drivers off). **XIRD = 0x3C040000 = stock**,
  XIRD1 0x00004000. Reboot logged "cores held, outputs off".
