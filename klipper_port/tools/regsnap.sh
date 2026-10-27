#!/bin/sh
# Print a snapshot of SoC registers that could affect the motor drivers
# (read only): APB config / pinmux, GPIO banks, step engines, PWM blocks.
#   sh regsnap.sh > /mnt/sd/regsnap_NAME.txt
# Compare two snapshots on the PC with diff.
dump() {   # base length
    a=$(($1)); e=$(($1 + $2))
    while [ $a -lt $e ]; do
        printf '%08x %s\n' $a $(devmem $a)
        a=$((a + 4))
    done
}
dump 0xf8000000 0x300                       # apb_config (pinmux)
for b in 0 1 2 3 4 5 6 7; do dump $((0xf8040000 + 0x1000 * b)) 0x54; done
for n in 0 1 2 3 4; do dump $((0xf8150000 + 0x1000 * n)) 0x100; done
dump 0xf8140000 0x40                        # dcmotor blocks
dump 0xf8141000 0x40
dump 0xf8142000 0x40
dump 0xf9304000 0x2000                      # dec_pwm blocks
