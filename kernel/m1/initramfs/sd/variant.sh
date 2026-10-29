#!/bin/sh
# sd variant: wait for the card, make it read-only, mount nothing
i=0
while [ ! -e /sys/block/mmcblk0 ] && [ $i -lt 10 ]; do
	sleep 1
	i=$((i + 1))
done
dmesg | grep -i -E 'mmc|sdhci'
# The stock kernel routes the SD pins itself (function 2, bits 2:0 of each
# pin configuration word); mainline does not, so show what U-Boot left
echo "--- SD pin mux (bits 2:0 must be 2): $(for a in 0xf804008c 0xf8040090 0xf8040094 0xf8040098 0xf8041080 0xf8041084; do devmem $a; done)"
if [ -e /sys/block/mmcblk0 ]; then
	echo 1 > /sys/block/mmcblk0/force_ro
	echo "--- mmcblk0: $(cat /sys/block/mmcblk0/size) sectors, read-only $(cat /sys/block/mmcblk0/ro) (1 = yes)"
	cat /proc/partitions
	echo "--- nothing is mounted. Read-only: mount -o ro,noload /dev/mmcblk0p1 /mnt (ext4)"
else
	echo "--- no card found on mmc0"
fi
