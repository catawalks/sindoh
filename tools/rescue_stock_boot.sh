#!/bin/sh
# Boot the stock Sindoh system from the 2GB-SD rescue card into RAM
# (2026-11-07): the stock kernel copy at sector 0x800 (0x69b990 bytes) and
# the rescue root (a copy of the stock root, ext2 partition 1). For
# comparing stock behaviour (e.g. the 8782 Wi-Fi start) with our system
# after mtd0 holds our kernel. U-Boot: pin selects and bootargs in RAM only,
# no saveenv; nothing is written to NAND or the card. The next plain reset
# boots NAND as usual.
# usage: tools/rescue_stock_boot.sh [CAPTURE_SECONDS]
set -e
secs=${1:-90}
here=$(dirname "$0")
# stop our stack if our system runs (harmless on stock: no rc.dp200)
py -3.15t "$here/serial_watch.py" COM3 30 '[ -x /etc/dp200/rc.dp200 ] && /etc/dp200/rc.dp200 stop; sync; echo STOPPED' | grep -a STOPPED | tail -1
py -3.15t "$here/uboot_cmd.py" COM3 --catch | tail -1
py -3.15t "$here/uboot_cmd.py" COM3 --pinmux-sd | tail -1
res=$(py -3.15t "$here/uboot_cmd.py" COM3 "mmcinfo" "mmc read 2000000 800 3500" "iminfo 2000000")
echo "$res" | grep -a -i -E "Image Name|Data Size|Verifying|OK|Bad" | tail -4
if ! echo "$res" | grep -a -q "Verifying Checksum ... OK"; then
	echo "no valid stock kernel at the card's sector 0x800; resetting"
	py -3.15t "$here/uboot_cmd.py" COM3 --reset | tail -1
	exit 1
fi
py -3.15t "$here/uboot_cmd.py" COM3 --rescue-bootargs | grep -a -q "BOOTARGS OK" ||
	{ echo "bootargs not set; resetting"; py -3.15t "$here/uboot_cmd.py" COM3 --reset | tail -1; exit 1; }
py -3.15t "$here/uboot_cmd.py" COM3 --bootm 2000000 "$secs"
