#!/bin/sh
# readtest.sh MODE ACK [NDCR_SET [DRAIN]]: one configuration of the bch_v1 read switches
P=/sys/module/marvell_nand/parameters
echo $1 > $P/read_mode; echo $2 > $P/ack_early; echo ${3:-0} > $P/ndcr_set
echo 0,0,0,0,0,0,0,0,0,0,0,0 > $P/stats; echo ${4:-0} > $P/drain
sh /root/klog.sh mark >/dev/null
echo "== read_mode $1 ack_early $2 ndcr_set ${3:-0} drain ${4:-0}"
python3 /root/nand_hammer.py 2000 10305 12161 9024
python3 /root/nand_readcheck.py /dev/mtd0 298b7390ccb500998661949c02ea68f8 \
	/dev/mtd3 8357ce022c8e407801c12bc29a39be82 \
	/dev/mtd5 9a14a0cad1043419214eded3dbd7645a
echo "STATS clean,cor,erased,retry,failed,timeout,early_unc,early_cor,rdd_unc,end_unc,extra_reads,extra_bytes = $(cat $P/stats)"
python3 /root/nfcregs.py | grep '+14 ' | sed 's/^/IDLE /'
sh /root/klog.sh check | tail -3
echo 0 > $P/ndcr_set; echo 0 > $P/read_mode
