#!/bin/sh
# End-goal stage 5 (owner-approved 2026-11-07 morning, autonomous): this
# printer's root (the 4 GB card's Debian root, trimmed as the runtime
# payload) into mtd6 as UBIFS. The stock 2020 mtd6 was dumped raw first
# (nand_images/stage2/mtd6_raw_oob_stock2020_20261107.bin, md5 8f7a1abf).
# Run on our kernel with the root on the card. The card stays the root
# (its /.dp200-root marker) until a separate step removes the marker.
# Prints STAGE5 OK only if every check passes.
set -u
W=/sys/module/marvell_nand/parameters/write_window
NEW=/run/newroot
X=/run/stage5.exclude
fail() { echo "STAGE5 FAIL: $*"; mountpoint -q $NEW && umount $NEW; [ -e /dev/ubi0 ] && ubidetach -d 0; echo none > $W; exit 1; }
[ "$(cat $W)" = none ] || fail "window not closed at start"
[ -e /dev/ubi0 ] && fail "ubi0 attached"
[ -f /.dp200-root ] || fail "root is not the marked card"
[ "$(awk '$2 == "/" { print $1 }' /proc/mounts)" = /dev/root ] || [ "$(awk '$2 == "/" { print $3 }' /proc/mounts)" = ext4 ] || fail "root not the card"
grep -q '^mtd6: 12660000 00020000 "filesystem"' /proc/mtd || fail "mtd6 layout"
# the payload's runtime list, but this printer keeps its own Wi-Fi networks
# and calibration (local copy, never shipped); card-only things stay out
grep -v -e wpa_supplicant /usr/src/dp200/klipper_port/install/nand/runtime.exclude > $X || fail "exclude list"
cat >> $X <<'EOF'
./proc/*
./sys/*
./dev/*
./run/*
./tmp/*
./mnt/*
./media/*
./var/tmp/*
./var/backups
./payload_out
./payload
./alpine
./payload_stage.*
./lost+found
./.dp200-root
./.dp200-revert
./bootrom
./kb_out
EOF
# every plain file in / is the card's (stock images, tarballs, dumps, logs):
# the Debian root needs none of them
find / -maxdepth 1 -type f | sed 's|^/|./|' >> $X
kb=$(( $(tar -C / --one-file-system --exclude-from=$X -cf - . | wc -c) / 1024 ))
echo "tree to copy: $kb KiB unpacked"
[ $kb -gt 50000 ] && [ $kb -lt 307200 ] || fail "unexpected size $kb KiB"
echo 1741,4091 > $W || fail "window"
echo "window $(cat $W)"
ubiformat /dev/mtd6 -y -q -O 2048 || fail "ubiformat"
ubiattach -m 6 -d 0 /dev/ubi_ctrl > /dev/null || fail "ubiattach"
ubimkvol /dev/ubi0 -N filesystem -m > /dev/null || fail "ubimkvol"
mkdir -p $NEW
mount -t ubifs ubi0:filesystem $NEW || fail "mount"
echo "copying (GNU tar, excludes $(grep -c . $X))"
tar -C / --one-file-system --exclude-from=$X -cf - . | tar -C $NEW -xpf - || fail "copy"
for d in proc sys dev run tmp mnt media var/log var/cache var/tmp \
	home/klipper/printer_data/logs home/klipper/printer_data/gcodes \
	home/klipper/printer_data/database; do mkdir -p $NEW/$d; done
chown $(stat -c %u:%g /home/klipper/printer_data) $NEW/home/klipper/printer_data/logs \
	$NEW/home/klipper/printer_data/gcodes $NEW/home/klipper/printer_data/database
chmod 1777 $NEW/var/tmp
chmod 1777 $NEW/tmp
sync
[ -x $NEW/etc/dp200/init.mainline ] || fail "no init.mainline in the new root"
[ -f $NEW/lib/firmware/mrvl/usb8782_uapsta.bin ] || fail "no 8782 firmware"
ls $NEW/lib/modules/$(uname -r)/kernel/drivers/net/wireless/marvell/mwifiex/mwifiex_usb.ko > /dev/null || fail "no mwifiex modules"
[ -f $NEW/home/klipper/printer_data/config/printer.cfg ] || fail "no printer.cfg"
[ -e $NEW/.dp200-root ] && fail "card marker copied"
df -k $NEW | tail -1
echo "files: card $(cd / && find . -xdev 2>/dev/null | wc -l) new $(find $NEW | wc -l)"
umount $NEW || fail "umount"
ubidetach -d 0 || fail "ubidetach"
echo none > $W
echo "window $(cat $W)"
echo "ecc_failures $(cat /sys/class/mtd/mtd6/ecc_failures)"
echo "STAGE5 OK: our root in mtd6 (card still marked)"
