#!/bin/sh
# Recovery path: boot the STOCK kernel from the SD card through U-Boot,
# without the kernel in mtd0 (2026-11-01). If mtd0's kernel area is ever
# broken, this gives a known-good kernel with Sindoh's own NAND driver to
# rewrite it. RAM only: no NAND write, no saveenv.
#
# The image (stock uImage from pa6170_rodin_nand.bin at 0x40000, 6928784
# bytes, crc32 9f0bc791) is the contiguous, immutable file
# /var/backups/stock_kernel.uimg on the 4 GB card's partition 1, at raw
# sector 4296704 (ext4 block 536064). Check it again with filefrag if the
# card is ever rebuilt.
# usage: tools/sd_stock_boot.sh [CAPTURE_SECONDS]
set -e
secs=${1:-120}
here=$(dirname "$0")
SECTOR=4296704
SIZE=6928784
CRC=9f0bc791
blocks=$(( (SIZE + 511) / 512 ))

# 1. stop the stack cleanly (stock: the chroot's start script; mainline: rc.dp200)
py -3.15t "$here/serial_watch.py" COM3 30 'if [ -x /mnt/sd/dp200/dp200-start.sh ] && [ -d /app ]; then /mnt/sd/dp200/dp200-start.sh stop; else /etc/dp200/rc.dp200 stop; fi; sync; echo STOPPED' | grep -a STOPPED | tail -1

# 2. U-Boot: load the stock kernel from the card, check its CRC
py -3.15t "$here/uboot_cmd.py" COM3 --catch | tail -1
py -3.15t "$here/uboot_cmd.py" COM3 --pinmux-sd | tail -1
res=$(py -3.15t "$here/uboot_cmd.py" COM3 "mmcinfo" \
	"mmc read 2000000 $(printf %x $SECTOR) $(printf %x $blocks)" \
	"crc32 2000000 $(printf %x $SIZE)")
echo "$res" | tail -2
if ! echo "$res" | grep -qi "==> *$CRC"; then
	echo "stock kernel on the card is not crc $CRC: resetting"
	py -3.15t "$here/uboot_cmd.py" COM3 --reset | tail -1
	exit 1
fi

# 3. stock bootargs in RAM (refuses to go on unless they are complete), boot
if ! py -3.15t "$here/uboot_cmd.py" COM3 --stock-bootargs | grep -q "BOOTARGS OK"; then
	echo "stock bootargs not set: resetting"
	py -3.15t "$here/uboot_cmd.py" COM3 --reset | tail -1
	exit 1
fi
py -3.15t "$here/uboot_cmd.py" COM3 --bootm 2000000 "$secs"
