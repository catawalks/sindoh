#!/bin/sh
# Build the UPC firmware (fm, io) and klippy's c_helper.so from a tarball of
# the fork (klipper-tip.tgz on the PC server), on the printer, with the
# toolchain on the SD card (mounted read-only at /mnt/sd; work in /tmp).
#   V=<version string> ; sh ktip.sh        log: /tmp/ktip.log
U=http://10.10.0.85:8099/deploy/usb/t
L=/tmp/ktip.log
V=${V:-sindoh-dp200}
: > $L
mountpoint -q /mnt/sd || { mkdir -p /mnt/sd; mount -o ro /dev/mmcblk0p1 /mnt/sd; }
mountpoint -q /mnt/sd/tmp || mount --bind /tmp /mnt/sd/tmp
mountpoint -q /mnt/sd/dev || mount --bind /dev /mnt/sd/dev
mountpoint -q /mnt/sd/proc || mount --bind /proc /mnt/sd/proc
rm -rf /tmp/kt; mkdir -p /tmp/kt
wget -q -O /tmp/kt/klipper-tip.tgz $U/klipper-tip.tgz || { echo FETCH_FAIL >> $L; exit 1; }
md5sum /tmp/kt/klipper-tip.tgz >> $L
tar xzf /tmp/kt/klipper-tip.tgz -C /tmp/kt
echo "$V" > /tmp/kt/klipper/klippy/.version
chroot /mnt/sd /usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root sh -c '
cd /tmp/kt/klipper || exit 1
for core in fm io; do
    rm -rf out .config
    cp config/dp200_$core.config .config
    make olddefconfig >/dev/null 2>&1
    if make >/tmp/kt/make_$core.log 2>&1; then
        cp out/klipper.bin /tmp/kt/$core.bin; cp out/klipper.elf /tmp/kt/$core.elf
        grep -a -m1 "Version:" /tmp/kt/make_$core.log
    else
        echo "MAKE_FAIL $core"; tail -15 /tmp/kt/make_$core.log
    fi
done
rm -rf out .config
/home/klipper/klippy-env/bin/python -c "
import sys, logging
logging.basicConfig(level=logging.INFO)
sys.path.insert(0, \"/tmp/kt/klipper/klippy\")
import chelper
chelper.get_ffi()
print(\"CHELPER_OK\")"
' >> $L 2>&1
ls -l /tmp/kt/fm.bin /tmp/kt/io.bin /tmp/kt/klipper/klippy/chelper/c_helper.so >> $L 2>&1
md5sum /tmp/kt/fm.bin /tmp/kt/io.bin /tmp/kt/klipper/klippy/chelper/c_helper.so >> $L 2>&1
echo KTIP_DONE >> $L
