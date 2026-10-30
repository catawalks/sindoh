#!/bin/sh
# gpio variant: the banks are registered read-only (marvell,read-only):
# requesting a line keeps its pin function, output and direction changes
# are refused. Only reads below.
mount -t debugfs debugfs /sys/kernel/debug 2>/dev/null
dmesg | grep -i 'gpio'
ls /sys/bus/gpio/devices
echo "--- bank registers (in out dir), compare with the probe lines above:"
for b in 0 1 2 3 4 5 6 7; do
	a=$((0xf8040000 + 0x1000 * b))
	echo "  bank $b: $(devmem $a) $(devmem $((a + 4))) $(devmem $((a + 8)))"
done

# global number of line L in bank B (chip label f80[4-7]B000.gpio)
gnum() {
	for c in /sys/class/gpio/gpiochip*; do
		case $(cat $c/label) in
		f804${1}000.gpio) echo $(( $(cat $c/base) + $2 )); return ;;
		esac
	done
}
# read: bank, line; export, read direction and value, compare with devmem
rd() {
	g=$(gnum $1 $2)
	[ -n "$g" ] || { echo "  bank $1 line $2: no gpiochip"; return; }
	if echo $g > /sys/class/gpio/export 2>/dev/null; then
		v=$(cat /sys/class/gpio/gpio$g/value) d=$(cat /sys/class/gpio/gpio$g/direction)
		raw=$(( ($(devmem $((0xf8040000 + 0x1000 * $1))) >> $2) & 1 ))
		echo "  bank $1 line $2 (gpio$g): $d value $v, input register bit $raw"
		echo $g > /sys/class/gpio/unexport
	else
		echo "  bank $1 line $2 (gpio$g): export refused (pin has another function)"
	fi
}
echo "--- sysfs reads (GPIO-function inputs: bank 4 lines 1 and 10, the X endstop pad bank 5 line 20):"
rd 4 1
rd 4 10
rd 5 20
echo "--- must be refused (Ethernet RGMII pad, function 1 after the loader):"
rd 1 16
echo "--- an output request must fail (EPERM), without touching the hardware:"
g=$(gnum 4 1)
echo $g > /sys/class/gpio/export && {
	echo out > /sys/class/gpio/gpio$g/direction 2>&1 && echo "  NOT REFUSED" || echo "  refused, as it must be"
	echo "  bank 4 dir after: $(devmem 0xf8044008)"
	echo $g > /sys/class/gpio/unexport
}
