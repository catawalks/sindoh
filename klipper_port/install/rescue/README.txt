DP200 RESCUE CARD
=================

This card boots the stock Sindoh kernel with this card as the root
filesystem (ext2, partition 1). Nothing on the printer's NAND is used or
changed unless you do it. Login: the serial console (115200) or the USB/WiFi
shell as usual; the prompt says RESCUE.

Card layout
  sector 1      boot table + signed U-Boot (copy of NAND mtd0 0..0x33800) -
                for the boot ROM when the DIP switches select SD (it looks
                at sectors 0-19). Not yet seen to boot.
  sector 0x80   older copy of the same, partly overwritten - unused
  sector 0x800  stock kernel uImage (copy of NAND mtd0 0x40000, 0x69b990 bytes)
  partition 1   from sector 32768: this rescue root (copy of the stock root)

Starting it (from the U-Boot prompt; press a key during "Hit any key"):
  run load_nand
  setenv bootargs console=ttyS0,115200n8 ${mtdparts} root=/dev/mmcblk0p1 rootfstype=ext2 rootwait ${bootargs_mv61X0_other} synopGMAC_Mem.ethaddr=${ethaddr_sdh}
  bootm ${downld_addr}
The kernel comes from NAND mtd0 (the Klipper install never writes it), the
root from this card. U-Boot's own SD driver can't see the card (mmcinfo shows
0 bytes on mvsdh0 and mvsdh1), so the kernel copy at sector 0x800 is only a
spare for restoring mtd0. Nothing is saved: the next reset boots NAND as usual.
(U-Boot's command line is short, so the NAND layout and SoC options come from
its own variables mtdparts, bootargs_mv61X0_other and ethaddr_sdh.)
Tested 2026-10-22: root /dev/mmcblk0p1 ext2, prompt RESCUE#, NAND root (mtd6)
not attached.

Restoring NAND (see /restore):
  mtd0.bin      NAND "kernel" partition (boot table, signed U-Boot, kernel),
                as read with nanddump -o -b. Write back ONLY if mtd0 is damaged:
                  flash_erase /dev/mtd0 0 0 && nandwrite -p /dev/mtd0 /restore/mtd0.bin
  Further images (stock root filesystem etc.) are added from the full chip
  dump made with a T48 programmer.

Removing a broken Klipper hook from the NAND root (when Klipper won't start):
  mkdir -p /mnt/nand && mount -t ubifs ubi0:filesystem /mnt/nand   (if not attached: ubiattach -m 6)
  cp /mnt/nand/etc/profile.stock /mnt/nand/etc/profile
  rm -f /mnt/nand/DEBUG_MACHINE /mnt/nand/etc/dp200-boot.sh
