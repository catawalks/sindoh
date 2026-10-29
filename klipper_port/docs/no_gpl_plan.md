# The "no GPL source" route for the DP200 kernel

Written 2026-10-28. This is the fallback in case the GPL source requests to
Sindoh and Marvell bring nothing back. It covers two things:
- how far out-of-tree modules for the running 3.2 kernel can go;
- the plan for porting a mainline 6.x kernel without vendor source.

Nothing here touched the printer. Every new fact comes from offline analysis
of the vendor kernel image in our own NAND dump (`nand_images/mtd0.bin`),
using `tools/kernel_re/` (README there), plus the existing
`docs/kernel/vendor_hw_snapshot.txt` and the vendor `.config`.

New files:
- `docs/kernel/vendor_System.map`: 38,440 kernel symbols, rebuilt from
  kallsyms;
- `docs/kernel/vendor_hwtables.txt`: the static I/O map, every platform
  MMIO/IRQ resource, and the machine record;
- `kernel/m1/`: milestone 1 build (timer driver, device tree, config, build script).

**Short version:**
- **Modules (route A):** they cover the missing *drivers*: USB serial,
  squashfs, FUSE, TUN, zram as a block device, USB gadget network/serial.
  They can't add *core* features: swap, Thumb/armhf, devtmpfs, time64,
  namespaces. The GPL source or a new kernel is the only way to get those.
- **Mainline (route B):** more realistic than it looked on 2026-10-20.
  - The CPU complex (PJ4B-MP + SCU + GIC, Cortex-A9-style private region)
    is the same arrangement as Marvell MMP3, which mainline supports.
  - UART, I²C, SPI, GIC, EHCI (ChipIdea), GMAC (Synopsys) and the Marvell
    88E1510 PHY all have mainline drivers.
  - The NAND controller is a **PXA3xx NFC**, which mainline's `marvell_nand`
    supports. The vendor resource is literally named `pxa3xx_resources_nand`,
    and the driver's strings and registers come from `pxa3xx_nand.c`.
  - Milestone 1 needs one new ~150-line timer driver. It might need none, if
    a TWD exists (to be checked).
  - The hard part is getting a kernel into RAM. This U-Boot has no `loady`,
    no `bootz`, no `fdt`, and no Ethernet driver. Its options are TFTP over
    the USB-B gadget port, or uploading through the serial console with
    `mw`.

---

## 0. What the offline analysis found

