# SD-card boot (DIP switch / U-Boot) - investigation

Status 2026-10-20: read-only investigation (U-Boot environment from the NAND
dump, kernel config, SD card layout). Nothing was changed. The main install
path for owners stays the USB stick → internal NAND (see usb_installer.md).
SD boot is the alternative for owners who have a card, and the test bed for a
newer kernel (kernel_research.md).

## How the DP200 boots

1. **Boot ROM.** DIP switch SW1 selects where it loads U-Boot from. From
   the earlier analysis (dp200-findings-and-plan.md):
   - NAND = switches 1-8 ON, 2-7 ON, 3-6 OFF;
   - SD = the inverse.
2. **U-Boot 2011.09** (Nov 2016), at the start of NAND mtd0. It waits
   `bootdelay=1` s for a key on ttyS0 (115200), then runs
   `bootcmd` → `bootcmd_select` → `mv61X0_nandboot`:
   `nand read 0x400000 0x40000 0x7C0000` (the kernel uImage in mtd0), then
   `bootm` with `ubi.mtd=filesystem root=ubi0:filesystem rootfstype=ubifs`.
3. **Kernel 3.2.** It has an embedded initramfs
   (`CONFIG_INITRAMFS_SOURCE="../root_fs"`), then mounts the UBIFS root.
   `/etc/profile` starts the Sindoh app (or our hook, with `/DEBUG_MACHINE`).

The environment (mtd1, CRC OK, decoded from `Sindoh_raw_dump/recovery/u-boot-env.bin`)
**already contains an SD boot**:

```
mv61X0_mmcboot   = run setbootargs_mv61x0; run load_mmc_big_part; bootm ${downld_addr}
load_mmc_big_part= mmcinfo; mmc read ${downld_addr} 0x202 0xD000
setbootargs_mv61x0 = ... ${mtdparts} root=/dev/mmcblk0p2 rootfstype=ext2 ... mv61fb.lcd_type=${lcd_type}
erase_mmc_uboot  = mw.l 0 0; mmc write 0 0 0x90 1; mmc write 0 0 0x80 1; reset
erase_mmc_env    = mmc write 0 0x28000 1
```

So an SD-booted system means:
- a **uImage kernel stored raw** from sector 0x202 (max 0xD000 sectors = 26 MB);
- **root on partition 2**, mounted as ext2;
- when U-Boot itself comes from SD (DIP), it sits at sector 0x80/0x90 and
  its environment at sector 0x28000 (inferred from the `erase_mmc_*`
  commands).

## Console speeds (measured 2026-10-21, tools/uboot_baud_scan.py)

- **Boot ROM loader ("BootCode"): ~120 000 baud** (not a standard rate; 120000
  decodes cleanly, 125000/128000 almost). It's the "garbage" seen at
  115200 during the first second after power-on/reset. Its output:
  `BootCode: Ver = 2011-9-9, v.1 program:12, platform:1` /
  `Processor speed 400, Bus speed 200, ASIC ID 0x617021` /
  **`Authentication success`** / `ElfImage OK. Loading...` / 8 ×
  `Load code addr F92…` / `Start the image at 0xF92808..`
- **U-Boot and Linux: 115200** (although the env has `baudrate=38400`).
- Timing after `reset` at the U-Boot prompt: boot ROM output from 0 to
  ~1.0 s, U-Boot banner at ~1.04 s, "Hit any key to stop autoboot" at
  ~3.9 s, with a 1 s window. A Linux `reboot` reaches the countdown in ~7 s.
