#!/bin/sh
# Front power button + reboot/power-off requests (stock BusyBox side, started
# by dp200-start.sh, runs as root outside the chroot).
#
# The button is GPIO bank 5 pin 27: 0xF8045000 bit 27, 1 = pressed (found
# 2026-10-22; it also shows as dec_sensor +0x210 bit 9). Short presses are
# the touch screen's job (it opens its POWER page). This loop handles:
#   - holding the button LONG_S seconds: forced shutdown, works even when
#     Klipper or the screen has hung;
#   - <root>/run/dp200/power containing "reboot" or "poweroff", written by the
#     screen's POWER page (the chroot can't shut the stock system down).
#
# Power-off: the stack is stopped (UPC cores held = heaters and motors off),
# then BusyBox poweroff. If the board's supply stays on (SW1-4 open: the
# power-management MCU doesn't control the DC-DC), Linux is halted and the
# printer is safe to switch off at the mains switch.
#
#   dp200-powerkey.sh ROOT
ROOT=${1:?usage: dp200-powerkey.sh ROOT}
REQ=$ROOT/run/dp200/power
KEY_REG=0xF8045000
KEY_BIT=$((1 << 27))
LONG_S=5

pressed() { [ $(( $(devmem $KEY_REG 32) & KEY_BIT )) -ne 0 ]; }

shutdown_now() {        # $1 = reboot | poweroff
    echo "dp200-powerkey: $1 $(date)"
    # stop Klipper & co (holds the UPC cores: heaters/motors off), at most 30 s
    sh $ROOT/dp200/dp200-start.sh stop &
    s=$!
    i=0
    while kill -0 $s 2>/dev/null && [ $i -lt 30 ]; do sleep 1; i=$((i + 1)); done
    kill -0 $s 2>/dev/null && { echo "dp200-powerkey: stop timed out"; kill $s; }
    sync
    if [ "$1" = reboot ]; then
        reboot
    else
        poweroff
    fi
    # init didn't take it down within 20 s: force it
    sleep 20
    sync
    if [ "$1" = reboot ]; then reboot -f; else poweroff -f; fi
}

held=0
while true; do
    if [ -f $REQ ]; then
        what=$(cat $REQ 2>/dev/null)
        rm -f $REQ
        case "$what" in
        reboot|poweroff) shutdown_now $what; exit 0 ;;
        *) echo "dp200-powerkey: ignored request '$what'" ;;
        esac
    fi
    if pressed; then
        held=$((held + 1))
        if [ $held -ge $((LONG_S * 2)) ]; then
            echo "dp200-powerkey: button held ${LONG_S} s"
            shutdown_now poweroff
            exit 0
        fi
    else
        held=0
    fi
    sleep 0.5 2>/dev/null || usleep 500000
done
