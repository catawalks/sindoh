#!/bin/sh
# read each listed chip page of mtd5 N times (corrected reads); print
# ecc_failures / corrected deltas and the distinct md5s seen
N=${N:-10}
S=/sys/class/mtd/mtd5
for p in "$@"; do
	off=$(( (p - 141 * 64) * 2048 ))
	f0=$(cat $S/ecc_failures); c0=$(cat $S/corrected_bits)
	sums=$(i=0; while [ $i -lt $N ]; do
		nanddump -q -s $off -l 2048 -f /tmp/pg /dev/mtd5 2>/dev/null; md5sum < /tmp/pg | cut -c1-8
		i=$((i+1)); done | sort | uniq -c | tr '\n' ' ')
	echo "page $p: failed $(( $(cat $S/ecc_failures) - f0 ))/$N corrected_bits +$(( $(cat $S/corrected_bits) - c0 )) md5s: $sums"
done
