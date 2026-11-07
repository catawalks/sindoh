#!/bin/sh
# Hang logger for our kernel (2026-11-07): what the running kernel exposes
# without a rebuild, once a second, to the SD card (synced every line, so it
# survives a hard hang up to the last second the bus worked) and to the PC.
# Read-only on NAND. Card: the 4GB-SD's partition 1, mounted at /mnt/hanglog
# (rw; nothing else uses it on a NAND root). Logs in
# /mnt/hanglog/var/log/dp200-hang/<boot time>.{stat,dmesg}.
# usage: hang_logger.sh [PC_IP]   (run with setsid; stops at reboot)
PC=${1:-10.10.0.85}
M=/mnt/hanglog
mkdir -p $M
mountpoint -q $M || mount -t ext4 -o rw,noatime /dev/mmcblk0p1 $M || { echo "no card"; exit 1; }
D=$M/var/log/dp200-hang
mkdir -p $D
B=$D/$(date +%Y%m%d-%H%M%S)-up$(cut -d. -f1 /proc/uptime)
ip route add $PC/32 dev eth0 2>/dev/null
# the kernel log, live, to the card (synced by the loop below)
(dmesg -w >> $B.dmesg 2>&1 &)
echo "# uname $(uname -v)" > $B.stat
echo "# fields: up load | nand reads clean,cor,erased,retry,fail,tmo,early_unc,early_cor,rdd_unc,end_unc | ubi max_ec avail | dirty/writeback kB | nr_dirtied nr_written | irq nand mmc usb2 eth timer1 | ipi resched c0/c1 fcall c0/c1 | ctxt" >> $B.stat
sync $B.stat
# the PC copy follows the card file, so a lost connection never stops the
# card log (port 9006)
(tail -n +1 -f $B.stat | busybox nc $PC 9006 > /dev/null 2>&1 &)
# one line a second to the card, fsynced
while :; do
	i=/proc/interrupts
	l="$(cut -d' ' -f1 /proc/uptime) $(cut -d' ' -f1-3 /proc/loadavg)"
	l="$l | nand $(cat /sys/module/marvell_nand/parameters/stats)"
	l="$l | ubi $(cat /sys/class/ubi/ubi0/max_ec 2>/dev/null) $(cat /sys/class/ubi/ubi0/avail_eraseblocks 2>/dev/null)"
	l="$l | $(awk '/^Dirty:/ {d=$2} /^Writeback:/ {w=$2} END {print d "/" w}' /proc/meminfo)"
	l="$l | $(awk '/^nr_dirtied / {d=$2} /^nr_written / {w=$2} END {print d, w}' /proc/vmstat)"
	l="$l | irq $(awk '/marvell-nfc/ {a=$2} /mmc0/ {b=$2} /usb2/ {c=$2} /eth0/ {d=$2} /timer1/ {e=$2} END {print a, b, c, d, e}' $i)"
	l="$l | ipi $(awk '/Rescheduling/ {r=$2 "/" $3} /Function call/ {f=$2 "/" $3} END {print r, f}' $i)"
	l="$l | $(awk '/^ctxt/ {print $2}' /proc/stat)"
	echo "$l" >> $B.stat
	sync $B.stat $B.dmesg
	sleep 1
done
