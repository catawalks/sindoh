#!/bin/sh
# Rebuild one UPC firmware image inside the Debian root (same steps as
# install/rootfs_inside.sh step 7) and install it to /opt/dp200/<core>.bin.
#   chroot /mnt/sd sh /usr/src/dp200/klipper_port/tools/fm_rebuild.sh [fm|io]
# The old image is kept as /opt/dp200/<core>.bin.prev.
set -e
core=${1:-fm}
PORT=/usr/src/dp200/klipper_port
KBUILD=$(mktemp -d /var/tmp/kbuild.XXXX)
cp -a /home/klipper/klipper $KBUILD/klipper
# /home/klipper/klipper is the fork checkout (klipper/FORK): the port is already in it
cd $KBUILD/klipper
make clean >/dev/null
cp config/dp200_$core.config .config
make olddefconfig >/dev/null
make
cp /opt/dp200/$core.bin /opt/dp200/$core.bin.prev
cp out/klipper.bin /opt/dp200/$core.bin
echo "$core.bin: $(stat -c %s /opt/dp200/$core.bin) bytes"
rm -rf $KBUILD
