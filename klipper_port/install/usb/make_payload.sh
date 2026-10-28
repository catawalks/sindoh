#!/bin/sh
# Build the USB installer payload from a WORKING printer's Debian root
# (built by build_rootfs_native.sh on the microSD card). Run on the printer,
# stock BusyBox shell; the Klipper stack may keep running (tar stays on the
# card's filesystem, so the chroot's proc/dev/tmp mounts are skipped):
#
#   sh make_payload.sh OUT_DIR [PORT_DIR] [full]
#
#   OUT_DIR   e.g. /mnt/sd/payload  or  /mnt/sda1/_update_rodin
#   PORT_DIR  checkout of this repository on the printer (generic configs come
#             from here, NOT from this printer's calibrated printer.cfg);
#             default /mnt/sd/usr/src/dp200/klipper_port
#   full      the whole build root incl. compilers (SD-card installs only).
#             Default: the RUNTIME image (install/nand/runtime.exclude),
#             ~120 MB gzip, which fits the internal NAND (mtd5).
#
# GNU tar from the Debian root does the work (BusyBox tar has no --exclude).
# Never included: logs, Moonraker database, uploaded G-code, caches, this
# printer's config (calibration), the NAND dump.
set -e
ROOT=/mnt/sd
OUT=${1:?usage: make_payload.sh OUT_DIR [PORT_DIR] [full]}
PORT=${2:-$ROOT/usr/src/dp200/klipper_port}
MODE=${3:-runtime}
[ -x $ROOT/usr/bin/tar ] || { echo "no Debian root on $ROOT"; exit 1; }
# Debian's tar needs Debian's libraries: run it inside the root, stream out
TAR="chroot $ROOT /usr/bin/tar"
for f in klipper/config/printer.cfg klipper/config/dp200_printer.cfg klipper/config/dp200_macros.cfg \
         klipper/config/dp200_adxl.cfg.off \
         install/rootfs/home/klipper/printer_data/config/moonraker.conf install/nand/runtime.exclude; do
    [ -f "$PORT/$f" ] || { echo "missing $PORT/$f"; exit 1; }
done
mkdir -p "$OUT"

# printer_data from scratch: generic config + empty dirs (this printer's
# printer_data - calibration, database, logs, G-code - is never shipped).
# Staged as ./payload_stage/printer_data inside the root and renamed in the
# archive (--transform); --exclude matches the on-disk name, so it only
# drops the live printer_data.
STAGE=payload_stage.$$
PD=home/klipper/printer_data
S=$ROOT/$STAGE/printer_data
rm -rf $ROOT/$STAGE; mkdir -p $S/config $S/logs $S/database $S/gcodes $S/comms
cp "$PORT"/klipper/config/printer.cfg "$PORT"/klipper/config/dp200_printer.cfg \
   "$PORT"/klipper/config/dp200_macros.cfg "$PORT"/klipper/config/dp200_adxl.cfg.off \
   "$PORT"/install/rootfs/home/klipper/printer_data/config/moonraker.conf $S/config/
chown -R $(grep '^klipper:' $ROOT/etc/passwd | cut -d: -f3,4) $S
cp "$PORT"/install/nand/runtime.exclude $ROOT/$STAGE/runtime.exclude

EXCL="--exclude=./$PD --exclude=./$STAGE/runtime.exclude --exclude=./home/klipper/.cache
      --exclude=./root/.cache --exclude=./var/cache/apt/archives/*.deb
      --exclude=./var/lib/apt/lists/* --exclude=./var/log/*"
[ "$MODE" = full ] || EXCL="$EXCL --exclude-from=/$STAGE/runtime.exclude"
NAME=dp200_klipper_payload.tar.gz

DIRS="./bin ./etc ./home ./lib ./opt ./root ./sbin ./srv ./usr ./var"
[ -e $ROOT/boot ] && DIRS="$DIRS ./boot"
$TAR -C / -czf - --numeric-owner --one-file-system $EXCL \
    --transform="s,^\./$STAGE/printer_data,./$PD," \
    $DIRS ./dp200/upctool $(cd $ROOT && ls ./dp200/*.sh) ./$STAGE/printer_data > "$OUT/$NAME"
rm -rf $ROOT/$STAGE
cd "$OUT"
md5sum $NAME > $NAME.md5
# unpacked size for the installer's space check (KiB)
$TAR -tvzf - < $NAME | awk '{s += $3} END {print int(s / 1024)}' > $NAME.size
echo "payload ($MODE): $(ls -l $NAME | awk '{print $5}') bytes, unpacked $(cat $NAME.size) KiB"
