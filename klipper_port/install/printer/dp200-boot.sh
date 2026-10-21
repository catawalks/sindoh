#!/bin/sh
# Stage 1 of the Klipper boot, on the stock NAND root as /etc/dp200-boot.sh.
# Called from the /etc/profile hook (hook_install.sh) when /DEBUG_MACHINE
# bypasses the Sindoh app. Finds the Klipper root and starts it:
#
#   1. internal NAND: UBI volume "klipper" on mtd5 ("recovery", unused by the
#      stock boot) -> attached as ubi2, mounted on /klipper
#   2. microSD card: /mnt/sd (mounted by the stock media.connect)
#
# /etc/profile runs for every login too; dp200-start.sh has its own lock.
MTD=5
UBI=2
MNT=/klipper

nand_root() {
    grep -q " $MNT " /proc/mounts && return 0
    [ -e /sys/class/ubi/ubi$UBI ] || ubiattach -m $MTD -d $UBI >/dev/null 2>&1 || return 1
    grep -q '^klipper$' /sys/class/ubi/ubi$UBI/ubi${UBI}_*/name 2>/dev/null || return 1
    mkdir -p $MNT
    mount -t ubifs -o compr=zlib ubi$UBI:klipper $MNT
}

if nand_root && [ -x $MNT/dp200/dp200-start.sh ]; then
    exec $MNT/dp200/dp200-start.sh "$@"
fi
# not on NAND: wait up to 30 s for the stock boot to mount the SD card
i=0
while [ ! -x /mnt/sd/dp200/dp200-start.sh ] && [ $i -lt 30 ]; do
    sleep 1; i=$((i + 1))
done
[ -x /mnt/sd/dp200/dp200-start.sh ] && exec /mnt/sd/dp200/dp200-start.sh "$@"
echo "dp200-boot: no Klipper root on NAND ($MNT) or SD card" > /dev/console
exit 1
