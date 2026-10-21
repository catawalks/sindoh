#!/bin/bash
# Build the Debian (trixie, armel) root filesystem for the Sindoh DP200.
# (No Linux PC? install/build_rootfs_native.sh builds it on the printer.)
#
# Run as root on a Debian/Ubuntu PC (or WSL2):
#   sudo ./build_rootfs.sh [OUTDIR]          # default ./dp200-rootfs
# then write it to a microSD card with ./write_sd.sh.
#
# Needs: debootstrap qemu-user-static binfmt-support git
#        gcc-arm-none-eabi (UPC firmware) and python3 (Klipper build)
#
# Why armel: the vendor kernel 3.2 is built without CONFIG_ARM_THUMB, and
# Debian armhf is compiled as Thumb-2, so its binaries fail with "Exec
# format error". armel is ARM-mode code (verified on the printer). trixie's
# glibc still supports kernel 3.2.
set -euo pipefail

OUT=$(realpath -m "${1:-./dp200-rootfs}")
HERE=$(cd "$(dirname "$0")" && pwd)
PORT=$(cd "$HERE/.." && pwd)
SUITE=trixie
MIRROR=${MIRROR:-http://deb.debian.org/debian}
KUSER=klipper
KHOME=$OUT/home/$KUSER

[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
for t in debootstrap qemu-arm-static git arm-none-eabi-gcc python3; do
    command -v $t >/dev/null || { echo "missing $t"; exit 1; }
done

in_root() { chroot "$OUT" /usr/bin/env -i HOME=/root \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8 "$@"; }
as_user() { in_root su -s /bin/bash $KUSER -c "$1"; }

cleanup() {
    for m in dev/pts dev proc sys; do
        mountpoint -q "$OUT/$m" && umount "$OUT/$m" || true
    done
}
trap cleanup EXIT

echo "== 1. debootstrap $SUITE armel into $OUT"
if [ ! -x "$OUT/bin/bash" ]; then
    debootstrap --arch=armel --foreign --variant=minbase \
        --include=ca-certificates "$SUITE" "$OUT" "$MIRROR"
    cp "$(command -v qemu-arm-static)" "$OUT/usr/bin/"
    chroot "$OUT" /debootstrap/debootstrap --second-stage
fi
cp "$(command -v qemu-arm-static)" "$OUT/usr/bin/"
mount -t proc proc "$OUT/proc"; mount -t sysfs sys "$OUT/sys"
mount -o bind /dev "$OUT/dev"; mount -o bind /dev/pts "$OUT/dev/pts"
cp /etc/resolv.conf "$OUT/etc/resolv.conf"

echo "== 2. packages"
in_root apt-get update
in_root apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev python3-pip gcc g++ make libc6-dev \
    libffi-dev libncurses-dev git sudo curl unzip nginx \
    libjpeg62-turbo-dev zlib1g-dev liblmdb-dev libsodium-dev \
    procps iproute2 iputils-ping less nano \
    ustreamer v4l-utils python3-pil fonts-dejavu-core
in_root apt-get clean
# time64 -> time32 V4L2 shim for kernel 3.2 (see install/camera/)
mkdir -p "$OUT/usr/src/dp200/camera"
cp "$HERE/camera/v4l2_time32_shim.c" "$OUT/usr/src/dp200/camera/"
in_root gcc -O2 -Wall -shared -fPIC -o /usr/local/lib/v4l2_time32_shim.so \
    /usr/src/dp200/camera/v4l2_time32_shim.c -ldl

echo "== 3. klipper user"
in_root id $KUSER >/dev/null 2>&1 || \
    in_root useradd -m -s /bin/bash -G dialout,video,tty $KUSER
chmod 755 "$KHOME"

echo "== 4. Klipper + Moonraker (this compiles python wheels under qemu; slow)"
[ -d "$KHOME/klipper" ] || as_user "git clone --depth 1 https://github.com/Klipper3d/klipper ~/klipper"
[ -d "$KHOME/moonraker" ] || as_user "git clone --depth 1 https://github.com/Arksine/moonraker ~/moonraker"
as_user "python3 -m venv ~/klippy-env && ~/klippy-env/bin/pip install -q -r ~/klipper/scripts/klippy-requirements.txt"
as_user "python3 -m venv ~/moonraker-env && ~/moonraker-env/bin/pip install -q -r ~/moonraker/scripts/moonraker-requirements.txt"
# Pre-build Klipper's host C helper so the first start on the printer is fast
as_user "cd ~/klipper/klippy && ~/klippy-env/bin/python -c 'import chelper; chelper.get_ffi()'"

echo "== 5. Mainsail"
if [ ! -f "$KHOME/mainsail/index.html" ]; then
    as_user "mkdir -p ~/mainsail && cd ~/mainsail && \
        curl -fsSL -o mainsail.zip https://github.com/mainsail-crew/mainsail/releases/latest/download/mainsail.zip && \
        unzip -q mainsail.zip && rm mainsail.zip"
fi
install -m 644 "$HERE/rootfs/etc/nginx/sites-available/mainsail" "$OUT/etc/nginx/sites-available/mainsail"
rm -f "$OUT/etc/nginx/sites-enabled/default"
ln -sf ../sites-available/mainsail "$OUT/etc/nginx/sites-enabled/mainsail"

echo "== 6. UPC firmware (built on this PC with arm-none-eabi-gcc)"
# Build from a copy of the rootfs' own Klipper checkout so the MCU
# firmware and the klippy host are the same version.
KBUILD=$(mktemp -d)
cp -a "$KHOME/klipper" "$KBUILD/klipper"
"$PORT/klipper/install_port.sh" "$KBUILD/klipper"
mkdir -p "$OUT/opt/dp200"
for core in fm io; do
    ( cd "$KBUILD/klipper" && make clean >/dev/null &&
      cp "config/dp200_$core.config" .config &&
      make olddefconfig >/dev/null && make )
    cp "$KBUILD/klipper/out/klipper.bin" "$OUT/opt/dp200/$core.bin"
done
make -C "$PORT/upc_fw/probe"
cp "$PORT/upc_fw/probe/probe_fm.bin" "$PORT/upc_fw/probe/probe_io.bin" "$OUT/opt/dp200/"
rm -rf "$KBUILD"

echo "== 7. upctool (built natively inside the armel root; ARM mode, softfp ABI)"
mkdir -p "$OUT/usr/src/dp200"
cp -r "$PORT/host" "$PORT/common" "$OUT/usr/src/dp200/"
rm -f "$OUT/usr/src/dp200/host/upctool"
in_root make -C /usr/src/dp200/host CC=gcc ARCHFLAGS= \
    CFLAGS="-O2 -Wall -std=gnu99 -marm -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=softfp"
install -m 755 "$OUT/usr/src/dp200/host/upctool" "$OUT/usr/local/bin/upctool"

echo "== 8. DP200 configuration and boot scripts"
install -d "$OUT/etc/dp200" "$OUT/dp200" "$KHOME/printer_data/config" \
    "$KHOME/printer_data/gcodes" "$KHOME/printer_data/logs"
install -m 755 "$HERE/rootfs/etc/dp200/rc.dp200" "$OUT/etc/dp200/rc.dp200"
install -m 755 "$HERE/display/dp200_screen.py" "$HERE/display/dp200_wifi.py" "$HERE/display/dp200_net.py" "$OUT/usr/local/bin/"
install -m 755 "$HERE/printer/"*.sh "$OUT/dp200/"
cp -n "$HERE/rootfs/home/klipper/printer_data/config/moonraker.conf" "$KHOME/printer_data/config/" || true
cp "$PORT/klipper/config/dp200_printer.cfg" "$PORT/klipper/config/dp200_macros.cfg" "$KHOME/printer_data/config/"
cp -n "$PORT/klipper/config/printer.cfg" "$KHOME/printer_data/config/printer.cfg" || true
cp "$PORT/klipper/extras/upc_stats.py" "$PORT/klipper/extras/upc_clockcheck.py" \
   "$PORT/klipper/extras/dp200_cartridge.py" "$KHOME/klipper/klippy/extras/"
in_root chown -R $KUSER:$KUSER /home/$KUSER
echo "dp200-klipper" > "$OUT/etc/hostname"

# Kernel 3.2 has no getrandom(); python/openssl fall back to /dev/urandom.
# There is no init system: services run from /etc/dp200/rc.dp200.
rm -f "$OUT/usr/bin/qemu-arm-static"
echo "== done: $OUT  ($(du -sh "$OUT" | cut -f1))"
echo "next: sudo ./write_sd.sh $OUT /dev/sdX"
