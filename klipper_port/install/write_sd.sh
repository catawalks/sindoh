#!/bin/bash
# Write the DP200 Debian root filesystem to a microSD card.
#
#   sudo ./write_sd.sh ./dp200-rootfs /dev/sdX
#
# ERASES the whole card. Creates one ext3 partition (ext3 is built into
# the vendor kernel; the stock media.connect mounts it at /mnt/sd).
# 8 GB or larger recommended.
set -euo pipefail
SRC=${1:?rootfs dir}; DEV=${2:?block device, e.g. /dev/sdb}
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
[ -b "$DEV" ] || { echo "$DEV is not a block device"; exit 1; }
[ -x "$SRC/etc/dp200/rc.dp200" ] || { echo "$SRC does not look like a DP200 rootfs"; exit 1; }

lsblk "$DEV"
read -r -p "ALL DATA ON $DEV WILL BE LOST. Type 'yes' to continue: " ok
[ "$ok" = yes ] || exit 1

umount "${DEV}"* 2>/dev/null || true
parted -s "$DEV" mklabel msdos mkpart primary ext3 4MiB 100%
sleep 1
PART=${DEV}1; [ -b "$PART" ] || PART=${DEV}p1
# 128-byte inodes and no newer ext4-only features: keeps kernel 3.2 happy
mkfs.ext3 -F -L DP200ROOT -I 128 "$PART"
MNT=$(mktemp -d)
mount "$PART" "$MNT"
rsync -aHAX --info=progress2 --exclude=/proc/* --exclude=/sys/* \
    --exclude=/dev/* --exclude=/tmp/* --exclude=/run/* "$SRC"/ "$MNT"/
sync
umount "$MNT"; rmdir "$MNT"
echo "SD card ready. On the printer (stock root shell): sh /mnt/sd/dp200/hook_install.sh"
