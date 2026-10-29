# Milestone 1, first RAM boot (2026-10-29, ~06:00 UTC)

Image: /d/DP200/kernel/out/m1.uimg (linux-6.18.59, 870017 B, md5 86595c02...).
Loaded with tools/uboot_upload.py COM3 m1.uimg 2000000 (7:38, 111 KB/min,
0 retries, crc32 aab72f05), booted with tools/uboot_cmd.py --bootm 2000000.
Log: m1_boot1.log.

Worked: decompressor, earlycon, DT (reserved framebuffer), GIC, timer2 as
clocksource (detected counting up, 1 MHz), 8250 ttyS0 on IRQ 25 (hwirq 32),
initramfs BusyBox shell, UART input interrupts.

BROKEN: timekeeping. `sleep 10` returned at once (0.3 s by the PC clock);
/proc/uptime was 16806 s about 5 min after boot (~4 x 4295 s = 4 wraps of
a 32-bit 1 MHz counter). Over a later 5.2 s window timer2 and uptime agreed
(5.20 vs 5.18 s), so the rate is right and the time JUMPS.
- mv61x0_timer1 (broadcast clockevent, mode 2 periodic) took 52 interrupts
  during boot, then ~1 per second at most (52 -> 53 in 1 s); per-CPU device
  is dummy_timer.
- Registers in m1 (0xf8020000 +): 00=0000000F 04=FFFFFFFF 08=0 0c=0
  10=00000004 (status: timer2 bit pending) 14=00002710 18=00000003
  1c=counting 20=0 24=FFFFFFFF 28=00000003 2c=counting 30..3c=0/FFFFFFFF/0/0
- Same registers in stock 3.2 Linux: identical except 10=00000000 (no
  pending status); 40=0000000F 44=FFFFFFFF 48=0 4c=0. Stock /proc/interrupts:
  "53: GIC Timer 1" counting (5797 after ~1 min), 52/54/55 Timer 0/2/3 = 0.
So the timer setup matches; the interrupt handling/ack (status 0x10 /
clear 0x20) or the GIC trigger type of hwirq 53 is the suspect, and the
stuck timer2 status bit may be related.

Reset without a power cycle (from U-Boot reset_cpu @0xf9280f20, replayed
with devmem from the m1 shell; it worked):
  r0 = readl(0xf8020000) ^ 0xf; writel(r0, 0xf8020000)   (0xF -> 0x0; then reads 0xE)
  writel(0, 0xf8020008); writel(1000, 0xf8020004); writel(3, 0xf8020008)  (timer0 = WDT)
  writel((readl(0xf8020000) ^ 0xf) | 0x80000000, 0xf8020000)
=> a restart handler for m1 is easy, and with panic=10 a crash would come back
to stock by itself.
