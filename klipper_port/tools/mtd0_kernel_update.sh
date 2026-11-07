#!/bin/sh
# Replace our kernel in mtd0's kernel area (blocks 2-63) from our running
# system (2026-11-07). Runs on our kernel with the root on mtd6 (its window
# 1741,4091 stays open alongside 2,63) or on a marked card (window none, mtd6
# detached). U-Boot (blocks 0-1) is never written; the guard refuses it
# anyway. The window is put back exactly as it was. Same checks as
# end_goal_stage4.sh: image md5 and size, stock U-Boot block before and
# after, readback md5, 0xff after the image. Prints KUPDATE OK only if every
# check passes. Needs the owner's OK like every NAND write.
# usage (on the printer): sh mtd0_kernel_update.sh URL MD5 SIZE
set -u
W=/sys/module/marvell_nand/parameters/write_window
IMG=/run/k.uimg
URL=$1 MD5=$2 SIZE=$3
UBOOT_MD5=dac6729ae1f8eceecc7bb940bbae7ea1
W0=$(cat $W)
fail() { echo "KUPDATE FAIL: $*"; echo "$W0" > $W; echo "window $(cat $W)"; exit 1; }
case "$W0" in
none) [ -e /dev/ubi0 ] && fail "ubi0 attached with the window closed"; OPEN="2,63" ;;
1741,4091) [ "$(awk '$2 == "/" { print $1 }' /proc/mounts)" = ubi0:filesystem ] || fail "mtd6 window open but / is not mtd6"; OPEN="1741,4091;2,63" ;;
*) fail "unexpected window at start: $W0" ;;
esac
wget -q -O $IMG "$URL" || fail "download"
[ "$(md5sum < $IMG | cut -c1-32)" = $MD5 ] || fail "image md5"
[ "$(wc -c < $IMG)" = $SIZE ] || fail "image size"
[ $SIZE -lt $((62 * 131072)) ] || fail "image larger than the kernel area"
[ "$(head -c 262144 /dev/mtd0 | md5sum | cut -c1-32)" = $UBOOT_MD5 ] || fail "U-Boot block not the stock one"
grep -q '^mtd0: 00800000 00020000 "kernel"' /proc/mtd || fail "mtd0 layout"
[ "$(cat /sys/class/mtd/mtd0/bad_blocks)" = 0 ] || fail "bad blocks in mtd0"
sync
echo "checks ok; writing"
echo "$OPEN" > $W || fail "window $OPEN"
echo "window $(cat $W)"
flash_erase -q /dev/mtd0 0x40000 62 || fail "erase"
nandwrite -q -p -s 0x40000 /dev/mtd0 $IMG || fail "write"
echo "$W0" > $W
echo "window $(cat $W)"
sync; echo 3 > /proc/sys/vm/drop_caches
got=$(dd if=/dev/mtd0 bs=131072 skip=2 2>/dev/null | head -c $SIZE | md5sum | cut -c1-32)
[ "$got" = $MD5 ] || fail "readback $got"
[ "$(head -c 262144 /dev/mtd0 | md5sum | cut -c1-32)" = $UBOOT_MD5 ] || fail "U-Boot block changed"
rest=$(dd if=/dev/mtd0 bs=131072 skip=2 2>/dev/null | tail -c +$((SIZE + 1)) | tr -d '\377' | wc -c)
[ "$rest" = 0 ] || fail "$rest non-0xff bytes after the image"
echo "ecc_failures $(cat /sys/class/mtd/mtd0/ecc_failures)"
rm -f $IMG
echo "KUPDATE OK: mtd0 kernel area = $MD5"
