#!/bin/bash
# Measure how big a Klipper runtime image (SD build root minus runtime.exclude)
# would be: uncompressed bytes and gzip -6 bytes (close to UBIFS zlib usage).
# Read-only on the root; writes nothing but its report.
# Run INSIDE the Debian chroot of the SD build:
#   chroot /mnt/sd /bin/bash /usr/src/dp200/klipper_port/install/nand/measure_runtime.sh /tmp/runtime_size.txt
set -eu
EXC=$(dirname "$0")/runtime.exclude
OUT=${1:-/tmp/runtime_size.txt}
cd /
DIRS="./bin ./etc ./home ./lib ./opt ./root ./sbin ./usr ./var"
{
echo "runtime image estimate $(date)"
RAW=$(tar -cf - --numeric-owner --one-file-system --exclude-from="$EXC" $DIRS 2>/dev/null | wc -c)
echo "uncompressed: $RAW bytes ($((RAW / 1048576)) MB)"
GZ=$(tar -cf - --numeric-owner --one-file-system --exclude-from="$EXC" $DIRS 2>/dev/null | gzip -6 | wc -c)
echo "gzip -6:      $GZ bytes ($((GZ / 1048576)) MB)"
echo "biggest remaining dirs (MB):"
du -xsm --exclude-from="$EXC" ./usr/lib/* ./usr/bin ./usr/share ./home/klipper/* 2>/dev/null | sort -rn | head -25
echo DONE
} > "$OUT" 2>&1
