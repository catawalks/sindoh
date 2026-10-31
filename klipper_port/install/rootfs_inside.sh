#!/bin/bash
# Steps 3-8 of the on-printer Debian build, run INSIDE the chroot by
# build_rootfs_native.sh (same result as build_rootfs.sh on a PC).
set -euo pipefail
PORT=/usr/src/dp200/klipper_port
KUSER=${KUSER:-klipper}
KHOME=/home/$KUSER
as_user() { su -s /bin/bash $KUSER -c "$1"; }

echo "== 3. packages"
dpkg --configure -a          # finish an interrupted earlier run
apt-get update -q
apt-get install -y -q -o Dpkg::Progress-Fancy=0 --no-install-recommends \
    python3 python3-venv python3-dev python3-pip gcc g++ make libc6-dev \
    libffi-dev libncurses-dev git sudo curl unzip nginx \
    libjpeg62-turbo-dev zlib1g-dev liblmdb-dev libsodium-dev \
    procps iproute2 iputils-ping less nano ca-certificates \
    gcc-arm-none-eabi binutils-arm-none-eabi libnewlib-arm-none-eabi \
    ustreamer v4l-utils \
    python3-pil fonts-dejavu-core
apt-get clean
# time64 -> time32 V4L2 buffer ioctl shim for kernel 3.2 (see install/camera/)
gcc -O2 -Wall -shared -fPIC -o /usr/local/lib/v4l2_time32_shim.so \
    $PORT/install/camera/v4l2_time32_shim.c -ldl

echo "== 4. klipper user"
id $KUSER >/dev/null 2>&1 || useradd -m -s /bin/bash -G dialout,video,tty $KUSER
chmod 755 $KHOME

echo "== 5. Klipper + Moonraker (native pip builds; slow on the PJ4)"
[ -d $KHOME/klipper ] || as_user "git clone --depth 1 https://github.com/Klipper3d/klipper ~/klipper"
[ -d $KHOME/moonraker ] || as_user "git clone --depth 1 https://github.com/Arksine/moonraker ~/moonraker"
[ -x $KHOME/klippy-env/bin/python ] || as_user "python3 -m venv ~/klippy-env"
as_user "TMPDIR=~/.cache/tmp; mkdir -p \$TMPDIR; export TMPDIR; ~/klippy-env/bin/pip install -q -r ~/klipper/scripts/klippy-requirements.txt"
[ -x $KHOME/moonraker-env/bin/python ] || as_user "python3 -m venv ~/moonraker-env"
# SKIP_CYTHON: dbus-fast/zeroconf fall back to pure Python. Their parallel
# Cython builds got OOM-killed (494 MB RAM, kernel without swap support).
as_user "TMPDIR=~/.cache/tmp; export TMPDIR SKIP_CYTHON=1 MAKEFLAGS=-j1; ~/moonraker-env/bin/pip install -q -r ~/moonraker/scripts/moonraker-requirements.txt"
as_user "cd ~/klipper/klippy && ~/klippy-env/bin/python -c 'import chelper; chelper.get_ffi()'"

echo "== 6. Mainsail"
if [ ! -f $KHOME/mainsail/index.html ]; then
    as_user "mkdir -p ~/mainsail && cd ~/mainsail && \
        curl -fsSL -o mainsail.zip https://github.com/mainsail-crew/mainsail/releases/latest/download/mainsail.zip && \
        unzip -q mainsail.zip && rm mainsail.zip"
fi
install -m 644 $PORT/install/rootfs/etc/nginx/sites-available/mainsail /etc/nginx/sites-available/mainsail
rm -f /etc/nginx/sites-enabled/default
ln -sf ../sites-available/mainsail /etc/nginx/sites-enabled/mainsail

echo "== 7. UPC firmware (arm-none-eabi-gcc, same Klipper version as klippy)"
KBUILD=$(mktemp -d /var/tmp/kbuild.XXXX)
cp -a $KHOME/klipper $KBUILD/klipper
sh $PORT/klipper/install_port.sh $KBUILD/klipper     # tarballs made on Windows carry no exec bits
mkdir -p /opt/dp200
for core in fm io; do
    # The Makefile fails the build itself when the image exceeds the 16 KiB ITCM
    if ( cd $KBUILD/klipper && make clean >/dev/null &&
         cp config/dp200_$core.config .config &&
         make olddefconfig >/dev/null && make ); then
        cp $KBUILD/klipper/out/klipper.bin /opt/dp200/$core.bin
        echo "$core.bin: gcc build, $(stat -c %s /opt/dp200/$core.bin) bytes"
    else
        # The verified images were built with zig/clang; gcc output may be larger
        echo "WARNING: gcc build of the $core image failed or exceeds 16384 bytes"
        if [ -f /dp200/klipper_$core.bin ]; then
            cp /dp200/klipper_$core.bin /opt/dp200/$core.bin
            echo "  using the hardware-verified /dp200/klipper_$core.bin instead (klippy version may differ!)"
        fi
    fi
done
rm -rf $KBUILD

echo "== 8. upctool, config, boot scripts"
# armel ABI (softfp: VFP instructions, soft-float calls) and ARM mode: the
# kernel cannot run Thumb code (no CONFIG_ARM_THUMB)
rm -f $PORT/host/upctool
if make -C $PORT/host CC=gcc ARCHFLAGS= \
    CFLAGS="-O2 -Wall -std=gnu99 -marm -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=softfp"; then
    install -m 755 $PORT/host/upctool /usr/local/bin/upctool
else
    echo "WARNING: upctool build failed - using the verified static /dp200/upctool"
    install -m 755 /dp200/upctool /usr/local/bin/upctool
fi
install -d /etc/dp200 /dp200 $KHOME/printer_data/config $KHOME/printer_data/gcodes $KHOME/printer_data/logs
install -m 755 $PORT/install/rootfs/etc/dp200/rc.dp200 /etc/dp200/rc.dp200
install -m 755 $PORT/install/display/dp200_screen.py $PORT/install/display/dp200_wifi.py $PORT/install/display/dp200_net.py /usr/local/bin/
install -m 755 $PORT/install/printer/*.sh $PORT/install/printer/*.py /dp200/
# PID 1 for a mainline boot of this root (unused on stock)
install -m 755 $PORT/install/rootfs/etc/dp200/init.mainline /etc/dp200/init.mainline
cp -n $PORT/install/rootfs/home/klipper/printer_data/config/moonraker.conf $KHOME/printer_data/config/ || true
# dp200_*.cfg belong to this port (replaced on every build/update);
# printer.cfg is the user's file (only created if missing)
cp $PORT/klipper/config/dp200_printer.cfg $PORT/klipper/config/dp200_macros.cfg \
   $PORT/klipper/config/dp200_adxl.cfg.off $KHOME/printer_data/config/
cp -n $PORT/klipper/config/printer.cfg $KHOME/printer_data/config/printer.cfg || true
cp $PORT/klipper/extras/upc_stats.py $PORT/klipper/extras/upc_clockcheck.py \
   $PORT/klipper/extras/dp200_cartridge.py $KHOME/klipper/klippy/extras/
chown -R $KUSER:$KUSER $KHOME
echo "dp200-klipper" > /etc/hostname
echo "== inside: done ($(du -sh /usr /home /opt 2>/dev/null | tr '\n' ' '))"
