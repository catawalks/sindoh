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
| SoC entry | `src/arch/arm/mach-mv61x0/` | `ARCH_MV61X0` selects GIC, `CPU_PJ4B`, the SIC and the timer. The DT machine is "Marvell 88PA61x0". `platsmp.c` starts CPU 1 the vendor's way: SCU enable, `secondary_startup` to the mailbox at 0xfa000000, then an SGI (`enable-method = "marvell,88pa6170-smp"`). |
| SIC irqchips | `src/drivers/irqchip/irq-mv61x0-sic.c`, `patches/0002-*.patch` | SIC0 (0xf9300100, SPI 101) and SIC1 (0xf9300200, SPI 103), 32 inputs each, chained. Registers from the vendor: +0 enable-set, +0xc clear, +0x14 enable-clear, +0x18 status. No users yet; the DEC timers are SIC0 inputs 0-7. |
| Ethernet | DTS `ethernet@f9050000`, `m1.config` | stmmac (`dwmac-generic`) on the Synopsys GMAC (SPI 64). MDIO clock range CR=0 (`clk_csr`, as the vendor). The 88E1510 at MDIO address 0 uses phylib's generic driver, so its strap RGMII delays stay as the vendor has them. GPIO 62 (bank B bit 30) is the PHY reset the vendor releases at boot; this kernel does not touch it. `/init` sets eth0 to 10.10.0.250/24. |
| USB host | `src/drivers/phy/marvell/phy-mv61x0-usb.c`, `patches/0003-*.patch`, DTS | `generic-ehci` on the ChipIdea host (0xf9041100, SPI 66) and OTG (0xf9048100, SPI 67) controllers, with a transaction translator (ChipIdea host-mode reset). The PHY driver replays the vendor's `usb_phy_init` (PLL at 0xf904f004, PHYs at 0xf904f040/80/c0). Enumeration only: no storage, serial, net or video class drivers. |
| Wi-Fi | `patches/0004-mwifiex-usb-add-88w8782.patch`, `m1.config`, `build.sh` | mwifiex patched for the 88W8782 (1286:2040): one product ID, and the firmware starts in place without re-enumerating. cfg80211 with the world regulatory domain only (no signed regdb, no crypto). The firmware `mrvl/usb8782_uapsta.bin` is copied from the local stock dump into the initramfs (md5 checked). **It is a Marvell binary: never commit it, and don't publish built images.** Static `iw` 6.17 on libnl 3.12. Details: `docs/kernel/wifi_88w8782.md`. |
| Webcam | `m1.config`, `tools/uvcgrab.c` | UVC driver for the 0c45:6341 camera; `uvcgrab` saves one MJPEG frame. |
| Panel console | DTS `/chosen/framebuffer@18000000`, `m1.config` | `simple-framebuffer` on the boot-logo buffer U-Boot left running: 800×480 RGB565, stride 1600. fbcon shows the kernel console there (`console=tty0`). Display only: no touch, no backlight control. The panel is mounted in portrait; append `fbcon=rotate:1` (or 3) to turn the text. |
| CPU setup | `patches/0001-*.patch` (proc-v7.S) | A PJ4B-MP entry (MIDR 0x560f5840/0xff0ffff0) with the vendor's `__v7_pj4bmp_setup` register values, including the A9-style SMP/FW bits in ACTLR. Mainline's `__v7_pj4b_setup` targets Armada XP and sets different bits. |
| Kconfig/Makefile hooks | `patches/0001-*.patch` | arch/arm Kconfig + Makefile, clocksource Kconfig + Makefile, dts Makefile. |
| Device tree | `src/arch/arm/boot/dts/marvell/88pa6170-dp200.dts` | CPU, A9-style SCU/GIC, the timer, UART0 as `ns16550a` (25 MHz, shift 2, 32-bit), 512 MB of RAM, and the boot-logo framebuffer at 0x18000000 reserved. |
| Config | `m1.config` | Merged over `make tinyconfig`. UP-capable SMP kernel (`maxcpus=1`), periodic 100 Hz tick, no network/block/modules, XZ zImage, DEBUG_LL + DEBUG_UNCOMPRESS on UART0. |
| Userspace | `busybox.config`, `initramfs/init`, `initramfs/m1-checks.sh` | Static BusyBox 1.38.0 on musl 1.2.6 (armhf, Thumb-2), built into the kernel. `/init` runs `/etc/m1-checks.sh` as a child, then loops a shell on ttyS0. |

## Building

The build runs in WSL (Debian 13; WSL1 is fine):

```bash
wsl -d Debian -- bash /mnt/d/DP200/backup/klipper_port/kernel/m1/build.sh
```

Each test step is its own image variant (see the test cards below):

```bash
wsl -d Debian -- bash -c "VARIANT=upc bash /mnt/d/DP200/backup/klipper_port/kernel/m1/build.sh"
```