| Fact | Value | Source |
|---|---|---|
| Machine | ATAGS machine number **10000 (0x2710)**, name `mv61x0`. Hooks: `gogin_map_io`, `mv61x0_init_early`, `mv61x0_init_irq`, `gogin_timer`, `mv61x0_mach_init` | `__arch_info_begin` in vendor_hwtables.txt |
| Static I/O map | 34 entries. Most are virtual = physical (0xf8xxxxxx/0xf9xxxxxx). Exceptions: **timer 0xfed20000 → 0xf8020000**, prescaler 0xfed30000 → 0xf8030000, 0xfed60000 → 0xf9600000, 0xfee00000 → 0xfa300000 | `gogin_io_desc` |
| GIC | Distributor **0xf8fe1000**, CPU interface **0xf8fe0100**. `gic_init(0, 29, ...)` gives a 0 offset, so the vendor IRQ number = GIC ID and **GIC_SPI = vendor IRQ − 32** | `mv61x0_init_irq` |
| SCU | 0xf8fe0000 (`scu_enable`). That is the Cortex-A9 private-region layout (SCU +0, GIC CPU +0x100, distributor +0x1000) | `platform_smp_prepare_cpus` |
| L2 | The vendor calls `l2x0_init` on 0xf8fe0000, which is the SCU. The "CACHE_ID 0x00000001" in dmesg is really the SCU control register. It then clears every outer-cache operation except `sync`. That sync is `mv61x0_cache_sync`, which writes 0x01010101 to **phys 0xfa300530** (probably a write-buffer drain; errata BZ 833/664?). So the L2 isn't really driven by a PL310 driver | `mv61x0_l2_init`, `mv61x0_cache_sync` |
| SMP | `boot_secondary` writes the physical address of `secondary_startup` to **phys 0xfa000000**, then raises an SGI. A normal pen_release scheme | `boot_secondary` |
| Timer block | phys 0xf8020000, IRQs 52-55 (SPI 20-23). Each timer n at +0x10·n has: +0x04 load, +0x08 control (bit0 enable, bit1 auto-reload), +0x0c count. +0x10 IRQ status (bit n), +0x20 IRQ clear. The prescaler at 0xf8030000+0 is written with busfreq/1 MHz (198), so the timers tick at **1 MHz**. Timer1 is the clockevent (periodic: load 10000 = 100 Hz). Timer2 runs free from 0xffffffff as the clocksource. There are no TWD local timers: broadcast IPIs are in use | `timer_*`, `mv61x0_time_init` |
| UART | 4 × 8250 at 0xf8060000 + 0x1000·n, IRQs 32-35, **uartclk 25 MHz, regshift 2, UPIO_MEM32** | `serial0_platform_data` |
| Secondary IRQ controllers | SIC0 regs 0xf9300100, IRQs 145-176, chained from GIC 133 (SPI 101). SIC1 regs 0xf9300200, IRQs 177-208, chained from GIC 135 (SPI 103). Registers: +0x0c ack, +0x14 mask, +0x18 pending; level-triggered | `init_sic_irq`, `sic_*` |
| GPIO | 8 banks of 32 at 0xf8040000 + 0x1000·n, IRQs 38-45. +0x00 input, +0x04 output, +0x08 direction (1 = out); interrupt registers up to +0x50 | `gogin_gpio_*` |
| NAND | 0xf9082000, IRQ 65. **PXA3xx NFC**: NDSR +0x14, NDECCCTRL +0x28, NDCB0 +0x48; strings "NDSR_UNCERR", "handle_data_pio", "command execution timed out" | `mv61x0_nand_*` |
| SD/MMC | 0xf9080000 / 0xf9080200, shared IRQ 66. Quirks: reads of 0xfc/0xfe (slot status / **host version**) return 0, and capability bit 25 (3.0 V) is cleared | `sdhci_gogin_readw/readl` |
| USB | Device ci13xxx 0xf9040000 (IRQ 97). Host EHCI 0xf9041000 (IRQ 98) and 0xf9048000 (IRQ 99), with **caps at +0x100** (a ChipIdea core). PHY registers 0xf904f000 + per-port 0xf904f040/080/0c0, set up by `usb_phy_init` (PLL and calibration bits) | resources, `ehci_mv61xx_drv_probe`, `usb_phy_init` |
| Ethernet | Synopsys GMAC 0xf9050000-0xf90510ff (MAC + DMA at +0x1000), IRQ 96. PHY 0141:0DD1 = Marvell 88E1510 family at address 0 | resources, dmesg |
| I²C / SPI clocks | i2c 400 MHz, spi 200 MHz (clkdev entries) | `i2c_clk2`, `spi_clk0` |
| U-Boot 2011.09 | Commands: `bootm`, `tftpboot`, `bootp`, `ping`, `nand`, `mmc`, `ext2load`, `md`, `mw`, `cp`, `cmp`, `mm`, `nm`, `go`, `crc32`, `iminfo`, `bdinfo`, `source`, `run`. **No** `loady`/`loadb`, `bootz`, `fdt`, or `usb`. The only network driver is the **USB Ethernet gadget** ("CDC Ethernet", `usbnet_devaddr`); there is no GMAC driver. It prints "Boot logo Phys Addr: 0x…" at boot | strings of the signed U-Boot ELF in mtd0 |

IRQ numbers in GIC_SPI terms, for the device tree:

| Block | SPI | Block | SPI |
|---|---|---|---|
| UART0-3 | 0-3 | GPIO A-H | 6-13 |
| SCCP 0/1 | 4/5 | Timers 0-3 | 20-23 |
| PMU | 27 | RTC | 32 |
| NAND | 33 | SD0+SD1 | 34 |
| I²C 2/3 | 40/41 | LCD (`mv61-fb`) | 43 |
| SPI 0-2 | 59-61 | GMAC | 64 |
| USB device | 65 | EHCI 0/1 | 66/67 |
| CDMA | 77 | UPC 0/1 | 94/95 |
| SIC0 / SIC1 parent | 101 / 103 | DEC fuser/adc/pwm/sensor | SIC0 lines 21-24 (IRQs 166-169) |

