#!/bin/sh
# Payload prep on the dev printer (2026-11-15): bring the SD card build root
# to the fork commit in $1 with the build from ktip.sh (/tmp/kt), then stage
# the port files (get.sh). Log: /tmp/kpay1.log. Run with sh, never sourced.
WANT=$1
L=/tmp/kpay1.log
exec > $L 2>&1
set -x
mountpoint -q /mnt/sd || { mkdir -p /mnt/sd; mount /dev/mmcblk0p1 /mnt/sd; }
mount -o remount,rw /mnt/sd || { echo REMOUNT_FAIL; exit 1; }
mountpoint -q /mnt/sd/proc || mount --bind /proc /mnt/sd/proc
mountpoint -q /mnt/sd/dev || mount --bind /dev /mnt/sd/dev
set +x
[ -f /tmp/kt/fm.bin ] && [ -f /tmp/kt/io.bin ] && [ -f /tmp/kt/klipper/klippy/chelper/c_helper.so ] || { echo NO_BUILD; exit 1; }
chroot /mnt/sd /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root GIT_PAGER=cat sh -c "
cd /home/klipper/klipper || exit 1
G='git -c safe.directory=*'
echo before: \$(\$G rev-parse HEAD) \$(\$G status --short | grep -v '^??' | wc -l) tracked changes
\$G status --short | grep -v '^??' | head -10
\$G fetch -q --tags https://github.com/catawalks/klipper sindoh-dp200 || { echo FETCH_FAIL; exit 1; }
[ \"\$(\$G rev-parse FETCH_HEAD)\" = '$WANT' ] || { echo WRONG_COMMIT \$(\$G rev-parse FETCH_HEAD); exit 1; }
\$G checkout -q -f --detach FETCH_HEAD || { echo CHECKOUT_FAIL; exit 1; }
echo after: \$(\$G rev-parse HEAD) \$(\$G describe --always --tags --long --dirty)
" || { echo GIT_STEP_FAILED; exit 1; }
K=/mnt/sd/home/klipper/klipper/klippy
cp /tmp/kt/klipper/klippy/chelper/c_helper.so $K/chelper/c_helper.so
chown --reference=$K/klippy.py $K/chelper/c_helper.so; touch $K/chelper/c_helper.so
for c in fm io; do cp -p /mnt/sd/opt/dp200/$c.bin /mnt/sd/opt/dp200/$c.bin.prev; cp /tmp/kt/$c.bin /mnt/sd/opt/dp200/$c.bin; done
md5sum $K/chelper/c_helper.so /mnt/sd/opt/dp200/fm.bin /mnt/sd/opt/dp200/io.bin
ls -la /mnt/sd/opt/dp200/
wget -q -O /tmp/get.sh http://10.10.0.85:8099/deploy/usb/get.sh && sh /tmp/get.sh
ls -la /mnt/sd/etc/dp200/ | cut -c1-90
df -h /mnt/sd | tail -1
sync
echo KPAY1_DONE
