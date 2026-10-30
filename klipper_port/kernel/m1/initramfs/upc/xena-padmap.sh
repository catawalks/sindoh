#!/bin/sh
# xena-padmap.sh: READ-ONLY. Which SoC pads carry the XENA inputs?
#
# Prints, once a second, the GPIO input registers of banks 4, 5 and 6
# (0xf8044000, 0xf8045000, 0xf8046000) next to XENA XIRD/XIRD1
# (0xf9209658/c). Under mainline the candidate UPC pads are still GPIO
# inputs, so their GPIO input bit already shows the pad level. While it
# runs, press the Y endstop, move the X carriage off its switch, and move
# the cartridge lever. The GPIO bit that toggles with each action is that
# input's pad. Under stock the same works with the pads in their UPC
# functions (XIRD toggles too there). Ctrl-C to stop.
#   sh xena-padmap.sh [seconds]
n=${1:-30}
prev=
while [ $n -gt 0 ]; do
	cur="b4=$(devmem 0xf8044000) b5=$(devmem 0xf8045000) b6=$(devmem 0xf8046000) XIRD=$(devmem 0xf9209658) XIRD1=$(devmem 0xf920965c)"
	[ "$cur" != "$prev" ] && echo "$(cut -d' ' -f1 /proc/uptime) $cur"
	prev=$cur
	sleep 1
	n=$((n - 1))
done
