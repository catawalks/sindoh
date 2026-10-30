#!/bin/sh
# nand variant: read-only checks (patch 0006, CONFIG_MTD_RAW_NAND_READ_ONLY)
dmesg | grep -i 'nand\|mtd\|marvell-nfc\|read-only'
cat /proc/mtd
echo "--- mtd0 flags (must not contain 'writeable'):"
for d in /sys/class/mtd/mtd[0-9]; do
	echo "  $(basename $d) $(cat $d/name) type=$(cat $d/type) flags=$(cat $d/flags) size=$(cat $d/size) writesize=$(cat $d/writesize) erasesize=$(cat $d/erasesize) bad=$(cat $d/bad_blocks 2>/dev/null)"
done
echo "--- md5 of the small partitions (raw reads, ECC off):"
for n in 0 3; do
	echo "  mtd$n $(dd if=/dev/mtd$n bs=131072 2>/dev/null | md5sum | cut -d' ' -f1)"
done
echo "    stock dumps (ECC-corrected): mtd0 298b7390ccb500998661949c02ea68f8, mtd3 e106bfe3be8f2e08044222c71a982c28"