---

## 1. Route A: out-of-tree modules on the running 3.2 kernel

**Recipe (already proven by cdc-acm.ko,** `install/kernel_modules/README.md`):
- vanilla `linux-3.2` + the vendor `.config` + `LOCALVERSION=-g67a8e16`;
- Versatile Express standing in for the missing `ARCH_MV61X0`;
- native GCC 14 in the printer's chroot.

`MODVERSIONS` is off, so only the vermagic string has to match. Struct
layouts are checked against the vendor modules' debug info (`verify/`).
That works for any driver that only uses generic kernel structures.

### What can be added as a module

| Module | Config | Value for us | Risk / notes |
|---|---|---|---|
| `cdc-acm` | `USB_ACM` | Klipper USB boards (RP2040 ADXL345) | **Built and verified**; the insmod test needs the user |
| `ch341`, `pl2303` | `USB_SERIAL_CH341/PL2303` | CH340 boards and cheap adapters (input_shaping.md: "CH340 boards won't work") | Low: usb-serial core is built in. `cp210x.ko` is already in the stock modules |
| `squashfs` + `xz_dec` (or zlib/lzo) | `SQUASHFS`, `XZ_DEC=m` | **Project 3:** a read-only, compressed Klipper runtime. 431 MB raw → ~140 MB, as a file on UBIFS loop-mounted (`loop.ko` exists). Frees most of the remaining NAND space | Low. `zlib_inflate`/`lzo1x_decompress` are exported, and xz_dec builds as its own module. UBI block devices (`ubiblock`) only arrived in 3.15, hence the loop file |
| `fuse` | `FUSE_FS` | sshfs, rclone mounts, AppImage-style tools | Low |
| `tun` | `TUN` | OpenVPN / tinc remote access (WireGuard needs ≥ 3.10: not possible) | Low |
| `g_ether` / `g_serial` / `g_cdc` | USB gadget | A network link or a second console over the **USB-B port** to a PC, instead of `g_printer`. Gadget modules in 3.2 compile the composite framework in, so they stand alone | Medium: the vendor's `ci13xxx` UDC is patched ("Sindoh MFP" strings); only one gadget can bind at a time |
| `binfmt_misc` | `BINFMT_MISC` | Running armhf-only binaries through `qemu-arm` (user-mode emulation) | Low, but slow (emulated). A curiosity, not a fix for armel |
| `zram` (staging, 3.2 = xvmalloc version) | `STAGING`, `ZRAM` | Compressed RAM **block device**: `mkfs.ext2` on it for /tmp, build directories or logs | Low. **Not usable as swap**, see below |
| `uinput` | `INPUT_UINPUT` | Synthesizing input events (screen tests, alternative touch handling) | Low |
| Other USB Wi-Fi chips | vendor out-of-tree drivers (e.g. Realtek `8188eu`-style, which bring their own stack) | A fallback if the 8782 module gives up | Medium: `cfg80211`/`mac80211` are built in at 3.2 level, and drivers from compat-wireless need the matching backport |
| `snd` + `snd-usb-audio` | `SOUND` | A USB speaker for print-done sounds | Low; nice to have |

All of these follow the same build, check and insmod plan as cdc-acm.
Drivers that touch Marvell-patched subsystems (the UDC, `mmc`, `mtd`, the
framebuffer) need an extra layout check against the running kernel's code
(`verify/kdump.sh` / `offcompare.py`) before any insmod.

### What a module can't do, and why

