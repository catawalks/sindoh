# Kernel research (first pass, 2026-10-20)

This is read-only research. Nothing was changed on the printer.
The goal is to judge whether a newer or rebuilt kernel is realistic. A new
kernel would give us:
- **Thumb support:** Debian armhf, and hardware floating point (the CPU has
  VFPv3 and NEON).
- **Swap.**
- **devtmpfs and namespaces.**
- **No more time64→time32 shims** (camera, touch).

## What runs now

| | |
|---|---|
| Version | `Linux 3.2.0-g67a8e16 #6 SMP PREEMPT Wed Nov 23 17:29:14 KST 2016` |
| Compiler | Marvell GCC 201208 (Linaro 4.6.4), `/opt/armcc.mv61x0/bin/arm-marvell-linux-gnueabi-` |
| Source tree (from the module `build` link) | `/home/inhwan5/Projects/marvell/SDK140404/marvell_lsp_distro_2014_04_02_shiloh/linux-mrvl`: Marvell's **LSP** (Linux Support Package) of April 2014, "shiloh" release, built at Sindoh |
| Platform | `CONFIG_ARCH_MV61X0`, board `CONFIG_MV61X0_P000_PRINTER`; errata options for the 88PA6170 (BZ 833, BZ 664) |
| Boot | U-Boot → zImage from NAND `mtd0` (8 MB), **ATAGS**, no device tree (`CONFIG_OF` not set) |
| CPU | 2× Marvell PJ4B-MP (ARMv7, id 0x562f5841), GIC, PL310 L2 (64 KB), 512 MB RAM (490 MB usable) |
| Config | full `.config` saved: [kernel/vendor_3.2.0-g67a8e16.config](kernel/vendor_3.2.0-g67a8e16.config) (from `/proc/config.gz`) |
| Hardware map | iomem, interrupts, dmesg, devices: [kernel/vendor_hw_snapshot.txt](kernel/vendor_hw_snapshot.txt) |

**Missing config options that hurt us:**
- `ARM_THUMB`: armhf is impossible, so we use armel (soft-float).
- `SWAP`: no swap at all.
- `DEVTMPFS`.
- `NAMESPACES`, `SECCOMP`, `FHANDLE`: no systemd. That's fine, we don't
  use it.

What it does have: `MODULES`, `IKCONFIG_PROC`, `KALLSYMS_ALL`
(46 512 symbols), `OABI_COMPAT`, `HIGHMEM`, `VFPv3`/`NEON`, `PREEMPT`,
`HZ=100`.

### Peripherals and their drivers

| Block | Address | Driver now | Mainline equivalent |
|---|---|---|---|
| UART ×4 | f8060000.. | 8250 | yes (`ns16550a`) |
| GIC, PL310, PJ4B | — | ARM core | yes (PJ4B is supported for Armada 370/XP) |
| Timers (Timer 0-3, irq 52-55) | ? | vendor | **no**: needs a small clocksource driver |
| SIC0 secondary irq controller (DEC timers, dec_sensor) | — | vendor | **no**: small chained irq driver |
| GPIO ×8 banks, pinmux (`set_pin_config`) | f8040000.. | vendor | **no**: gpio + pinctrl driver |
| I²C ×2 | f80a2000, f80a3000 | `i2c_designware` | yes |
| SPI ×3 | f8070000.. | `dw_spi_mmio` | yes |
| NAND | f9082000 | `mv61x0_nand` (vendor) | **no**: biggest missing driver. Avoidable by booting from SD. |
| SD/MMC ×2 | f9080000, f9080200 | `sdhci-gogin` (vendor) | probably `sdhci-pltfm` plus quirks |
| USB host ×2 | f9041000, f9048000 | EHCI "mv61xx" | probably `ehci-platform` |
| USB gadget | — | ci13xxx | `chipidea` (maybe) |
| Ethernet | f9050000 | `synopGMAC` (vendor) | probably `stmmac` / dwmac-generic |
| WiFi (USB, 88W8782) | — | `usb8xxx` + `mlan` (out-of-tree) | mainline `mwifiex` has no USB 8782 as far as I know; **check** |
| LCD | f9070000 | `mv61tft` / `mv61-fb` | **no**; U-Boot already sets the panel up (boot logo), so a `simple-framebuffer` node could reuse that |
| Touch | I²C, GPIO irq | `TOUCHSCREEN_ROHM` (vendor) | yes: `bu21029_ts` (mainline since 4.19) |
| UPC ×2 (our Klipper MCUs) | f9200000, f9210000 | `upc.ko` (module) | **no**, but we know the hardware (upctool already uses /dev/mem); a small new driver or plain UIO |
| DEC blocks (pwm, adc, sensor, wavegen…) | f9300000.. | UIO (`uio_pdrv_genirq`) | UIO works in mainline too |
| CDMA, JBIG, SCCP, RTC "gogin" | — | vendor | not needed by us (RTC is nice to have) |

