#!/bin/sh
# sdroot-test: prove a real userspace runs on mainline, read-only.
#   sdroot-test [partition]     (default: every ext2/3/4 partition of mmcblk0)
#
# Only the 2 GB rescue card: refuses a card larger than 3 GB. Sets the
# block device read-only (force_ro), mounts each partition -o ro,noload
# (noload: no journal replay, which would write), and, where it finds
# /bin/sh, runs a few read-only commands inside it with chroot. No init and
# no services are started. Unmounts at the end.
B=/sys/block/mmcblk0
[ -d $B ] || { echo "sdroot-test: no mmcblk0"; exit 1; }
sectors=$(cat $B/size)
if [ "$sectors" -gt $((3 * 1024 * 1024 * 2)) ]; then
	echo "sdroot-test: card is $((sectors / 2048)) MiB: not the 2 GB rescue card, refusing"
	exit 1
fi
echo 1 > $B/force_ro
echo "--- mmcblk0: $((sectors / 2048)) MiB, force_ro $(cat $B/force_ro), ro $(cat $B/ro)"
cat /proc/partitions | grep mmcblk

parts=$1
[ -n "$parts" ] || parts=$(cd /dev && ls mmcblk0p* 2>/dev/null)
for p in $parts; do
	p=${p#/dev/}
	m=/mnt/sdroot-$p
	mkdir -p $m
	if ! mount -t ext4 -o ro,noload /dev/$p $m 2>/dev/null &&
	   ! mount -t ext2 -o ro /dev/$p $m 2>/dev/null; then
		echo "--- $p: not ext2/3/4, skipped"
		continue
	fi
	echo "--- $p mounted read-only: $(grep " $m " /proc/mounts)"
	ls $m
	if [ -x $m/bin/sh ]; then
		echo "--- chroot $m /bin/sh (read-only commands only):"
		chroot $m /bin/sh -c 'echo "uname: $(uname -a)"; head -n 3 /etc/os-release 2>/dev/null || head -n 1 /etc/issue 2>/dev/null; ls -l /bin/sh; id; echo "chroot ok"'
		echo "--- exit status $?"
	else
		echo "--- $p: no /bin/sh"
	fi
	umount $m
done
grep mmcblk /proc/mounts || echo "--- nothing left mounted"
