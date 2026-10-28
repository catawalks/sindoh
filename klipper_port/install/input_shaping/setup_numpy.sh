#!/bin/sh
# Make numpy available to Klipper for SHAPER_CALIBRATE (docs/input_shaping.md).
# Opt-in: only owners with an accelerometer need it (~25 MB). Needs internet.
# Run on the printer's serial/SSH shell, in the foreground (a background job
# on the serial console gets stopped when apt touches the terminal):
#   chroot /mnt/sd sh /usr/src/dp200/klipper_port/install/input_shaping/setup_numpy.sh
#
# Klipper's virtualenv can't build numpy on this armel CPU (no wheels, and a
# source build takes hours), so this installs Debian's python3-numpy and
# exposes only numpy to the venv through a .pth file.
set -e
VPY=/home/klipper/klippy-env/bin/python
LINK=/usr/local/lib/dp200-numpy

apt-get update
# --reinstall: the internal-NAND runtime image leaves numpy's files out
# (install/nand/runtime.exclude) while dpkg still lists it as installed
apt-get install -y --no-install-recommends --reinstall python3-numpy libblas3 liblapack3 libgfortran5
mkdir -p $LINK
ln -sfn /usr/lib/python3/dist-packages/numpy $LINK/numpy
SITE=$($VPY -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
echo $LINK > $SITE/dp200-numpy.pth
$VPY -c 'import numpy; print("numpy", numpy.__version__, "OK for Klipper")'
echo "Restart Klipper (screen: SYSTEM -> KLIPPER) before SHAPER_CALIBRATE."
