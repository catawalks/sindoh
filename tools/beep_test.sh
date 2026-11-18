#!/bin/sh
# Beeper test (owner present, listening): drive dec_pwm block 10 the way
# the stock app does (docs/hardware_notes.md "Beeper"), straight through
# /dev/mem, without Klipper. Block 10 is not used by Klipper's firmware.
#   sh beep_test.sh            three 120 ms beeps at the stock volumes 3, 6, 36 %
#   sh beep_test.sh HZ DUTY MS one beep: tone in Hz, duty in %, length in ms
# Stock: control 0x18 (timebase 1, one tick taken as 1 us), period 250 = 4 kHz.
B=0xf9304a00        # dec_pwm block 10 (0xf9304000 + 0x100 * 10)
G=0xf9304000        # global enable, bit 9 = block 10
dm() { busybox devmem "$@"; }

beep() {    # $1 Hz, $2 duty %, $3 ms
    per=$((1000000 / $1)); hi=$((per * $2 / 100)); [ $hi -lt 1 ] && hi=1
    dm $B 32 0x18                       # stopped, output low
    dm $((B + 4)) 32 4                  # delay count (stock)
    dm $((B + 8)) 32 $hi
    dm $((B + 12)) 32 $((per - hi))
    g=$(dm $G 32); dm $G 32 $((g | 0x200))
    dm $B 32 0x19                       # run
    sleep "$(awk "BEGIN{print $3/1000}")"
    dm $B 32 0x18                       # stop, output low
}

if [ $# -eq 3 ]; then
    beep "$1" "$2" "$3"
else
    for d in 3 6 36; do
        echo "4000 Hz, $d % duty, 120 ms"
        beep 4000 $d 120
        sleep 1
    done
fi
echo "beep_test: done (block 10 control $(dm $B 32))"