## The routes

**1. Rebuild the vendor 3.2 kernel with the missing options.** This is the
best value: our userspace and the UPC firmware keep working unchanged, and
we gain Thumb (armhf), swap and devtmpfs. It is **blocked on the source**.
- Sindoh (and Marvell's LSP) are GPL code and must offer the kernel source.
  Nothing is published: searches for the SoC, `mv61x0`, the LSP name and a
  Sindoh GPL page found nothing.
- **Action for the user:** send Sindoh a written GPL source request for the
  DP200 / 3DWOX firmware kernel (`3.2.0-g67a8e16`, built 2016-11-23) and
  U-Boot. There's a draft below.
- Related lead: Marvell's 2015 "88PA6120 3D Printer Development Kit"
  (the smaller sibling chip) shipped a Linux 3.14 SDK with source code to
  partners. It isn't public, but a copy may surface.

**2. Mainline kernel (6.x) with a new device tree.** This is a real porting
project, but most blocks already have mainline drivers (table above).
- **New code needed:**
  - timer and SIC irq driver;
  - gpio/pinctrl;
  - UPC driver (or UIO);
  - probably sdhci/ehci/stmmac glue.
- **Display:** `simple-framebuffer` reusing what U-Boot sets up.
- **Avoid NAND entirely** by booting from SD (this ties in with the
  SD/DIP-switch boot task). That way the stock firmware stays untouched,
  and the NAND driver can come last, or never.
- **WiFi is the risk:** without the vendor `usb8xxx` driver, a USB WiFi
  dongle with a mainline driver may be the practical answer.
- Weeks of work, done in milestones:
  1. serial console + timer + GIC with an initramfs, loaded from RAM by
     U-Boot (`loady`/`bootz`, nothing written to flash);
  2. SD card root;
  3. USB/Ethernet/WiFi;
  4. UPC + DEC UIO, then Klipper;
  5. LCD + touch.

**3. Keep 3.2 and work around it (current state).** This works today:
- armel userspace;
- time32 shims for V4L2 and input;
- killing stock processes for RAM.

Swap stays impossible. Workable for printing.

**Not recommended:** patching the running kernel from a module, e.g.
setting `HWCAP_THUMB` so the ELF loader accepts Thumb binaries. Without
`CONFIG_ARM_THUMB` the signal and exception paths don't handle the Thumb
state bit, so programs would crash randomly on signals.

## Suggested next steps

1. User: send the GPL request (draft below).
2. Me (unattended): the SD/DIP U-Boot investigation, to read U-Boot's
   environment and commands (`mtd1` u-boot-env, strings of U-Boot). This
   answers whether U-Boot can load a kernel from SD or over serial.
3. With the user's OK (the printer must reboot into U-Boot, Klipper off,
   no heaters): milestone 1 of route 2. Boot a mainline zImage with only a
   UART + GIC + timer DT, loaded into RAM. Nothing is written to flash, and
   a power cycle returns to stock.

## Draft GPL request (for the user to send, edit as needed)

> Subject: GPL source code request - Sindoh DP200 (3DWOX) firmware
>
> Hello,
>
> I own a Sindoh 3DWOX DP200. Its firmware contains the Linux kernel
> (version 3.2.0-g67a8e16, built 23 Nov 2016) and U-Boot, which are licensed
> under the GNU GPL version 2. Under section 3 of that license I request the
> complete corresponding source code for the kernel (including the Marvell
> mv61x0 platform code, drivers and the build configuration), for U-Boot,
> and for any other GPL-licensed components in the current DP200 firmware.
>
> A download link or an archive by email would be ideal.
>
> Thank you,
> [name]

Sources consulted (none had the source):
- [LinuxGizmos: 3D printer dev kit runs Linux on new Marvell ARMv7 SoC](https://linuxgizmos.com/3d-printer-dev-kit-runs-linux-on-new-marvell-armv7-soc/)
- [Kernel docs: ARM Marvell SoCs](https://docs.kernel.org/arch/arm/marvell.html): printer SoCs are not listed
- [MarvellEmbeddedProcessors/linux-marvell](https://github.com/MarvellEmbeddedProcessors/linux-marvell): Armada families only
- [Timesys 88PA6270 getting started](https://linuxlink.timesys.com/docs/gsg/pa6270): a vendor 4.2 kernel for the 64-bit successor
