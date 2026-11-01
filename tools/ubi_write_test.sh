#!/bin/bash
# NAND write path, step 2 (owner-approved 2026-10-31): UBI + UBIFS writes
# through the mainline driver, on the stock root (mtd6), from the test
# kernel m1-debian-nandw. Runs on the printer as root.
#   1. write window = mtd6 without the 4 BBT blocks (1741-4091)
#   2. attach mtd6 read-write as ubi1, mount ubi1:filesystem
#   3. write a 16 MB random file, sync, unmount, mount again, check its md5
#   4. delete it, sync, unmount, detach
#   5. close the window; print the UBI/UBIFS kernel log
# The window never covers mtd0-mtd5 (the driver refuses them anyway), and
# the stock root's format stays 4: mainline only writes format 5 when
# encryption is turned on. Stops at the first error; the window is closed
# and UBI detached on every exit.
set -u
WIN=/sys/module/marvell_nand/parameters/write_window
MNT=/run/ubitest
FILE=$MNT/dp200_ubi_write_test.bin
SIZE_MB=16

attach() {
	python3 -c "import fcntl,os,struct; f=os.open('/dev/ubi_ctrl',os.O_RDONLY); fcntl.ioctl(f,0x40186f40,struct.pack('iiihbb8x',1,6,0,0,0,0))"
}
detach() {
	python3 -c "import fcntl,os,struct; f=os.open('/dev/ubi_ctrl',os.O_RDONLY); fcntl.ioctl(f,0x40046f41,struct.pack('i',1))" 2>/dev/null
}
cleanup() {
	mountpoint -q $MNT && umount $MNT
	[ -e /dev/ubi1 ] && detach
	echo none > $WIN
	echo "window: $(cat $WIN)"
}
trap cleanup EXIT
fail() { echo "FAIL: $*"; exit 1; }

[ "$(cat $WIN)" = none ] || fail "window not closed at start"
[ "$(cat /sys/class/mtd/mtd6/flags)" = 0x400 ] || fail "mtd6 not writable (wrong kernel?)"
grep -q ubi1 /proc/mounts && fail "ubi1 already mounted"
mark=$(dmesg | wc -l)

echo 1741,4091 > $WIN || fail "window"
# watchdog: more than 20 UBI scrub moves (a wrong bitflip count made UBI
# scrub everything it read on 2026-10-31) closes the window at once
scrubs0=$(dmesg | grep -c scrubbed)
( while [ "$(cat $WIN)" != none ]; do
	if [ $(( $(dmesg | grep -c scrubbed) - scrubs0 )) -gt 20 ]; then
		echo none > $WIN
		echo "WATCHDOG: >20 scrubs, window closed"
	fi
	sleep 1
  done ) &
echo "1. window $(cat $WIN)"
attach || fail "UBI attach"
sleep 1
echo "2. attached: $(cat /sys/class/ubi/ubi1/total_eraseblocks) PEBs, $(cat /sys/class/ubi/ubi1/bad_peb_count) bad, max EC $(cat /sys/class/ubi/ubi1/max_ec), volumes: $(cat /sys/class/ubi/ubi1/ubi1_*/name | tr '\n' ' ')"
mkdir -p $MNT
mount -t ubifs ubi1:filesystem $MNT || fail "mount rw"
df -k $MNT | tail -1 | awk '{print "   free before: " $4 " KB"}'

dd if=/dev/urandom of=$FILE bs=1M count=$SIZE_MB conv=fsync 2>/dev/null || fail "write"
sum=$(md5sum < $FILE | cut -d' ' -f1)
sync
echo "3. wrote $SIZE_MB MB, md5 $sum"
umount $MNT || fail "umount"
echo 3 > /proc/sys/vm/drop_caches
mount -t ubifs ubi1:filesystem $MNT || fail "mount again"
again=$(md5sum < $FILE | cut -d' ' -f1)
[ "$again" = "$sum" ] || fail "md5 after remount $again"
echo "   after remount: md5 matches"

rm -f $FILE && sync || fail "rm"
df -k $MNT | tail -1 | awk '{print "4. deleted; free after: " $4 " KB"}'
umount $MNT || fail "umount 2"
detach || fail "detach"
echo "   detached"
echo "   scrubs: $(( $(dmesg | grep -c scrubbed) - scrubs0 )), bitflip reports: $(dmesg | tail -n +$((mark + 1)) | grep -c "fixable bit-flip")"
echo "5. kernel log (UBI/UBIFS/NAND):"
dmesg | tail -n +$((mark + 1)) | grep -i "ubi\|nand\|program\|refused\|error\|fail" | head -40
echo DONE
