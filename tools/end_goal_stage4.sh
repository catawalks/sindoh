#!/bin/sh
# End-goal stage 4 (owner-approved 2026-11-07 morning, autonomous): our kernel
# (m1-nandboot-errata) into mtd0's kernel area, blocks 2-63. U-Boot (blocks 0-1)
# is never written; the guard refuses it anyway. Run on our kernel with the
# root on the card. Prints STAGE4 OK only if every check passes.
set -u
W=/sys/module/marvell_nand/parameters/write_window
IMG=/run/k.uimg
# m1-nandboot-errata (e1ee7e8): the image soak-tested 2026-11-07; its config
# is the nandboot default since then (variants/nandboot.config)
MD5=5b17e2ec0c90ae69c8bed2863c2675f0
SIZE=2814412
UBOOT_MD5=dac6729ae1f8eceecc7bb940bbae7ea1
fail() { echo "STAGE4 FAIL: $*"; echo none > $W; exit 1; }
[ "$(cat $W)" = none ] || fail "window not closed at start ($(cat $W))"
[ -e /dev/ubi0 ] && fail "ubi0 attached"
wget -q -O $IMG http://10.10.0.85:8099/m1-nandboot-errata.uimg || fail "download"
[ "$(md5sum < $IMG | cut -c1-32)" = $MD5 ] || fail "image md5"
[ "$(wc -c < $IMG)" = $SIZE ] || fail "image size"
[ "$(head -c 262144 /dev/mtd0 | md5sum | cut -c1-32)" = $UBOOT_MD5 ] || fail "U-Boot block not the stock one"
grep -q '^mtd0: 00800000 00020000 "kernel"' /proc/mtd || fail "mtd0 layout"
[ "$(cat /sys/class/mtd/mtd0/bad_blocks)" = 0 ] || fail "bad blocks in mtd0"
echo "checks ok; writing"
echo 2,63 > $W || fail "window 2,63"
echo "window $(cat $W)"
flash_erase -q /dev/mtd0 0x40000 62 || fail "erase"
nandwrite -q -p -s 0x40000 /dev/mtd0 $IMG || fail "write"
echo none > $W
echo "window $(cat $W)"
sync; echo 3 > /proc/sys/vm/drop_caches
got=$(dd if=/dev/mtd0 bs=131072 skip=2 2>/dev/null | head -c $SIZE | md5sum | cut -c1-32)
[ "$got" = $MD5 ] || fail "readback $got"
[ "$(head -c 262144 /dev/mtd0 | md5sum | cut -c1-32)" = $UBOOT_MD5 ] || fail "U-Boot block changed"
rest=$(dd if=/dev/mtd0 bs=131072 skip=2 2>/dev/null | tail -c +$((SIZE + 1)) | tr -d '\377' | wc -c)
[ "$rest" = 0 ] || fail "$rest non-0xff bytes after the image"
echo "ecc_failures $(cat /sys/class/mtd/mtd0/ecc_failures)"
rm -f $IMG
echo "STAGE4 OK: mtd0 kernel area = m1-nandboot-errata $MD5"
