# NAND layout and boot path

The one home for these facts. Other documents link here.

## Partitions (`/proc/mtd`, 128 KiB erase blocks)

| mtd | Name | Size | Holds | May we write it? |
|---|---|---|---|---|
| mtd0 | kernel | 8 MB | Blocks 0-1: U-Boot (stock, md5 of the first 256 KiB `dac6729a...`). Blocks 2-63: the kernel image U-Boot boots | Blocks 2-63 only, with the owner's OK per write, by `tools/mtd0_kernel_update.sh`. **Never blocks 0-1.** |
| mtd1 | u-boot-env | 128 KiB | U-Boot environment (holds the Ethernet MAC) | **Never** (no saveenv) |
| mtd2 | bbt | 512 KiB | Bad-block table | **Never** |
| mtd3 | boot-logo | 1 MB | Boot logo | Not by us today |
| mtd4 | backup | 8 MB | Sindoh's per-printer data (karas.db copy: model, serial, calibration) | **Never** |
| mtd5 | recovery | 200 MB | Sindoh's factory recovery set (UBI volume `recovery`: stock kernel, root, apps) | **Never.** It is how a printer gets back to stock. |
| mtd6 | filesystem | 294 MB | The root: stock root (+ `/klipper` on a stick install), or our UBIFS root `ubi0:filesystem` | Yes, it is the root |

## Boot path

1. U-Boot (unchanged, stock environment) reads 0x7C0000 bytes from
   mtd0 + 0x40000 and boots it with the stock bootargs.
2. Our kernel ignores those bootargs (`CONFIG_CMDLINE_FORCE`); its own
   command line is in [kernel/nand_boot_cmdline.md](kernel/nand_boot_cmdline.md).
3. Our initramfs (`dp200-init`) mounts the root: `ubi0:filesystem` on mtd6.
   A card carrying the marker `/.dp200-root` is used as the root instead;
   that is for development and recovery only.
4. `/etc/dp200/init.mainline` loads the modules, starts the network and
   runs `/etc/dp200/rc.dp200 start` (Klipper, Moonraker, screen, camera).

Reboot from our root with `busybox reboot` (there is no `/sbin/reboot`).

## Write rules

- The mainline NAND driver refuses every program/erase outside its
  **write window** (`/sys/module/marvell_nand/parameters/write_window`).
  The normal window is `1741,4091` (mtd6). The mtd0 kernel area (`2,63`)
  is opened only inside `tools/mtd0_kernel_update.sh`, which checks the
  image md5 and size, the U-Boot block before and after, bad blocks, and
  reads the image back.
- RAM-boot every new kernel before it goes to mtd0
  (`tools/sd_raw_install.sh` puts it in the 4 GB card's gap,
  `tools/sd_raw_boot.sh` boots it from U-Boot without writing anything).
- Never delete `pa6170_rodin_nand.bin` or the stock `auto_update.sh`.
- A power cut during an mtd0 write leaves no bootable kernel; recovery is
  the serial console, as with Sindoh's own updates.

Back to stock: [nand_restore.md](nand_restore.md) and
[kernel/revert_to_stock_plan.md](kernel/revert_to_stock_plan.md).
What is in NAND on each printer today: [STATUS.md](STATUS.md).
