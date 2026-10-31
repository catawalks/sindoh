#!/bin/sh
# Put a kernel image raw on the SD card for tools/sd_raw_boot.sh: into the gap
# before partition 1, from sector 64. Runs from the printer's Linux (stock or
# mainline) over the serial console; the printer fetches the image from the
# PC's HTTP server (D:/DP200/kernel/out on port 8099). Refuses when the
# image would reach partition 1. Writes the SD card only (never NAND), then
# reads it back and compares the md5.
# The gap's old content was saved once (2026-10-31) to
# /var/backups/sd_gap_sectors_1-8191.bin on the card's root.
# usage: tools/sd_raw_install.sh [IMAGE] [PC_IP]
set -e
img=${1:-D:/DP200/kernel/out/m1-debian.uimg}
pc=${2:-10.10.0.85}
here=$(dirname "$0")
SECTOR=64
[ -f "$img" ] || { echo "$img: not found"; exit 1; }
out=$(cd "$(dirname "$img")" && pwd)
mkdir -p "$out/deploy"
cp "$img" "$out/deploy/sd-raw.uimg"
size=$(wc -c < "$img")
blocks=$(( (size + 511) / 512 ))
md5=$(md5sum "$img" | cut -d' ' -f1)
echo "$(basename "$img"): $size bytes, $blocks sectors from $SECTOR, md5 $md5"
curl -sf -o /dev/null "http://$pc:8099/deploy/sd-raw.uimg" ||
	{ echo "no HTTP server at $pc:8099 serving $out"; exit 1; }

# on the printer: partition 1 must start after the image; wget (stock) or
# python3 (the Debian root on mainline) fetches it
py -3.15t "$here/serial_watch.py" COM3 90 "p1=\$(cat /sys/block/mmcblk0/mmcblk0p1/start); \
if [ \$(( $SECTOR + $blocks )) -gt \$p1 ]; then echo REFUSED partition 1 starts at \$p1; else \
{ wget -q -O /tmp/k.uimg http://$pc:8099/deploy/sd-raw.uimg 2>/dev/null || \
python3 -c \"import urllib.request as u; open('/tmp/k.uimg','wb').write(u.urlopen('http://$pc:8099/deploy/sd-raw.uimg').read())\"; } && \
[ \$(md5sum < /tmp/k.uimg | cut -d' ' -f1) = $md5 ] && \
dd if=/tmp/k.uimg of=/dev/mmcblk0 bs=512 seek=$SECTOR conv=fsync 2>/dev/null && sync && \
echo 3 > /proc/sys/vm/drop_caches && \
echo READBACK \$(dd if=/dev/mmcblk0 bs=512 skip=$SECTOR count=$blocks 2>/dev/null | head -c $size | md5sum); \
rm -f /tmp/k.uimg; fi" | grep -a "REFUSED\|READBACK" | tail -1 | tee /dev/stderr | grep -q "READBACK $md5" &&
	echo "installed: sector $SECTOR, md5 $md5 (boot it with tools/sd_raw_boot.sh)" ||
	{ echo "not installed"; exit 1; }
