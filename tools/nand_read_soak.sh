#!/bin/sh
# NAND read soak for the interrupt-driven read fix (2026-11-07): every 2 min
# drop the page cache and read the whole root (UBIFS on mtd6); heartbeat to
# the PC every 5 s. Read-only on NAND. usage: irq_soak.sh SECONDS
DUR=${1:-14400}; PC=10.10.0.85
ip route add $PC/32 dev eth0 2>/dev/null
K=$(uname -v | cut -c1-30)
(while :; do echo "HB up $(cut -d" " -f1 /proc/uptime) nfc $(awk '/marvell-nfc/ {print $2}' /proc/interrupts) rdd_irq $(cat /sys/module/marvell_nand/parameters/rdd_irq) stats $(cat /sys/module/marvell_nand/parameters/stats) k $K"; sleep 5; done | busybox nc $PC 9006 > /dev/null 2>&1 &)
t0=$(cut -d. -f1 /proc/uptime); n=0
while [ $(( $(cut -d. -f1 /proc/uptime) - t0 )) -lt $DUR ]; do
	echo 3 > /proc/sys/vm/drop_caches
	echo "IRQSOAK TAR $n start" > /dev/kmsg
	echo "IRQSOAK TAR $n done $(tar -C / --one-file-system -cf - . 2>/dev/null | wc -c)" > /dev/kmsg
	n=$((n + 1)); sleep 120
done
echo "IRQSOAK DONE $n passes" > /dev/kmsg
