#!/bin/sh
# Boot the mainline Debian kernel stored raw on the SD card (2026-10-31): the
# fast path for the 4 GB card, whose ext4 U-Boot 2011 can't read. The image
# (m1-debian.uimg, about 3 MB) sits in the gap before partition 1, from
# sector 64 (put it there with tools/sd_raw_install.sh). Each boot: stop the
# Klipper stack, catch U-Boot, route the SD pins (RAM only, approved), mmc
# read, compare the CRC with the local build, bootm. About 1 minute instead
# of the 11-minute serial upload. Nothing is written to NAND or the U-Boot
# env.
# usage: tools/sd_raw_boot.sh [IMAGE] [CAPTURE_SECONDS]
#   IMAGE: the .uimg that was installed (default D:/DP200/kernel/out/m1-debian.uimg)
set -e
img=${1:-D:/DP200/kernel/out/m1-debian.uimg}
secs=${2:-60}
here=$(dirname "$0")
SECTOR=64
[ -f "$img" ] || { echo "$img: not found"; exit 1; }
size=$(wc -c < "$img")
blocks=$(( (size + 511) / 512 ))
crc=$(py -3.15t -I -c "import sys, zlib; print('%08x' % zlib.crc32(open(sys.argv[1], 'rb').read()))" "$img")

# 1. stop the stack cleanly (stock: the chroot's start script; mainline: rc.dp200)
py -3.15t "$here/serial_watch.py" COM3 30 'if [ -x /mnt/sd/dp200/dp200-start.sh ] && [ -d /app ]; then /mnt/sd/dp200/dp200-start.sh stop; else /etc/dp200/rc.dp200 stop; fi; sync; echo STOPPED' | grep -a STOPPED | tail -1

# 2. U-Boot: load the image from the card and check it is this build
py -3.15t "$here/uboot_cmd.py" COM3 --catch | tail -1
py -3.15t "$here/uboot_cmd.py" COM3 --pinmux-sd | tail -1
res=$(py -3.15t "$here/uboot_cmd.py" COM3 "mmcinfo" \
	"mmc read 2000000 $(printf %x $SECTOR) $(printf %x $blocks)" \
	"crc32 2000000 $(printf %x "$size")")
echo "$res" | tail -2
if ! echo "$res" | grep -qi "==> *$crc"; then
	echo "the card's image (sector $SECTOR) is not $img (crc $crc):"
	echo "resetting to stock; install it with tools/sd_raw_install.sh"
	py -3.15t "$here/uboot_cmd.py" COM3 --reset | tail -1
	exit 1
fi

# 3. boot it
py -3.15t "$here/uboot_cmd.py" COM3 --bootm 2000000 "$secs"
