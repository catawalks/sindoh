#!/bin/sh
# Stock-system Wi-Fi watcher (2026-11-17): one line per change of the
# access point / network name on mlan0, plus a heartbeat every 10 minutes.
# Log in RAM: /tmp/wifimon.log. Run: sh /tmp/wifimon.sh &
L=/tmp/wifimon.log
last=none
n=0
while true; do
	w=$(iwconfig mlan0 2>/dev/null)
	ap=$(echo "$w" | sed -n 's/.*Access Point: \([^ ]*\).*/\1/p')
	id=$(echo "$w" | sed -n 's/.*ESSID:"\([^"]*\)".*/\1/p')
	sig=$(echo "$w" | sed -n 's/.*Signal level[=:]\([^ ]*\).*/\1/p')
	ip=$(ifconfig mlan0 2>/dev/null | sed -n 's/.*inet addr:\([^ ]*\).*/\1/p')
	up=$(cut -d' ' -f1 /proc/uptime)
	cur="$ap|$id"
	n=$((n + 1))
	if [ "$cur" != "$last" ]; then
		echo "$(date '+%m-%d %H:%M:%S') up=$up CHANGE ap=$ap essid=$id sig=$sig ip=$ip" >> $L
		last=$cur
	elif [ $((n % 120)) -eq 0 ]; then
		echo "$(date '+%m-%d %H:%M:%S') up=$up beat ap=$ap essid=$id sig=$sig ip=$ip" >> $L
	fi
	sleep 5
done
