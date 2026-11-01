#!/bin/sh
# Read-only UBI/UBIFS check of the stock root (mtd6) on the read-only
# mainline kernel (mtd6 read-only in its device tree: UBI attaches it
# read-only, nothing can be written). Attach as ubi1, mount ubi1:filesystem
# read-only, count and read every file, unmount, detach.
set -u
MNT=/run/ubiro
python3 -c "import fcntl,os,struct; f=os.open('/dev/ubi_ctrl',os.O_RDONLY); fcntl.ioctl(f,0x40186f40,struct.pack('iiihbb8x',1,6,0,0,0,0))" || { echo "UBIRO attach FAILED"; exit 1; }
sleep 1
echo "UBIRO attached: $(cat /sys/class/ubi/ubi1/total_eraseblocks) PEBs, $(cat /sys/class/ubi/ubi1/bad_peb_count) bad, volumes: $(cat /sys/class/ubi/ubi1/ubi1_*/name | tr '\n' ' ')"
mkdir -p $MNT
if mount -t ubifs -o ro ubi1:filesystem $MNT; then
	files=$(find $MNT -xdev -type f | wc -l)
	errs=0
	find $MNT -xdev -type f | while read f; do cat "$f" > /dev/null 2>&1 || echo "UBIRO read error: $f"; done > /tmp/ubiro_errs
	echo "UBIRO files $files, read errors $(wc -l < /tmp/ubiro_errs)"
	head -5 /tmp/ubiro_errs
	umount $MNT
else
	echo "UBIRO mount FAILED"
fi
python3 -c "import fcntl,os,struct; f=os.open('/dev/ubi_ctrl',os.O_RDONLY); fcntl.ioctl(f,0x40046f41,struct.pack('i',1))" && echo "UBIRO detached"
