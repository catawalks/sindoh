#!/bin/sh
# (docs/dev_printer_testing.md) Build klippy's c_helper.so for the dp200-clean stage B and C host code,
# with the gcc on the SD card (same Debian as the NAND root; card mounted
# read-only at /mnt/sd, work in /tmp).
U=http://10.10.0.85:8099/deploy/usb/t
L=/tmp/kso.log
: > $L
mountpoint -q /mnt/sd/tmp || mount --bind /tmp /mnt/sd/tmp
mountpoint -q /mnt/sd/dev || mount --bind /dev /mnt/sd/dev
mountpoint -q /mnt/sd/proc || mount --bind /proc /mnt/sd/proc
for n in b c; do
    rm -rf /tmp/kb/$n; mkdir -p /tmp/kb/$n
    wget -q -O /tmp/kb/klippy-$n.tgz $U/klippy-$n.tgz || { echo "FETCH_FAIL $n" >> $L; continue; }
    md5sum /tmp/kb/klippy-$n.tgz >> $L
    tar xzf /tmp/kb/klippy-$n.tgz -C /tmp/kb/$n
    chroot /mnt/sd /home/klipper/klippy-env/bin/python -c "
import sys, logging
logging.basicConfig(level=logging.INFO)
sys.path.insert(0, '/tmp/kb/$n/klippy')
import chelper
ffi, lib = chelper.get_ffi()
print('BUILT_AND_LOADED $n')" >> $L 2>&1
    ls -l /tmp/kb/$n/klippy/chelper/c_helper.so >> $L 2>&1
    md5sum /tmp/kb/$n/klippy/chelper/c_helper.so >> $L 2>&1
done
echo KSO_DONE >> $L
