#!/bin/sh
# wpa_cli action script (dp200-wifi.sh): $1 = interface, $2 = CONNECTED|DISCONNECTED.
# On every (re)connection, restart the DHCP client so a new network gets a lease.
IF=$1
PID=/var/run/udhcpc.$IF.pid
case "$2" in
CONNECTED)
    [ -f $PID ] && kill $(cat $PID) 2>/dev/null
    udhcpc -b -i $IF -p $PID >/dev/null 2>&1
    ;;
esac
