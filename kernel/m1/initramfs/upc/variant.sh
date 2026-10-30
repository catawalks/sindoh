#!/bin/sh
# upc variant: read-only checks; the driver held the cores and forced the
# outputs off at probe. Run again any time (sh /etc/m1-variant.sh), e.g.
# while the probe firmware runs: every output must still read off.
echo "--- UPC: $(ls /dev/upc* 2>/dev/null)"
dmesg | grep -i 'upc'
echo "--- CPUSoftReset $(devmem 0xf9208154) (0 = held, 1 = running), GPStatus $(devmem 0xf9208150)"
on= n=1
while [ $n -le 32 ]; do
	c=$(devmem $((0xf9304000 + 0x100 * n)))
	[ $((c & 5)) -ne 0 ] && on="$on pwm$n=$c"
	n=$((n + 1))
done
echo "--- PWM blocks 1-32 with run/level set (bits 0/2):${on:- none}"
echo "--- PWM CTRL blocks 1-5: $(for n in 1 2 3 4 5; do devmem $((0xf9304000 + 0x100 * n)); done)"
echo "--- stepper CFG 0-4 (bit 0 = driver off): $(for n in 0 1 2 3 4; do devmem $((0xf815000c + 0x1000 * n)); done)"
echo "--- UPC APB clocks 0xf8000180: $(devmem 0xf8000180)"
