#!/bin/sh
# Engine test, X (engine 0), driver DISABLED (+0x0c bit 0 = 1): one long
# multi-step move with no motor current, sampling +0x78 (COM_STP?) and
# +0x64 against /proc/uptime. Registers it writes are saved and restored.
B=$((0xf8150000))
rd() { busybox devmem $((B + $1)) 32; }
wr() { busybox devmem $((B + $1)) 32 $2; }
CFG=`rd 0x0c`
if [ $((CFG & 1)) != 1 ]; then echo "ABORT: X driver enabled (cfg $CFG)"; exit 1; fi
S50=`rd 0x50`; S54=`rd 0x54`; S58=`rd 0x58`; S5C=`rd 0x5c`
echo "saved 50=$S50 54=$S54 58=$S58 5c=$S5C cfg=$CFG busy=`rd 0x64`"
EDGES=60000; PER=13333       # 30000 steps, 4.0 s at a 200 MHz engine clock
wr 0x8c 0x100
wr 0x58 $PER
wr 0x5c $(( (EDGES << 16) | 1 ))
T0=`cut -d' ' -f1 /proc/uptime`
wr 0x60 1
i=0
while [ $i -lt 400 ]; do
    t=`cut -d' ' -f1 /proc/uptime`
    echo "S $t `rd 0x78` `rd 0x64` `rd 0x88` `rd 0x0c`"
    [ $(( `rd 0x88` & 0x100 )) != 0 ] && break
    i=$((i + 1))
done
T1=`cut -d' ' -f1 /proc/uptime`
echo "start $T0 done-seen $T1 after $i samples"
echo "after: 78=`rd 0x78` 74=`rd 0x74` 70=`rd 0x70` 64=`rd 0x64` 88=`rd 0x88`"
# restore
wr 0x8c 0x100
wr 0x58 $S58; wr 0x5c $S5C; wr 0x54 $S54; wr 0x50 $S50
echo "restored 50=`rd 0x50` 54=`rd 0x54` 58=`rd 0x58` 5c=`rd 0x5c` cfg=`rd 0x0c` 88=`rd 0x88`"
