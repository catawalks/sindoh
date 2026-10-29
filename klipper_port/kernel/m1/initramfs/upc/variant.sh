#!/bin/sh
# upc variant: read-only checks; the driver held the cores and forced the
# outputs off at probe
echo "--- UPC: $(ls /dev/upc* 2>/dev/null)"
dmesg | grep -i 'upc'
echo "--- CPUSoftReset $(devmem 0xf9208154) (0 = held), GPStatus $(devmem 0xf9208150)"
echo "--- PWM CTRL blocks 1-4: $(for n in 1 2 3 4; do devmem $((0xf9304000 + 0x100 * n)); done)"
echo "--- stepper CFG 0-4: $(for n in 0 1 2 3 4; do devmem $((0xf815000c + 0x1000 * n)); done)"
echo "--- UPC APB clocks 0xf8000180: $(devmem 0xf8000180)"
