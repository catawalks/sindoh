#!/bin/sh
# Build the Debian (trixie, ARMEL) root filesystem ON THE PRINTER itself -
# the alternative to build_rootfs.sh when no Linux PC / WSL is available.
# The DP200 SoC is ARMv7, so no qemu is needed; apt and pip run natively.
#
# Why armel: the vendor kernel has no CONFIG_ARM_THUMB, and Debian armhf is
# compiled as Thumb-2 ("Exec format error"). armel is ARM-mode code (tested:
# binaries, bash signal handlers, apt all run). bookworm armel images are no
# longer published by debuerreotype; trixie's glibc still supports kernel 3.2.
#
# Run from the stock (BusyBox) root shell, printer online (WiFi), clock set, with:
#   ROOTFS  official Debian trixie armel rootfs from the debuerreotype
#           artifacts (dist-arm32v5 branch, trixie/oci/blobs/rootfs.tar.gz;
#           check its sha256 against oci/blobs/image-manifest.json),
#           copied to the SD card
#   PORTTAR this repository as a tar.gz (host/ common/ klipper/ install/ upc_fw/)
#
#   sh build_rootfs_native.sh /mnt/sd/rootfs_armel.tar.gz /mnt/sd/klipper_port.tar.gz
#
# The Debian root goes to the SD card root (/mnt/sd), where dp200-start.sh
# expects it. Existing files there (dp200/, alpine*, pa6170_rodin_nand.bin,
# auto_update.sh, lost+found) are not touched: the Debian tree has none of
# those names. Re-running continues where it stopped.
set -e
ROOT=${ROOT:-/mnt/sd}
ROOTFS=$1
PORTTAR=$2
KUSER=klipper

[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
# The stock system boots with a 2013 clock: apt signatures and TLS would fail
[ "$(date +%Y)" -ge 2025 ] || { echo "system clock is $(date) - set it first: date -s 'YYYY-MM-DD hh:mm:ss'"; exit 1; }
grep -q " $ROOT " /proc/mounts || { echo "$ROOT is not mounted"; exit 1; }
for f in pa6170_rodin_nand.bin auto_update.sh; do
    [ -e "$ROOT/$f" ] && echo "keeping $ROOT/$f (not touched)"
done

echo "== 1. Debian base"
if [ ! -x $ROOT/usr/bin/apt-get ]; then
    [ -f "$ROOTFS" ] || { echo "missing Debian rootfs tarball '$ROOTFS'"; exit 1; }
    for d in bin sbin lib usr etc var; do
        [ -e "$ROOT/$d" ] && { echo "$ROOT/$d exists but no Debian there - refusing to overwrite"; exit 1; }
    done
    tar -xzf "$ROOTFS" -C $ROOT
fi
[ -x $ROOT/usr/bin/apt-get ] || { echo "extract failed"; exit 1; }

echo "== 2. port sources -> $ROOT/usr/src/dp200/klipper_port"
if [ -n "$PORTTAR" ]; then
    rm -rf $ROOT/usr/src/dp200/klipper_port
    mkdir -p $ROOT/usr/src/dp200/klipper_port
    tar -xzf "$PORTTAR" -C $ROOT/usr/src/dp200/klipper_port
fi
[ -f $ROOT/usr/src/dp200/klipper_port/install/rootfs_inside.sh ] || { echo "missing port sources"; exit 1; }

. $ROOT/usr/src/dp200/klipper_port/install/printer/dp200-mounts.sh
trap dp200_umount_root EXIT
dp200_mount_root
# pip builds need more space than a tmpfs: keep the build's /tmp on the card

echo "== 3..8 inside the chroot"
chroot $ROOT /usr/bin/env -i HOME=/root TERM=dumb \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8 KUSER=$KUSER \
    /bin/bash /usr/src/dp200/klipper_port/install/rootfs_inside.sh
echo "== done. Next: sh $ROOT/dp200/hook_install.sh (see README)"
