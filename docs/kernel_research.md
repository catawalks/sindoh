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

## What a GPL source request is, and whether it can work

*Written 2026-10-28 for the user, who doubts an individual can get anywhere
with it. General knowledge about how GPL compliance works; nothing here is
specific knowledge of Sindoh's or Marvell's practices, and it isn't legal
advice.*

**What the license requires.** The Linux kernel and U-Boot are licensed
under the GNU GPL version 2. A company may put them in a product and sell
it, but in exchange it must give the people who receive the binaries the
matching source code: the "complete corresponding source", meaning the
code plus the scripts and configuration used to build it. GPLv2 section 3
gives the distributor three ways to do that: ship the source with the
product, include a **written offer**, valid for at least three years, to
provide it on request, or (for non-commercial redistribution only) pass on
an offer they received. Sindoh sells the printer commercially, so the
second option is the realistic one: somewhere in the manual, the printer's
legal/about screen or the support site there should be a notice like "this
product contains GPL software; source available on request from ...".

**Who has to answer.** The obligation is on whoever distributed the
binaries to you: **Sindoh**, who built this kernel (the module paths name a
Sindoh build machine) and shipped it in the printer. Marvell wrote most of
the platform code (the "LSP") and gave it to Sindoh, so Marvell owed Sindoh
the source, but Marvell didn't distribute anything to you. That's why the
request goes to **Sindoh first**. Asking Marvell as well is reasonable and
costs nothing (they sometimes publish LSP trees for their chips), but they
have no direct duty to a printer owner.

**Why an individual has standing.** The GPL's written offer must be valid
for "any third party" (GPLv2 3b), and the source must reach the recipients
of the binaries; you received them when you bought the printer. You don't
need to be a company, a developer, or a customer of record. Requests from
individual owners are exactly what the mechanism is for, and most source
releases of consumer devices (routers, TVs, NAS boxes, cameras) happened
because individuals asked.

**Why companies tend to answer.** Ignoring a request carries a real risk.
Copyright holders of kernel code, and groups that work with them
(Software Freedom Conservancy, gpl-violations.org in the past), have
enforced the GPL against device makers; lawsuits are rare but have been won
(e.g. Germany, against several consumer-electronics companies). Large
companies usually have an open-source compliance contact and a standard
process because it's cheaper than a dispute. A polite, specific, written
request is the normal and expected first step; it's not hostile.

**Honest expectations.**
- **Likely outcomes, roughly:** a download link or archive (best case); a
  partial tarball (often missing the build config or vendor drivers, which
  is then worth a polite follow-up); a long wait; or no answer at all.
  Smaller companies and regional subsidiaries (Sindoh is mostly a Korean
  office-equipment maker) answer less reliably than large ones.
- **The code is old** (kernel built 2016 from a 2014 LSP). The three-year
  offer period may be argued to have run out for older firmware, but it
  counts from the last time they distributed the binaries (e.g. as a
  firmware download), so an old product isn't automatically a lost cause.
- Even a perfect answer only gives the vendor kernel, which would let us
  rebuild it with Thumb, swap and CDC-ACM. It doesn't make the mainline port
  unnecessary for a modern kernel.
- **Nothing depends on it:** the cdc-acm module is built without it
  (install/kernel_modules/), and everything printing-related works on the
  existing kernel.

**How to send it.**
- Look first for the written offer (manual, printer legal screen,
  sindoh.com support pages) and use the address it names. Otherwise use
  Sindoh's support or contact form, ideally the global/US support plus Korea
  HQ.
- Include: the model (3DWOX DP200), the serial number, the firmware version
  you're running, and the exact kernel string (below). Ask for the kernel
  (with the mv61x0 platform code and the .config), U-Boot and any other
  GPL/LGPL components.
- Keep it short and polite. Give a reasonable time frame (e.g. 30 days) and
  ask for an acknowledgement.
- If there's no answer after the time frame: one reminder; then optionally
  ask Software Freedom Conservancy (compliance@sfconservancy.org) for
  advice. They take reports from users and contact companies themselves for
  devices that contain Linux.
- Marvell: a separate, shorter note asking whether the 88PA6170 (mv61x0)
  LSP kernel source is available, mentioning the product it's in.

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
> Printer serial number: [serial]. Firmware version: [version from the
> printer's info screen].
>
> A download link or an archive by email would be ideal. Could you confirm
> that you received this request, and let me know when I can expect the
> source (within 30 days if possible)?
>
> Thank you,
> [name]

Sources consulted (none had the source):
- [LinuxGizmos: 3D printer dev kit runs Linux on new Marvell ARMv7 SoC](https://linuxgizmos.com/3d-printer-dev-kit-runs-linux-on-new-marvell-armv7-soc/)
- [Kernel docs: ARM Marvell SoCs](https://docs.kernel.org/arch/arm/marvell.html): printer SoCs are not listed
- [MarvellEmbeddedProcessors/linux-marvell](https://github.com/MarvellEmbeddedProcessors/linux-marvell): Armada families only
- [Timesys 88PA6270 getting started](https://linuxlink.timesys.com/docs/gsg/pa6270): a vendor 4.2 kernel for the 64-bit successor
