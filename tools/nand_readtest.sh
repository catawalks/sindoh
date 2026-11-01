#!/bin/sh
# nand_readtest.sh: read checks of the bch_v1 driver against the stock
# dumps (2026-10-26 md5s), with the driver's read counters and the kernel
# log. Read-only. Runs on the printer (mainline) from /root.
P=/sys/module/marvell_nand/parameters
echo 0,0,0,0,0,0,0,0,0,0 > $P/stats
sh /root/klog.sh mark >/dev/null
echo "== readtest $(uname -v | cut -c1-30)"
python3 /root/nand_hammer.py 2000 10305 12161 9024
python3 /root/nand_readcheck.py /dev/mtd0 298b7390ccb500998661949c02ea68f8 \
	/dev/mtd3 8357ce022c8e407801c12bc29a39be82 \
	/dev/mtd5 9a14a0cad1043419214eded3dbd7645a
echo "STATS clean,cor,erased,retry,failed,timeout,early_unc,early_cor,rdd_unc,end_unc = $(cat $P/stats)"
python3 /root/nfcregs.py | grep '+14 ' | sed 's/^/IDLE /'
sh /root/klog.sh check | tail -3
