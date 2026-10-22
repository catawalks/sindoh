#!/bin/sh
# Front power button + reboot/power-off requests (stock BusyBox side, started
# by dp200-start.sh, runs as root outside the chroot).
#
# The button is GPIO bank 5 pin 27: 0xF8045000 bit 27, 1 = pressed (found
# 2026-10-22; it also shows as dec_sensor +0x210 bit 9). Short presses are
# the touch screen's job (it opens its POWER page).
#
# HARDWARE: holding the button ~2 s makes the power-management MCU cut the
# power at once (seen 2026-10-22), whatever Linux does. So on every press
# this loop syncs the filesystems straight away (a hold may follow). This
# loop handles:
#   - sync as soon as the button goes down;
#   - holding the button LONG_S seconds: forced shutdown, for boards where
#     the MCU does not cut the power (normally the hardware is faster);
#   - <root>/run/dp200/power containing "reboot" or "poweroff", written by the
#     screen's POWER page (the chroot can't shut the stock system down).
#
# Power-off: the stack is stopped (UPC cores held = heaters and motors off),
# the root is remounted read-only, then BusyBox poweroff. That only HALTS
# Linux: the supply stays on (tested 2026-10-22). No software power-off was
# found - the stock firmware's power key only did sleep/wake - so the user
# then holds the button ~2 s and the power-management MCU cuts the power.
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
    # Leave the Klipper root clean: init's "umount -a -r" can't remount it
    # read-only while the chroot mounts and our log files are open on it.
    exec >/dev/console 2>&1
    [ -f /var/run/dp200-netd.pid ] && kill $(cat /var/run/dp200-netd.pid) 2>/dev/null
    for p in $(ps | grep '[w]pa_cli' | awk '{print $1}'); do kill $p; done
    sleep 1
    . $ROOT/dp200/dp200-mounts.sh
    dp200_umount_root
    for m in var/log home/klipper/printer_data/logs; do
        grep -q " $ROOT/$m " /proc/mounts && umount $ROOT/$m
    done
    sync
    mount -o remount,ro $ROOT 2>/dev/null && echo "dp200-powerkey: $ROOT read-only" \
        || echo "dp200-powerkey: $ROOT still busy (journal will recover it)"
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
        # the hardware may cut the power in ~2 s: flush the cards now
        [ $held -eq 0 ] && sync
        held=$((held + 1))
        if [ $held -ge $((LONG_S * 5)) ]; then
            echo "dp200-powerkey: button held ${LONG_S} s"
            shutdown_now poweroff
            exit 0
        fi
    else
        held=0
    fi
    sleep 0.2 2>/dev/null || usleep 200000
done
