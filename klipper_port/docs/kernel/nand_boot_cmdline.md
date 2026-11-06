# Our kernel in mtd0: the stock U-Boot command line, and the size budget

Offline check, 2026-11-06 (end_goal_install_plan.md, stage 4). Nothing was
booted or written.

## What stock U-Boot does (env unchanged, docs/kernel/uboot_facts.txt)

`bootcmd` -> `mv61X0_nandboot` = `run setbootargs_nand; run load_nand;
bootm 0x400000`:
- `load_nand`: `nand read 0x400000 0x40000 0x7C0000` (mtd0 blocks 2-63,
  bad blocks skipped);
- `bootm` of a legacy uImage: checks the header and data CRCs, copies the
  data to the load address (ours: 0x8000, `-C none`), passes ATAGS in r2
  (no `fdt`, no `bootz` in this U-Boot);
- the command line it passes (env values filled in):

```
console=ttyS0,115200n8
mtdparts=mv61x0_nand:0x800000(kernel),0x20000(u-boot-env),0x80000(bbt)ro,0x100000(boot-logo),0x800000(backup),0xC800000(recovery),-(filesystem)
ubi.mtd=filesystem root=ubi0:filesystem rootfstype=ubifs
BUSFREQ=200000000 ASICREV=C0 lxkearlycon=uart8250,mmio32,0xf8060000
synopGMAC_Mem.ethaddr=<ethaddr_sdh> mv61tft.boot_time=17 mv61tft.bar_color=0
```

## How our kernel treats it today (m1.config)

`ARM_APPENDED_DTB` + `ARM_ATAG_DTB_COMPAT` + `..._CMDLINE_EXTEND`: the
decompressor puts the ATAG memory size into the DT and **appends** the stock
line to the DT's bootargs. Item by item:

| Item | Effect on our kernel |
|---|---|
| `console=ttyS0,115200n8` | right (the UART is ttyS0) |
| `mtdparts=...` | ignored: `MTD_CMDLINE_PARTS` is off, the DT partitions are used. They have the same boundaries (88pa6170-dp200.dts: kernel 0-8 MB, env, bbt, boot-logo, backup, recovery, filesystem from 0xd9a0000). Keep it off: with it on, the parser would need the mtd name `mv61x0_nand`, and the DT is the one place the read-only flags live |
| `ubi.mtd=filesystem` | **a problem.** UBI is built in (full.config), so it attaches mtd6 during boot, before the initramfs can choose a root. That is the boot-time UBI scan that coincided with the 8782's 0xa9 timeout in D2. It also leaves mtd6 attached when the revert needs it detached |
| `root=ubi0:filesystem rootfstype=ubifs` | ignored while the built-in initramfs has an /init; the init can read it from /proc/cmdline |
| `BUSFREQ`, `ASICREV`, `lxkearlycon`, `synopGMAC_Mem.*`, `mv61tft.*` | unknown: a warning, then passed to init's environment. Harmless |

## Decision for the NAND-boot image (VARIANT=nandboot)

- **`CONFIG_CMDLINE_FORCE` with our own `CONFIG_CMDLINE`**:
  `console=ttyS0,115200n8 marvell_nand.write_window=1741,4091 panic=10 consoleblank=0`.
  The stock line is then ignored completely, and no U-Boot env change is
  needed. `ARM_ATAG_DTB_COMPAT` stays on, so the memory size still comes
  from U-Boot's ATAG (mem=512 MiB).
- **No `ubi.mtd`:** the initramfs attaches mtd6 itself, after the 8782
  firmware is up (see the Wi-Fi notes in debian_root_boot.md).
- **The window opens mtd6 at boot** (patch 0010 v2), so the root can be
  mounted read-write. mtd0 and mtd3 are opened only by the revert or a
  kernel update, around their writes.
- **Lost by ignoring the stock line:** `ethaddr_sdh` (the Ethernet MAC).
  The initramfs can read it from mtd1 (read-only) if Ethernet needs it
  there; stmmac otherwise picks a random MAC.

## Size

The budget is 0x7C0000 = 8,126,464 bytes (7.75 MiB), from 0x40000 to the
end of mtd0. Only the uImage's data counts: bootm checks the CRC over the
header's data size and ignores the rest of the read.

| Part | Size |
|---|---|
| m1-full uImage today (kernel + DTB + initramfs with busybox, wpa_supplicant, iw, upctool, the 8782 firmware), XZ | 3,065,768 bytes |
| m1-full-nandw | 3,068,488 bytes |
| planned additions: mtd-utils (ubiformat, flash_erase; static, ~0.3 MB raw), the boot/revert scripts | ~+0.1-0.2 MB compressed |
| expected nandboot uImage | **~3.2-3.3 MB, about 40 % of the budget** |

**Measured (2026-11-06, with mtd-utils):** m1-nandboot.uimg = 2,649,276
bytes (md5 eea44879...), **33 % of the budget** (5.2 MB to spare). It is
smaller than m1-full because it has no 8782 firmware, wpa_supplicant or
iw. The 11 static mtd-utils tools are 0.8 MB unpacked and +67 KB in the
XZ image; the build without them was 2,582,068 bytes.

Also checked:
- bootm copies the data from 0x400040 to 0x8000; for images over ~4 MB the
  areas overlap, and U-Boot's memmove handles that. The zImage then moves
  itself above the decompressed kernel.
- A bad block among 2-63 makes U-Boot's read skip it and run on into
  mtd1/mtd2. That is harmless for a ~3.3 MB image (nandwrite skips the same
  blocks). This printer has 64/64 good blocks in mtd0.
- **The 8782 firmware must not be in the published image** (Marvell
  binary). The nandboot image is built without it (`NOFW=1`): mwifiex's
  download fails at boot, and after switch_root the root's
  /lib/firmware/mrvl copy (the installer copies it from the stock root)
  plus a USB re-enumeration (as init.mainline already does) bring Wi-Fi up.
