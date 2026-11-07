#!/bin/sh
# NAND-root + Wi-Fi soak (2026-11-07). Results as "SOAK ..." kernel log
# lines (reach the PC via the dmesg stream and netconsole). Read-only on
# NAND apart from normal system activity. usage: soak.sh SECONDS
DUR=${1:-10800}
PC=10.10.0.85
GW=10.10.0.1
K() { echo "SOAK $*" > /dev/kmsg; }
ip route add $PC/32 dev eth0 2>/dev/null
mountpoint -q /sys/kernel/config || mount -t configfs none /sys/kernel/config
N=/sys/kernel/config/netconsole/pc
[ -d $N ] || { mkdir -p $N; echo eth0 > $N/dev_name; echo $PC > $N/remote_ip; echo 6666 > $N/remote_port; echo 1 > $N/enabled; }
dmesg -n 8
(dmesg -w | busybox nc $PC 9005 > /dev/null 2>&1 &)
(while :; do echo "HB $(date +%T) up $(cut -d" " -f1 /proc/uptime) load $(cut -d" " -f1-3 /proc/loadavg) mlan0 $(cat /sys/class/net/mlan0/operstate 2>/dev/null) $(ip -4 -br addr show mlan0 2>/dev/null | awk '{print $3}')"; sleep 5; done | busybox nc $PC 9006 > /dev/null 2>&1 &)
K "START dur $DUR kernel $(uname -v | cut -c1-40)"
t0=$(cut -d. -f1 /proc/uptime); n=0
while [ $(( $(cut -d. -f1 /proc/uptime) - t0 )) -lt $DUR ]; do
	# Wi-Fi: 20 pings to the router over mlan0 every minute (the PC drops pings)
	p=$(ping -I mlan0 -c 20 -i 0.5 -W 1 $GW 2>&1 | grep -E "packet loss|rtt")
	K "PING $(echo $p | tr '\n' ' ')"
	# Wi-Fi: a 2.8 MB download over mlan0 every 5 minutes
	if [ $((n % 5)) -eq 0 ]; then
		K "WDL $(curl --interface mlan0 -s -m 60 -o /dev/null -w '%{http_code} %{size_download} %{time_total}s' http://$PC:8099/m1-nandboot.uimg)"
	fi
	# NAND: a full read of the root every 10 minutes
	if [ $((n % 10)) -eq 0 ]; then
		K "TAR start"
		K "TAR done $(tar -C / --one-file-system -cf - . 2>/dev/null | wc -c) bytes"
	fi
	n=$((n + 1))
	sleep 30
done
K "DONE after $n cycles"