- **The boot ROM authenticates the U-Boot ELF image** ("Authentication
  success"). An SD-boot card (way C) must therefore carry Sindoh's signed
  U-Boot image unchanged; a self-built U-Boot would likely be refused. That
  doesn't affect ways A/B, where Sindoh's U-Boot loads our kernel.
- The U-Boot prompt is `# `; `version` reports U-Boot 2011.09-svn22695 and
  Marvell GCC 4.6.4.

## Boot block and U-Boot (from the mtd0 dump, 2026-10-22)

mtd0 starts with a boot table (big-endian):

| Offset | Value | Meaning |
|---|---|---|
| 0x00 | `c1deed1c` | magic |
| 0x04 | `6c30cca4` | checksum? |
| 0x10 | type 0, offset 0x60, size 0x332b4 | signed U-Boot blob |
| 0x30 | type 1, offset 0x40000, size 0x69b990 | kernel uImage (what `load_nand` reads) |
| 0x60 | `8120c0de`, then 256 bytes | signature header + an RSA-2048-sized signature |
| 0x170 | 0x33190 | U-Boot ELF length; the ELF starts at 0x180 |

U-Boot strings show **only `env_nand.c`**: the environment always comes from
NAND (mtd1), even when the boot ROM loaded U-Boot from SD. So a DIP-switch
SD boot of U-Boot alone still boots the NAND kernel and root. It protects
against a damaged **mtd0**, which the Klipper NAND install never writes. A
damaged **NAND root** needs a rescue Linux on the SD card, started by U-Boot,
either:
- by hand (key at the prompt, then `mmc read` a kernel + `bootm` with
  root=/dev/mmcblk0pN); or
- automatically, by changing `bootcmd_select` in mtd1 to boot an SD rescue
  kernel when present and NAND otherwise. A corrupt env falls back to the
  built-in default, which is NAND boot, so this is safe.

Layout conflict: the stock `mv61X0_mmcboot` reads the kernel from sector 0x202,
which overlaps a U-Boot copy at sector 0x80 (it ends at ~0x21A). A rescue card
therefore puts the kernel at its own offset (e.g. 1 MiB, sector 0x800) and uses
its own command.

## Constraints found

- **Partition layout:** this printer's card has partition 1 at sector
  8192, inside the 0x202–0xD202 kernel area. An SD-boot card needs its own
  layout: raw kernel area first, partitions from ≥ 32 MiB (sector 65536),
  and the root as **partition 2**.
- **Filesystem:** `EXT2_FS=y`, `EXT3_FS=y`, but `EXT4_FS=m`. The root must
  be **ext3 without ext4 features** (made with `mkfs.ext3`; the ext2
  driver mounts it, since `has_journal` is only a compat feature) or ext2.
  The current card is ext4 (it's only mounted after boot, when the module
  is loaded).
- **Kernel:** the stock uImage can be taken from mtd0 at 0x40000 (in the
  NAND dump). Same kernel, same limits (no Thumb, no swap).
- **No Sindoh userland when booting from SD.** Our root would need its own:
  - init (BusyBox init or sysvinit; systemd is too new for 3.2);
  - modules: `upc.ko`, WiFi `usb8xxx`/`mlan` + firmware from
    `/lib/modules/8782`, uvcvideo, ext4;
  - WiFi setup (wpa_supplicant + the saved network);
  - mdev/hotplug.

  These are all copied from the stock root, so the SD system becomes a full
  OS, not a chroot.

## Three ways to start it

| Way | Flash writes | Who can do it | Notes |
|---|---|---|---|
| A. U-Boot prompt: key during the 1 s delay, then `run mv61X0_mmcboot` | none | needs the serial console | Best for development (e.g. testing kernels). Lost at the next power-on. |
| B. Change `bootcmd_select` in the U-Boot env, e.g. try SD then NAND | mtd1 (128 KB env), reversible | USB installer could do it (needs `fw_setenv` or a raw env write with CRC) | Fallback behaviour must be tested: does `mmc read` fail cleanly without a card, and does this U-Boot's shell support `||`? |
| C. DIP switch to SD: the boot ROM loads U-Boot from the card | **none** | owner flips switches | Truly flash-free: DIP=NAND is stock, DIP=SD is Klipper. Needs U-Boot (from the NAND dump) written to the card in the boot ROM's format (sector 0x80/0x90; header format unknown) and a U-Boot env on the card (sector 0x28000) with `bootcmd_select=run mv61X0_mmcboot`. |

## Recommended next steps

1. **With the user at the serial console (no heat, no motion):**
   1. interrupt U-Boot;
   2. record `printenv`, `help`, `version`, and whether `mmc`, `fatload`,
      `ext2load` and `bootz` exist;
   3. test hush `||` with a harmless `false || echo ok`.

   Nothing is saved.
2. Prepare a second SD card (not the working one), all from the PC or the
   chroot without touching NAND:
   - kernel raw at 0x202;
   - p1 small vfat (optional);
   - p2 ext3 root.
3. Boot it once with way A. Fix init, modules and WiFi until Klipper comes
   up.
4. Then try way C. Write U-Boot to the card, and compare with the boot ROM
   header seen at NAND offset 0 to learn the format. **Experimental; only
   with the user present.**