| VARIANT | Output | Adds on top of the base image |
|---|---|---|
| `base` (default) | `m1.uimg` | Milestone 1 + SMP, panel, USB, Wi-Fi scan, webcam |
| `net` | `m1-net.uimg` | Uniprocessor loader: `wifi-join` (wpa_supplicant, udhcpc) and `netload` (kexec-tools) |
| `upc` | `m1-upc.uimg` | `/dev/upc0`, `/dev/upc1` (`src/drivers/misc/mv61x0-upc.c`), PTYs, `upctool` |
| `sd` | `m1-sd.uimg` | SD socket (`sdhci-mv61x0.c`), block layer, ext4/vfat, read-only use |
| `gpio` | `m1-gpio.uimg` | GPIO banks A-H (`gpio-mv61x0.c`) registered, debugfs |

A variant merges `variants/<v>.config` after `m1.config`, uses
`variants/<v>.dts` (the base DTS plus `status = "okay"` for its nodes;
every new node is `disabled` in the base DTS), and adds `initramfs/<v>/`.
`/init` runs that variant's `variant.sh` checks after the common ones.

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
`console=tty0 console=ttyS0,115200n8 earlycon=uart8250,mmio32,0xf8060000 rdinit=/init panic=10`

If the second CPU causes trouble, boot the same image with
`setenv bootargs maxcpus=1`; the appended value keeps CPU 1 parked.

`reboot` and a panic (after 10 s) reset the SoC through the watchdog,
back to U-Boot and the stock firmware.

## Boot history

| Image (md5) | Result |
|---|---|
| 870017 B, `86595c02…` (2026-10-29) | Boots to the shell. Earlycon, DT, GIC, clocksource and UART work (log: `docs/kernel/m1_boot1.log`). **Timekeeping broken:** uptime jumps by 2^32 µs, `sleep` returns at once, timer 1 interrupts stop after ~0.5 s, and timer 2's status bit stays pending. |
| 771801 B, `c073d1ea…` | Status bits are cleared after timer 2 starts; IRQs 52/54/55 are taken and acked like the vendor's; clocksource reads are filtered and counted; restart handler; `panic=10`; config trimmed (VT, input, HID, STRICT_KERNEL_RWX off). **Boot 2 (`m1_boot2.log`):** timer probe status 0; the restart handler works (panic → reset → stock). `/init` died with exit 2 at 0.40 s because BusyBox lacked `$(( ))` (`FEATURE_SH_MATH` off). Linux IRQ 24 is now timer 0; timer 1 is IRQ 27. |
| 773633 B, `d583f22f…` | `FEATURE_SH_MATH` on. `/init` is minimal and runs the checks as a child (`/etc/m1-checks.sh`), so PID 1 can't exit. The driver logs timer 1 interrupts #1-3, #100, #1000 and #10000 with the raw timer 2 count. **Boot 3:** the timer 1 tick runs at 100 Hz (#1000 at 10.017 s), uptime matches real time, no clocksource glitches. But every timed sleep returns at once: tinyconfig leaves `COMPAT_32BIT_TIME` off, musl uses the time32 `nanosleep`/`ppoll` for small values, and gets ENOSYS. |
| 783265 B, `f34f8ba8…` | `COMPAT_32BIT_TIME` and `POSIX_TIMERS` on. **Boot 4: milestone 1 done.** `sleep 2` = 2014135 µs, `sleep 10` = 10.0 s, timer 1 at 100 Hz, no glitches, UART input works, `reboot -f` returns to stock. |
| 842710 B, `25e2d0da…` | Next steps: SMP (no `maxcpus=1`), SIC0/SIC1 irqchip, panel console via simple-framebuffer (VT + fbcon; keyboard/mouse/serio off). `/init` also prints the online CPUs and `/proc/fb`. **Boot 5:** 2 CPUs, fbcon on the panel, timing right, SIC probe lines present. |
| 1333269 B, `6006330e…` | Ethernet (stmmac, 10.10.0.250/24) and USB host (EHCI ×2 + vendor PHY init). BusyBox adds `ifconfig`, `route`, `ping`, `tftp`, `nc` and `lsusb`. |
| 1333685 B, `462a7845…` | Same kernel; `/init` also prints the MDIO PHY ID and, for each USB device, the ID, bcdDevice, interfaces and endpoints (8782 boot-ROM vs firmware state, see `docs/kernel/wifi_88w8782.md`). No Ethernet cable on this printer: probe and PHY ID only. **Boot 6:** both EHCI controllers, hub 1a40:0101, Wi-Fi 1286:2040 (bcd 0x3119, 3+3 bulk endpoints) and webcam 0c45:6341 at 480 Mb/s; USB PHYs already powered by U-Boot. stmmac probes as DWMAC1000 (3.6), but the PHY at address 0 reads ID 0 (in reset?). |
| 1863877 B, `a15d015d…` | Wi-Fi: mwifiex + 8782 patch + stock firmware, `iw`; `/init` waits for `mlan0` and runs a **passive** scan (no association). Webcam: UVC + `uvcgrab` (one frame to `/tmp/frame.jpg`). |

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

