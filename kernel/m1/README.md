# Milestone 1: mainline kernel RAM boot (Linux 6.18.59)

This builds `m1.uimg`, a mainline Linux 6.18.59 image for the DP200's
Marvell 88PA6170 (see `docs/no_gpl_plan.md`, section 2.4). U-Boot runs it
from RAM with `bootm`. Nothing is written to NAND or the U-Boot
environment.

The kernel version is 6.18, the newest 6.x longterm release on 2026-10-28.
The user asked for "6.2", but 6.2 reached end of life in 2023, and nothing
on this SoC needs that exact version.

## What it contains

| Part | Where | Notes |
|---|---|---|
| Timer driver | `src/drivers/clocksource/timer-mv61x0.c` | New. Timer 1 is the clockevent (SPI 21), timer 2 the free-running clocksource and sched_clock, at 1 MHz (prescaler 198). Register sequences copied from the vendor 3.2 kernel. All four timer IRQs are acknowledged, as the vendor does. Clocksource reads are filtered: two back-to-back reads must agree within 1 ms, and rejected reads are counted in `/sys/module/timer_mv61x0/parameters/`. A restart handler replays U-Boot's `reset_cpu` (watchdog on timer 0). At boot the driver logs what U-Boot left in the timer block and the measured count direction. |
| SoC entry | `src/arch/arm/mach-mv61x0/` | `ARCH_MV61X0` selects GIC, `CPU_PJ4B` and the timer. The DT machine is "Marvell 88PA61x0". |
| CPU setup | `patches/0001-*.patch` (proc-v7.S) | A PJ4B-MP entry (MIDR 0x560f5840/0xff0ffff0) with the vendor's `__v7_pj4bmp_setup` register values, including the A9-style SMP/FW bits in ACTLR. Mainline's `__v7_pj4b_setup` targets Armada XP and sets different bits. |
| Kconfig/Makefile hooks | `patches/0001-*.patch` | arch/arm Kconfig + Makefile, clocksource Kconfig + Makefile, dts Makefile. |
| Device tree | `src/arch/arm/boot/dts/marvell/88pa6170-dp200.dts` | CPU, A9-style SCU/GIC, the timer, UART0 as `ns16550a` (25 MHz, shift 2, 32-bit), 512 MB of RAM, and the boot-logo framebuffer at 0x18000000 reserved. |
| Config | `m1.config` | Merged over `make tinyconfig`. UP-capable SMP kernel (`maxcpus=1`), periodic 100 Hz tick, no network/block/modules, XZ zImage, DEBUG_LL + DEBUG_UNCOMPRESS on UART0. |
| Userspace | `busybox.config`, `initramfs/init` | Static BusyBox 1.38.0 on musl 1.2.6 (armhf, Thumb-2), built into the kernel. `/init` prints the milestone checks, then loops a shell on ttyS0. |

## Building

The build runs in WSL (Debian 13; WSL1 is fine):

```bash
wsl -d Debian -- bash /mnt/d/DP200/backup/klipper_port/kernel/m1/build.sh
```

One-time packages (`apt-get install`, as root):
`build-essential gcc-arm-linux-gnueabihf bc flex bison xz-utils u-boot-tools cpio python3 rsync`.

Source tarballs are read from `D:\DP200\kernel\src` and checked against
their published SHA-256 sums. Trees and build directories go to
`~/dp200` inside WSL: the kernel tree needs a case-sensitive file system,
and WSL's own disk is faster than `/mnt/d`. The outputs land in
`D:\DP200\kernel\out`:

| File | Use |
|---|---|
| `m1.uimg` | Legacy uImage for `bootm` (load = entry = 0x8000, compression none) |
| `m1-zImage-dtb.bin` | The same payload without the 64-byte header |
| `m1-vmlinux`, `m1-System.map` | For decoding oops addresses (`arm-linux-gnueabihf-addr2line -e m1-vmlinux <pc>`); KALLSYMS is off to save space |
| `m1-full.config`, `m1.dtb`, `m1-info.txt` | Full config, the DTB, sizes and md5 |

