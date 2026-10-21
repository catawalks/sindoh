#!/bin/sh
# Build the installer payload, rehearse the install (DRY_RUN) and smoke-test the
# unpacked runtime - all without touching the NAND. Stock side, on a printer
# with the development SD card:
#   sh release_check.sh [PORT_DIR] [OUT_DIR]
# Log: OUT_DIR/release_check.log
P=${1:-/mnt/sd/usr/src/dp200/klipper_port}
OUT=${2:-/mnt/sd/payload}
mkdir -p $OUT
exec > $OUT/release_check.log 2>&1
echo "== $(date) make_payload"
rm -f $OUT/dp200_klipper_payload.tar.gz*
sh $P/install/usb/make_payload.sh $OUT $P || { echo "PAYLOAD FAILED"; exit 1; }
echo "== $(date) dry run"
rm -rf /mnt/sd/dryrun_root
DRY_RUN=1 sh $P/install/usb/unmistakable_klipper_install.sh $OUT || { echo "DRY RUN FAILED"; exit 1; }
echo "== $(date) runtime check"
sh $P/install/nand/check_runtime.sh /mnt/sd/dryrun_root || { echo "RUNTIME CHECK FAILED"; exit 1; }
rm -rf /mnt/sd/dryrun_root
echo "== $(date) RELEASE CHECK PASSED"
