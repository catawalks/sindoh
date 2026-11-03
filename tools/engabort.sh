#!/bin/sh
# ABORT test, X (engine 0), driver DISABLED (+0x0c bit 0 = 1, no motion):
# start a 4 s move, abort after ~1 s, check busy clears and +0x78 freezes.
B=$((0xf8150000))
rd() { busybox devmem $((B + $1)) 32; }
wr() { busybox devmem $((B + $1)) 32 $2; }
CFG=`rd 0x0c`
if [ $((CFG & 1)) != 1 ]; then echo "ABORT: X driver enabled (cfg $CFG)"; exit 1; fi
S58=`rd 0x58`; S5C=`rd 0x5c`
C0=`rd 0x78`
wr 0x8c 0x100; wr 0x58 13333; wr 0x5c $(( (60000 << 16) | 1 )); wr 0x60 1
sleep 1
echo "running: 78=`rd 0x78` 64=`rd 0x64` 88=`rd 0x88`"
C1=`rd 0x78`; wr 0x04 0x100; C2=`rd 0x78`
echo "abort: before $C1 after $C2 64=`rd 0x64` 88=`rd 0x88`"
sleep 1
echo "1 s later: 78=`rd 0x78` 64=`rd 0x64` (frozen = stopped)"
echo "edges made: $(( (C0 - C2) & 0xffffff )) of 60000 (start counter $C0)"
wr 0x8c 0x100; wr 0x58 $S58; wr 0x5c $S5C
echo "restored 58=`rd 0x58` 5c=`rd 0x5c` cfg=`rd 0x0c`"