## Booting (U-Boot 2011.09, RAM only)

1. Put `m1.uimg` in RAM at 0x02000000 (serial `mw.l` uploader, or TFTP over the USB gadget).
2. Optionally check it with `iminfo 0x02000000` (header and data CRC).
3. Run `bootm 0x02000000`.

`bootm` copies the payload to 0x8000 and enters with r1 = 10000 and
r2 = ATAGs at 0x100. The zImage takes the memory size from ATAG_MEM and
merges U-Boot's `bootargs` into the DTB. U-Boot's bootargs are *appended*
to the DT bootargs (`ARM_ATAG_DTB_COMPAT_CMDLINE_EXTEND`), so the stock
bootargs are harmless: `root=` is ignored because the initramfs has `/init`.
To try options without rebuilding, use `setenv bootargs <extra args>`
(never `saveenv`). Later values win, for example `maxcpus=2`.

DT bootargs:
`console=ttyS0,115200n8 earlycon=uart8250,mmio32,0xf8060000 maxcpus=1 rdinit=/init panic=10`

`reboot` and a panic (after 10 s) reset the SoC through the watchdog,
back to U-Boot and the stock firmware.

## Boot history

| Image (md5) | Result |
|---|---|
| 870017 B, `86595c02…` (2026-10-29) | Boots to the shell. Earlycon, DT, GIC, clocksource and UART work (log: `docs/kernel/m1_boot1.log`). **Timekeeping broken:** uptime jumps by 2^32 µs, `sleep` returns at once, timer 1 interrupts stop after ~0.5 s, and timer 2's status bit stays pending. |
| 771801 B, `c073d1ea…` | Fix attempt. Status bits are cleared after timer 2 starts; IRQs 52/54/55 are taken and acked like the vendor's; clocksource reads are filtered and counted; restart handler; `panic=10`; config trimmed (VT, input, HID, STRICT_KERNEL_RWX off). `/init` now prints a sleep-2 check: timer 2 µs against uptime, the glitch counters, and timer status. |

## Expected output, and what a hang means

| You see | Means |
|---|---|
| `Uncompressing Linux... done, booting the kernel.` | uImage OK, decompressor and DEBUG_LL output work |
| nothing after that | early kernel: CPU setup, MMU or DT problem (DEBUG_LL prints fatal early errors) |
| `Booting Linux on physical CPU 0x0` ... `Machine model: Sindoh DP200` | earlycon works, DT accepted |
| `mv61x0-timer: wdt ... ctrl ... prescale 198` then `timer 2 counts up (...), 1000000 Hz` | timer block reachable; direction confirmed |
| hang at `Calibrating delay loop...` | timer 1 interrupts do not arrive (GIC/IRQ number/trigger type) |
| `printk: console [ttyS0] enabled` then silence | the 8250 driver took over and broke the UART (it is a DesignWare UART: try `snps,dw-apb-uart` + `SERIAL_8250_DW`) |
| `=== DP200 milestone 1` and a `#` prompt | milestone 1 reached; `/init` printed the clocksource, the clockevent and `/proc/interrupts` twice |

Milestone-1 checks (no_gpl_plan 2.4): earlycon output; `mv61x0_timer2` as
the clocksource; the `mv61x0_timer1` count in `/proc/interrupts` grows by
about 100 per second; typing works at the shell (UART RX interrupt).
`devmem` is included for register reads from the shell.

The BusyBox binary was not run on the PC: qemu-user cannot map a 32-bit
guest under WSL1. Its ELF attributes were checked instead (ARMv7-A,
Thumb-2, VFPv3-D16, hard-float, static), and it worked on the first boot.

The kernel never touches GPIOs, heaters, motors or NAND. Power-cycling
the printer returns it to the stock firmware.
