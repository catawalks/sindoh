#!/bin/sh
# ubi variant: attach the stock root UBI (mtd6 "filesystem") read-only and
# mount its UBIFS read-only. Three NAND write locks underneath (patch 0006);
# UBI sees no MTD_WRITEABLE and runs in ro_mode; UBIFS is mounted -o ro.
dmesg | grep -i 'nand\|mtd\|read-only'
cat /proc/mtd
echo "--- ubiattach mtd6 (filesystem):"
ubiattach -m 6 /dev/ubi_ctrl
dmesg | grep -i 'ubi' | tail -n 25
echo "--- ubi0 ro_mode (must be 1): $(cat /sys/class/ubi/ubi0/ro_mode 2>/dev/null)"
for v in /sys/class/ubi/ubi0_*; do
	[ -d "$v" ] && echo "  $(basename $v) name=$(cat $v/name) type=$(cat $v/type) size=$(cat $v/data_bytes)"
done
mkdir -p /mnt/ubi
if mount -t ubifs -o ro ubi0:filesystem /mnt/ubi; then
	grep ubi /proc/mounts
	ls /mnt/ubi
	echo "--- stock file md5s (expected from the rootfs dumps):"
	for f in lib/libc-2.15.so:b33dd0c4b559a660eed49d9efe41cfb3 app/upc.ko:d57c4203070b1206184178d4e3ab6e5b bin/busybox:8786fcf018c2c0c785412abd50ea3689 etc/inittab:103b9da89920e003ccab6ea2ea3178ae; do
		n=${f%%:*} e=${f#*:}
		h=$(md5sum /mnt/ubi/$n 2>/dev/null | cut -d' ' -f1)
		[ "$h" = "$e" ] && echo "  $n OK" || echo "  $n $h (expected $e)"
	done
	df -k /mnt/ubi
else
	echo "--- mount failed"
fi
echo "--- ECC statistics (corrected / failed) on mtd6:"
cat /sys/class/mtd/mtd6/corrected_bits /sys/class/mtd/mtd6/ecc_failures 2>/dev/null