The base image never touches GPIOs, heaters, motors or NAND. The `upc`
variant only ever forces the UPC-driven outputs *off* (until `upctool load`
starts firmware), and the `gpio` variant registers the banks without
driving anything. No image writes NAND. Power-cycling the printer returns
it to the stock firmware.

## Test cards (each needs the user at the printer)

Common to all: upload as usual (`tools/uboot_upload.py` to 0x02000000,
then `bootm 0x02000000`). `reboot -f` returns to stock. A panic resets
after 10 s. Back out any test by power-cycling.

### net: join Wi-Fi, then load kernels over the network

1. Boot `m1-net.uimg` (uniprocessor; Wi-Fi as in boot 7).
2. At the shell, type `wifi-join`. It asks for the SSID and the passphrase
   (not echoed). Only the derived key lands in `/tmp`; nothing is stored in
   any image. The user types them; don't paste them into logs.
3. **Success:** `iw dev mlan0 link` says "Connected", udhcpc prints a lease,
   and `ping <pc-address>` answers.
4. On the PC, in `D:\DP200\kernel\out`: `python -m http.server 8000` (allow
   it through the Windows firewall for the private network).
5. On the printer: `netload <pc-address> m1-upc-zImage-dtb.bin` (any
   `*-zImage-dtb.bin`; extra kernel arguments may follow).
6. **Success:** the new kernel's boot log on the serial console, in seconds
   instead of a 17-min upload.
7. **Known risk, untested:** the 88W8782 keeps its firmware running across
   kexec. Patch 0004 then skips the download ("no boot ROM answer, assuming
   the firmware runs"). If Wi-Fi fails in the kexec'd kernel, power-cycle
   before the next Wi-Fi test.

### upc: the UPC driver (Klipper MCUs)

1. Boot `m1-upc.uimg`, or `netload` it.
2. Automatic checks (`/etc/m1-variant.sh`) read back CPUSoftReset (must be
   0 = held), the first PWM CTRL words (bits 0 and 2 clear), the stepper
   CFG words (bit 0 set = driver off), and the UPC clock register 0xf8000180.
   Like stock `upc.ko` at load, the driver sets its bits 7:5 to 3 and logs
   "APB config old -> new". Compare with stock (`devmem 0xf8000180` there).
3. The user runs `upctool info` (reads only), then `upctool safe`.
4. Only then, with the user watching, try the passive probe firmware
   (`upc_fw/probe`). Klipper firmware, heaters and motion come later, one at
   a time (`docs/kernel/upc_mainline_design.md`, bring-up order).
5. **Success:** `/dev/upc0` and `/dev/upc1` exist, the dmesg line reads
   "cores held, outputs safe", and upctool sees the DTCM nonce.
6. Safety paths: `reboot -f` logs "reboot: cores held, outputs off";
   `echo c > /proc/sysrq-trigger` forces a panic, which must print
   "mv61x0-upc: panic: cores held, outputs off" before the 10 s reset.
   Repeat both later while the probe firmware runs, to prove the outputs
   really go off.

### sd: the SD socket, read-only

0. Pre-check, read-only, before spending a boot: at the U-Boot prompt
   `md.l 0xf804008c 4; md.l 0xf8041080 2`. These are the SD pins' function
   selects (bits 2:0 must be 2). The stock kernel sets them itself and
   mainline does not yet. If they aren't 2, skip this test until an
   approved pin-mux step exists; the image would only report "no card".
1. **The user inserts the 2 GB rescue card**, never the 4 GB working card,
   and confirms it before the upload.
2. Boot `m1-sd.uimg`. The checks wait for `mmcblk0`, set `force_ro`, print
   `/proc/partitions` and mount nothing.
3. Read-only look: `mount -o ro,noload /dev/mmcblk0p1 /mnt` (ext4; `noload`
   skips the journal replay, which would write).
4. **Success:** a "new ... SDHC card" line, the partitions match what the PC
   shows for that card, and the file listing works. `umount /mnt` before
   `reboot -f`.

### gpio: the GPIO banks, nothing driven

1. Boot `m1-gpio.uimg`.
2. Each bank logs "32 lines: in .. out .. dir .. (untouched)". The checks
   print the bank registers again and `/sys/kernel/debug/gpio`.
3. **Success:** eight gpiochips (A-H = 0xf8040000-0xf8047000), and the
   in/out/dir values equal the probe lines and the U-Boot `md.l` values,
   i.e. nothing changed.
4. Nothing requests a line in this image. The first real use (Ethernet PHY
   reset, GPIO 62 = bank B line 30) needs a DT `reset-gpios` and the user's
   OK, because requesting a line switches its pin to the GPIO function.
