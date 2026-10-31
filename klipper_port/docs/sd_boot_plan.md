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

## Rescue card test (2026-10-22)

U-Boot's SD driver can't see the card: `mmcinfo` reports 0 bytes on both
controllers (`mmc list`: mvsdh0, mvsdh1), with or without `mmc rescan`. So
U-Boot loads nothing from SD, and the stock `mv61X0_mmcboot` can't work on
this board either. What works is the **NAND kernel with the root on the
card**, started by hand from the U-Boot prompt:

```
run load_nand
setenv bootargs console=ttyS0,115200n8 ${mtdparts} root=/dev/mmcblk0p1 rootfstype=ext2 rootwait ${bootargs_mv61X0_other} synopGMAC_Mem.ethaddr=${ethaddr_sdh}
bootm ${downld_addr}
```

Result: `/` is `/dev/mmcblk0p1` (ext2), the NAND root (mtd6) is not attached,
and the stock init runs from the card. Card layout and restore notes are in
`install/rescue/README.txt`. This covers a broken NAND **root** (the only
part the Klipper install writes). It needs mtd0 (U-Boot + kernel) to be
intact.

The consequence for way B: U-Boot can't test whether a card is present, so
"boot SD if present, else NAND" can't be decided in U-Boot. It would have to
happen in Linux, for example in the kernel's initramfs or very early in the
NAND root's boot scripts.

## Boot ROM (dumped 2026-10-22)

The mask ROM is 64 KiB at 0xF9F00000 (aliased at 0xFFFF0000 for the vectors).
It's readable from Linux with `tools/memdump.py` (mmap of /dev/mem; `dd`
gets EFAULT). The dump stays outside the repo (vendor code):
`D:\DP200\backup\bootrom\rom_f9f00000.bin`, md5
2bdf7d7dd0939026e349646f36deb781. Build "Fri Sep 09 2011", ARM reset code,
then Thumb-2.

**Boot mode** = strap bits 5, 6 and 7 of 0xF8000004
(`mode = b5 | b6<<1 | b7<<2`). With the stock DIP setting the register
reads 0x21, which is mode 1.

| Mode | Loader |
|---|---|
| 0 | SPI flash, table at 0, 0x10000 or 0x40000 |
| 1 | NAND (if 0xFA000010 bit 17), table copies at erase-block steps, 10 tries |
| 2, 4 | SD on controller 0 (0xF9080000), 4-bit, pins GPIO1 0-5 |
| 5 | eMMC on controller 1 (0xF9080200), 8-bit |
| 6 | SD on controller 0, 4-bit, pins GPIO1 0-1 + GPIO0 3-6 |
| 3, 7 | no storage boot |

After a failed storage boot, every mode ends in a download loop (Marvell
"ACL" protocol: DOWNLOAD, BURN_FLASH, RESET...; probably over USB device)
that also retries SD when card detect changes. It prints nothing while
waiting, which matches the silence seen with the SD DIP setting.

**This board's SD slot** is on controller 0 with pins GPIO1 0-1 and
GPIO0 3-6 set to function 2 (read in Linux). That is exactly **mode 6**.
Mode 6 = binary 110, the inverse of NAND's 001. So "SD = inverse of the
NAND switches" would select it, if those switches are the strap bits.

**SD image layout** the ROM looks for, in mode 2, 4 or 6:
- the boot table (`c1deed1c`, 0x50 bytes) at the start of one of sectors
  0-19 (512-byte steps);
- image offsets in the table are relative to the table;
- the image must start with the `xxxxc0de` code header, then checksum and
  authentication.

Both SDSC (byte addressing) and SDHC are handled. The NAND boot block
(mtd0 bytes 0-0x33800) copied unchanged to **sector 1** keeps the MBR in
sector 0. It was written to 2GB-SD that way and verified, but the boot ROM
still printed nothing after its banner with the SD DIP setting.

Still open: which mode the DIP setting really produces. Mode 2/4 (wrong
pins) or 3/7 (no storage boot) would also be silent; mode 6 with a
working read would at least print "Authentication success" or an error.
The table checksum at 0x04 isn't a plain sum, XOR or CRC32 (not needed for
a verbatim copy).

**DIP test 3 (2026-10-22).** The board silkscreen (SW1, KSD42H) says
NAND = 1 ON, 2 ON, 3 OFF and SD = 1 OFF, 2 OFF, 3 ON; switch 4 selects DC-DC
vs power-management-MCU control. NAND reads as mode 1, so ON = 0 and switch
3 = bit 5, which makes the SD setting **mode 6** (correct for this slot).

With the USB-B port connected to a PC, nothing enumerated (no new USB
device), and pulling and reinserting the card after 30 s gave no output.
So the ROM hangs inside the SD attempt, before its download loop.

A possible cause: in Linux the slot's power doesn't come from the SDHCI
power bit (0xF9080029 = 0x0E, bit 0 clear); the board powers the card
another way, which the ROM may not enable. Sindoh's own recovery
(`recovery/nand_write.sh`) runs from Linux booted off NAND with update files
on the SD card, not from an SD-booted system.

**Verdict:** DIP-switch SD boot doesn't work on this board without further
hardware work (e.g. JTAG on CN3 to see where the ROM stops). The recovery
path is the rescue card started from NAND U-Boot (above).

The first SD attempt (table at sector 0x80, outside sectors 0-19) reset
itself once after ~30 s and then stayed silent.

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

**Open lead (2026-10-31): the SD pads in boot ROM mode 6.** Found after the
DIP tests: with U-Boot from NAND, the SD clock/command pads (GPIO1 pins 0-1)
aren't set up for SD (0x1001 / 0). The data pads (GPIO0 3-6) read 0x41002.
U-Boot's `mmc` only works after pins 0/1 are set to 0x1002
(`uboot_cmd.py --pinmux-sd`). In DIP-SD mode the ROM sets the pins itself,
before U-Boot. If it writes only the function bits and not what 0x1002 /
0x41002 add (bit 12, bit 18: likely pull-up or drive), the card may never
answer the ROM. That would fit the silent hang. Checkable offline: the
values the ROM dump writes to 0xf8041080/84 and 0xf804008c-98 in mode 6. The
file system (ext2/ext4) plays no part there: the ROM reads raw sectors 0-19.