| Wanted | Why it can't be a module |
|---|---|
| **Swap** (also zram-as-swap, zswap, frontswap) | `CONFIG_SWAP` is core mm: the swap cache, anon-page reclaim in `vmscan.c`, swap PTE entries, `sys_swapon` (compiled to `-ENOSYS` without it). There is no hook for a module to add any of that. zram can only be a filesystem-in-RAM, which saves page cache, not anonymous memory |
| **Thumb userspace / armhf** | `CONFIG_ARM_THUMB` changes the exception entry, signal return trampolines, `ptrace` and the ELF `HWCAP_THUMB` check. Setting the hwcap from a module would let Thumb binaries start, then crash on the first signal (kernel_research.md, "Not recommended"). qemu via binfmt_misc is the only module-level crutch |
| **devtmpfs** | Hooked into `device_add()`/`device_del()` in the driver core, and mounted by `prepare_namespace()`; nothing is exported for it. mdev / static `/dev` stays (already done) |
| **time64** (`clock_gettime64`, 64-bit `input_event`/V4L2 timestamps) | New syscall table entries (Linux 5.1+) and changed core ABIs. The LD_PRELOAD time32 shims stay (they work) |
| Namespaces, seccomp, `fhandle`, AIO | `cond_syscall` stubs plus core structures (`nsproxy`, `task_struct` fields). No containers, no systemd, no Docker. Not needed |
| HZ, high-res timers, NO_HZ, PREEMPT model | Scheduler/timekeeping core |
| kexec (booting a new kernel from Linux) | `CONFIG_KEXEC` is off, so there is no `kexec_load` syscall or `machine_kexec`. A self-written module *could* do it: stop CPU1 (`HOTPLUG_CPU=y`), copy the kernel, turn off the MMU and caches, and jump with r1 = machine number, r2 = ATAGS/DTB. Doable, but delicate. Listed as a loader option in §2.3 |

**Conclusion for route A:** it fixes the *peripheral* gaps cheaply and
safely (input-shaping sensors, a compressed NAND install, USB network). The
*system* gaps (armel, no swap) stay until we get the GPL source or a new
kernel.

---

## 2. Route B: mainline 6.x without vendor source

### 2.1 Which mainline SoC is closest

| Mainline family | CPU complex | Match with the 88PA6170 |
|---|---|---|
| **MMP3** (`mmp3.dtsi`, mainline since 5.6) | 2 × PJ4B-MP, SCU 0xe0000000, GIC CPU +0x100 / distributor +0x1000, TWD +0x600, PL310, enable-method `marvell,mmp3-smp` | **Closest CPU complex**: same core, same A9-style private region. Model our SMP and cache setup on it. Different peripherals (PXA UARTs, MMP timers, own ICU) |
| **Berlin BG2/BG2CD** (`berlin2*.dtsi`) | PJ4B-MP + SCU + GIC, Tauros3 L2, DW APB UART/timers | Close CPU complex too. Its SDHCI (`mrvl,pxav3-mmc`), ChipIdea USB with a Marvell PHY, and DesignWare I²C/SPI blocks are the same IP family as ours |
| Armada 370/XP (mvebu) | PJ4B / PJ4B-MP with the Marvell coherency fabric, **MPIC** (not GIC), Aurora L2 | The CPU core matches (`proc-v7.S` `__v7_pj4b_setup`; our MIDR 0x562f5841 matches its 0x560f5800/0xff0fff00 entry), and so does the **NAND controller** (marvell_nand). Its IRQ controller and SMP don't |
| MMP2 / PXA168 | PJ4 (not B) / PJ1 | Only the SDHCI and USB PHY families |
| 88PA6120 / 6270 (other printer SoCs) | — | Not in mainline |

So the device tree is new, but nearly every building block has a model.

### 2.2 Block by block

