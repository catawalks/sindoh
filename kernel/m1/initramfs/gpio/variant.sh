#!/bin/sh
# gpio variant: the banks are registered, nothing is requested or driven
mount -t debugfs debugfs /sys/kernel/debug 2>/dev/null
dmesg | grep -i 'gpio'
ls /sys/bus/gpio/devices
cat /sys/kernel/debug/gpio
echo "--- bank registers (in out dir), compare with the probe lines above:"
for b in 0 1 2 3 4 5 6 7; do
	a=$((0xf8040000 + 0x1000 * b))
	echo "  bank $b: $(devmem $a) $(devmem $((a + 4))) $(devmem $((a + 8)))"
done
