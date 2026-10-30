#!/bin/sh
# xena-dump.sh: READ-ONLY dump of the XENA input configuration, to diff
# stock (upc.ko + Sindoh firmware) against mainline (probe firmware).
# XENA is the UPC's local block: core address 0x08000000 = phys 0xf9208000
# (CPUSoftReset 0xf9208154). Only configuration and input registers are
# read; mailboxes and GPStatus are left alone.
#   XIIC[n]  0xf9209268 + 4n, n = 0..63   per-pin config (stock FM sets
#            n = 42 43 44 46 to 0 and n = 20 to 0x40000149)
#   XIRW     0xf9209650                    stock FM sets bit 20
#   XIRD     0xf9209658, XIRD1 0xf920965c  pin levels 0..31 / 32..63
# Works with BusyBox devmem on stock and on mainline:
#   sh xena-dump.sh > /tmp/xena.txt
X=0xf9209000
i=0
while [ $i -lt 64 ]; do
	printf 'XIIC[%d]=%s\n' $i "$(devmem $((X + 0x268 + 4 * i)))"
	i=$((i + 1))
done
for o in 0x640 0x644 0x648 0x64c 0x650 0x654 0x658 0x65c 0x660 0x664 0x668 0x66c; do
	printf '%#x=%s\n' $((X + o)) "$(devmem $((X + o)))"
done