| Block | Address / IRQ | Mainline candidate | New code | Confidence |
|---|---|---|---|---|
| CPU | PJ4B-MP ×2 | `CPU_PJ4B` in a `ARCH_MULTI_V7` build, `marvell,pj4b` | none | high |
| GIC | 0xf8fe1000 / 0xf8fe0100 | `arm,cortex-a9-gic` | none | high |
| SMP | mailbox phys 0xfa000000 + SGI | — | ~60-line `smp_operations` (copy of `mmp3-smp` / berlin) | high (logic is visible in `boot_secondary`) |
| L2 / cache sync | write 0x01010101 to 0xfa300530 | — | possibly an `outer_cache.sync` hook in the platform code; run without the L2 first | **unknown**: what U-Boot leaves enabled, and what the register really is |
| Timer | 0xf8020000, SPI 20-23, 1 MHz | `TWD` if it exists at 0xf8fe0600, else nothing | ~150-line `TIMER_OF_DECLARE` driver (clocksource timer2, clockevent timer1) | high (registers decoded) |
| UART | 0xf8060000.., SPI 0-3 | `ns16550a`, reg-shift 2, reg-io-width 4, 25 MHz (maybe `snps,dw-apb-uart`, see §2.5) | none | high |
| SIC irqchips | 0xf9300100/0200 | — | ~120-line chained irqchip (needed for the DEC timers/sensor, not for Klipper's UPC) | high |
| GPIO | 0xf8040000.. | `gpio-mmio` style (dat/set/dirout) | small driver or new compatible; IRQ part ~200 lines | high |
| Pinmux | `set_pin_config` (in the APB config at 0xf8000000) | `pinctrl-single`? | registers not decoded yet; U-Boot/boot ROM setup is probably enough at first | medium |
| I²C ×2 | 0xf80a2000/3000, SPI 40/41 | `snps,designware-i2c` (clock 400 MHz) | none | high |
| SPI ×3 | 0xf8070000.., SPI 59-61 | `snps,dw-apb-ssi` (200 MHz) | none | high |
| SD/MMC ×2 | 0xf9080000/0200, SPI 34 | `sdhci-pltfm` glue (`mrvl,pxav3-mmc` worth trying; `sdhci-caps-mask` covers the cleared 3.0 V bit) | small glue for host version = v1.0 and card power (the board doesn't use the SDHCI power bit) | medium |
| NAND | 0xf9082000, SPI 33 | `marvell,pxa3xx-nand-controller` (marvell_nand) | none expected; the ECC mode and BBT layout must match the stock UBI | medium (read-only first) |
| USB host ×2 | 0xf9041000/8000 (caps +0x100), SPI 66/67 | `chipidea,usb2` host mode (`ci_hdrc_usb2`) + a PHY | ~100-line generic-PHY driver replaying `usb_phy_init` (registers 0xf904f004/008, per-port +0xc bit 15) | medium |
| USB device | 0xf9040000, SPI 65 | ChipIdea UDC (same core, `dr_mode = "peripheral"`) | none beyond the PHY | medium |
| Ethernet | 0xf9050000, SPI 64, 88E1510 | `stmmac` (`snps,dwmac-3.x`?) + `marvell` PHY driver | none expected; check the GMAC version register | medium-high |
| Wi-Fi | USB 1286:2040 (88W8782) | `mwifiex_usb` covers 8766/8797/8801/8897/8997; **8782 / PID 0x2040 isn't listed** (check against current `mwifiex/usb.h`) | port the 8782 into mwifiex (firmware `usb8782_uapsta.bin` is on the printer), or use a USB dongle / the Ethernet port | low |
| Camera | UVC 0c45:6341 | `uvcvideo` | none; the time32 shim goes away | high |
| LCD | 0xf9070000, SPI 43; 800×480 RGB565, stride 1600 | `simple-framebuffer` on the buffer U-Boot set up | none for display. Backlight: unknown (the stock fb `blank` doesn't turn it off) | high (display only) |
| Touch | BU21029 on I²C-2 @0x40, GPIO interrupt | `bu21029_ts` (mainline since 4.19) | none | high once GPIO works |
| Cartridge chip | "Smart-IC" on I²C-3 @0x30 (DS2465 → DS28E22) | `i2c-dev` from userspace (as now) | none | high |
| **UPC ×2 (Klipper MCUs)** | 0xf9200000 (64 KB) / 0xf9210000 (0xb0000), SPI 94/95 | — | small misc driver with upc.ko's 4 ioctls (RUN/HOLD, ITCM select, DTCM select; hardware_notes.md has them decoded) **or** UIO + teaching upctool the ITCM/DTCM window. upctool already maps DTCM/XENA through /dev/mem | high |
| DEC blocks (pwm, adc, sensor, fuser, wavegen) | 0xf9300000.. | `uio_pdrv_genirq` as today | SIC irqchip for their IRQs | high |
| RTC | 0xf8100000, SPI 32 | — | small `rtc` driver (nice to have; NTP covers it) | — |
| Temperature sensor | 0xf80f0000.. (`tsen`) | — | hwmon later | — |
| JBIG/JPEG/PIP/CDMA/SCCP | | not needed | | |

### 2.3 Getting a kernel into RAM (the real bottleneck)

What U-Boot 2011.09 offers (§0):
- `bootm` of a uImage, with ATAGS and machine number 10000;
- no `bootz` and no `fdt`, so the DTB has to be **appended** to the zImage
  (`ARM_APPENDED_DTB` + `ARM_ATAG_DTB_COMPAT`), wrapped with `mkimage -A arm
  -T kernel -C none -a 0x8000 -e 0x8000`;
- its SD driver sees no card (sd_boot_plan.md);
- it has no serial download command;
- its only network path is the USB gadget.

Loader options, best first. **None of them runs `saveenv` or writes flash.**

1. **TFTP over the USB-B port (CDC Ethernet gadget).** At the U-Boot
   prompt: `setenv usbnet_devaddr ...; setenv usbnet_hostaddr ...;
   setenv ipaddr ...; setenv serverip ...; tftpboot 0x2000000 m1.uimg;
   bootm 0x2000000`.
   - The PC side must speak CDC-ECM. Windows 10 has no inbox ECM driver, so
     use a Linux host: a Raspberry Pi, or a Linux VM with USB passthrough,
     running `tftpd`.
   - Seconds per try, so this is the development loop.
   - To verify first: `help usb`/`bdinfo`, and whether the gadget enumerates
     (needs the user at the console).
2. **Serial upload with `mw.l`.** A PC script types `mw.l <addr> <word>`
   lines (or `mm` sequences) and checks the result with `crc32`.
   - Roughly 25 characters per 4 bytes at 115200 baud: a 2.5 MB milestone-1
     image (small initramfs) takes about **20-25 minutes**.
   - Slow, but it needs only the console we already use. Fine for the first
     few boots if option 1 fails.
3. **A "kexec" module from the running 3.2.** No U-Boot interaction at all,
   but it needs an insmod and careful CPU1/cache/MMU shutdown (see the
   table in §1). Higher risk of a hang; a power cycle recovers it. Worth it
   only if 1 and 2 fail.
4. **An image in an unused NAND area, read with `nand read`.** Fast and
   simple, but it **writes NAND**: only with the user's explicit OK, and
   only to an area proven unused. Not part of the plan.

The safety net is the same in every case: the kernel only lives in RAM, so
a power cycle goes back to the stock boot (DIP = NAND, env unchanged).

### 2.4 Milestone 1: RAM-booted mainline kernel with UART, GIC and timer

**Goal:** a mainline 6.x kernel boots to a BusyBox shell on ttyS0 from a
built-in initramfs. One CPU, no storage, no network.

**Build:**
- `multi_v7_defconfig` stripped down, with `CPU_PJ4B`, `ARM_APPENDED_DTB`,
  `ARM_ATAG_DTB_COMPAT`, `SERIAL_8250`, `SERIAL_OF_PLATFORM`, `ARM_GIC` and
  `INITRAMFS_SOURCE`;
- Thumb2 kernel **off** at first (PJ4B runs Thumb2, but keep the variables
  few);
- `DEBUG_LL` + `DEBUG_UART_8250` with phys 0xf8060000, shift 2, word
  access, and `EARLY_PRINTK`, so the decompressor and early boot are
  visible before the device tree is parsed;
- an armhf BusyBox for the initramfs. It runs: a new kernel has Thumb.

**Device tree:** `kernel/m1/src/arch/arm/boot/dts/marvell/88pa6170-dp200.dts`: memory 512 MB, CPU
`marvell,pj4b`, GIC, the SoC timer, UART0 at 25 MHz, and
`earlycon=uart8250,mmio32,0xf8060000 maxcpus=1`.

**New code:** `drivers/clocksource/timer-mv61x0.c`, about 150 lines:
- clocksource = timer2 free-running (`clocksource_mmio_init`, with
  readl_down or readl_up depending on §2.5);
- clockevent = timer1 one-shot/periodic on SPI 21;
- the prescaler at 0xf8030000 set to busfreq/1 MHz (or left as U-Boot set
  it).

If a TWD answers at 0xf8fe0600 (§2.5), the clockevent can be
`arm,cortex-a9-twd-timer` instead. The clocksource is still needed, because
PJ4B has no global timer.

**Done when:**
1. earlycon output appears;
2. "Booting Linux on physical CPU 0" through to the initramfs shell;
3. `cat /proc/interrupts` shows the timer IRQ counting;
4. `sleep 10` takes 10 s by a stopwatch;
5. the UART works with interrupts (typing at the shell).

**Risks:**
- What U-Boot leaves in the caches and L2. Mitigation: the decompressor
  flushes and turns off the caches; no outer cache in milestone 1.
- The unknown errata register at 0xfa300530. Mitigation: UP only, no DMA in
  milestone 1.
- A wrong IRQ trigger type. All are set to level-high, the GIC reset
  default. The vendor's `gic_set_type` calls aren't decoded yet.

**Effort:** 2-4 working days once a loader from §2.3 works: timer driver,
DTS, config, and the first boots.

### 2.5 Facts still missing, and how to collect them

**A. Read-only commands within today's printer rules** (`cat /proc`,
`dmesg`, `dd` of `/dev/mtd*` to stdout, `md5sum`). Safe while printing,
but leave the serial console to the main session.

| Fact | Why | Command |
|---|---|---|
| Offline System.map is right | Every address above relies on it | `cat /proc/kallsyms \| grep -E ' (timer_set_next_event\|gogin_map_io\|boot_secondary\|sic_handler)$'`. Must equal the addresses in `docs/kernel/vendor_System.map` (c001e25c, c0575364 (an init function, still listed), c041b060, c001ee60) |
| Clockevent/clocksource names, broadcast mode, no TWD | Confirms timer1/timer2 and that no local timer is registered | `cat /proc/timer_list \| grep -E 'Clock Event Device\|mode\|event_handler'` |
| CPU features | PJ4B revision, IWMMXT/VFP flags | `cat /proc/cpuinfo` |
| Full boot log | Any messages lost before the snapshot | `dmesg` (if the ring buffer still holds the boot) |
| U-Boot env | Already in the repo (sd_boot_plan.md) | `dd if=/dev/mtd1 bs=128k count=1 \| md5sum` to confirm it's unchanged |

**B. Read-only `/dev/mem` reads (`devmem` / `tools/memdump.py`).** Safe
reads of status/ID registers, but **outside the agreed list: ask the user
first.** Don't read FIFOs or clear-on-read registers. The UART RBR (+0x00)
and the NAND data buffer are left out on purpose.

| Fact | Address(es) | Read |
|---|---|---|
| TWD present? | 0xf8fe0600, 0xf8fe0604 (load/counter), 0xf8fe0608 (control) | `devmem 0xf8fe0604` twice: a moving value means a TWD |
| Timer2 count direction | 0xf802002c | two reads a second apart (falling = readl_down) |
| Prescaler value | 0xf8030000 | expect 198 (0xc6) |
| UART IP (DesignWare?) | 0xf80600f4 (CPR), 0xf80600f8 (UCV), 0xf80600fc (CTR) | UCV = an ASCII version (e.g. "3.11a") and CTR = 0x44570110 ("DW") → `snps,dw-apb-uart` |
| GMAC version | 0xf9050020 | `0x1037`-style Synopsys version → stmmac `snps,dwmac-3.70a` etc. |
| SD host version (raw) | 0xf90800fc (32-bit read covers 0xfc/0xfe) | what the vendor hides; decides pxav3 vs plain |
| SD capabilities | 0xf9080040, 0xf9080044 | for `sdhci-caps-mask` |
| NAND config | 0xf9082000 (NDCR), 0xf9082004/0c (timings), 0xf9082028 (NDECCCTRL) | ECC mode (Hamming vs BCH), page size, for marvell_nand |
| ChipIdea IDs | 0xf9040000, 0xf9041000, 0xf9048000 (ID), +0x100 (CAPLENGTH/HCIVERSION) | confirms `ci_hdrc` |
| USB PHY state | 0xf904f000-0xf904f0ef | the values `usb_phy_init` leaves, for the PHY driver |
| Framebuffer base | LCD regs 0xf9070000-0xf9070207 (one of them holds the scan-out address) | for `simple-framebuffer`; also printed by U-Boot ("Boot logo Phys Addr") |
| SIC state | 0xf9300100-0xf930011c, 0xf9300200-0xf930021c | mask/pending layout check |
| Boot strap / chip ID | 0xf8000000-0xf80000ff (APB config) | pinmux register layout, revision ("ASSP revision C1") |

**C. Needs the user at the serial console** (the printer idle, Klipper
off, no heat/motion, nothing saved):
- the full boot log from power-on, for the "Boot logo Phys Addr" line;
- at the U-Boot prompt: `help`, `bdinfo` (memory, arch_number, boot params
  address), `printenv`, `help tftpboot`, and whether the USB gadget
  enumerates on a Linux host when `tftpboot` is started;
- `md 0xfa000000 4` (the SMP mailbox), `md 0xfa300530 1`.

**D. More offline work, no printer needed:**
- the vendor `__v7_pj4b_setup` / `proc-v7` code in `Image`: which PJ4B
  auxiliary control bits it sets (needed in mainline too);
- `set_pin_config`, which isn't in kallsyms by that name (inlined):
  pinmux register layout, from `board_do_mpp_config` (c057639c);
- `rohm-i2c` board info: which GPIO the touch IRQ 275 is;
- `upc.ko` (stock modules): the exact ITCM/DTCM window programming for a
  mainline UPC driver;
- the `synopGMAC` init (PHY interface mode, RGMII delays) and the GMAC
  clock setup;
- `mv61x0_nand_probe`: the timing and ECC setup it writes.

---

## 3. Ranked step list

Ordered by value per effort, with what each step unblocks. Steps 1-4
don't depend on the GPL answer; from step 5 on this is route B proper.

| # | Step | Effort | Risk | Unblocks |
|---|---|---|---|---|
| 1 | **Offline RE of the vendor image** (this doc, `tools/kernel_re/`) | done | none | everything below |
| 2 | Collect list A (read-only /proc) and check System.map against `/proc/kallsyms` | 15 min | none | confidence in every address |
| 3 | **Module set for 3.2** with the cdc-acm recipe: ch341, pl2303, squashfs + xz_dec, fuse, tun, zram; layout check each | 1-2 days | low (insmod tests with the user; a power cycle backs out) | CH340/PL2303 sensors; **squashfs NAND install** (project 3 headroom); remote access |
| 4 | insmod tests (cdc-acm first, existing plan; then the set from step 3) | 1 h with the user | low | input shaping over CDC-ACM; the rest of step 3 |
| 5 | Collect lists B and C (user OK / at the console) | 1 h | very low (reads only; U-Boot without saveenv) | TWD/timer choice, the loader choice, NAND ECC, framebuffer base |
| 6 | **Loader:** TFTP over the USB gadget from a Linux host; fallback a `mw.l` serial uploader script (`tools/`) | 0.5-2 days | low | every route-B boot |
| 7 | **Milestone 1:** mainline zImage + appended DTB + initramfs; new timer driver; UP | 2-4 days | low (RAM only) | a working mainline base; armhf userspace testable on the real CPU |
| 8 | Milestone 2: SMP (mailbox + SGI), GPIO driver, SDHCI glue → **root on the SD card** | 3-5 days | low-medium (SD card only; never the 4GB working card, use 2GB-SD) | a full armhf Debian on SD, swap, devtmpfs |
| 9 | Milestone 3: ChipIdea host + USB PHY driver → camera, USB Wi-Fi dongle / USB Ethernet; stmmac on the RJ45 port | 3-5 days | medium (PHY init is guesswork until the list-B values are in) | network without the 8782; the camera without shims |
| 10 | Milestone 4: UPC misc driver (4 ioctls) + DEC UIO + SIC irqchip → **Klipper on mainline** | 2-3 days | medium (UPC reset behaviour must match; no heat until the user is there) | the actual goal: Klipper on a modern kernel |
| 11 | Milestone 5: simple-framebuffer + bu21029 touch + backlight GPIO | 1-2 days | low | the screen UI on mainline |
| 12 | Milestone 6: NAND via marvell_nand (**read-only** at first, compare page reads with the dumps), then 8782 Wi-Fi into mwifiex (or stay with a dongle), RTC, a real install path (kernel in mtd0 is out: signed boot block. Keep the signed U-Boot and replace the uImage? Needs the user, and a restore image is ready in nand_images) | weeks | **high** for writes (ECC/BBT mismatch can corrupt UBI). Reading is safe | stock-free install for owners without an SD card |

**What the GPL source would change, if it comes:** steps 3/4 become "rebuild
the vendor kernel with ARM_THUMB, SWAP, DEVTMPFS, USB_ACM" (days, low
risk), and that fixes armel and swap right away. Route B would still be the
way to a modern kernel; the source would mainly speed up steps 9-12 (USB
PHY, SDHCI, NAND ECC, UPC details).
