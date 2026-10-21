#!/bin/sh
# wpa_cli action script (dp200-wifi.sh): $1 = interface, $2 = CONNECTED|DISCONNECTED.
# On every (re)connection make sure there is a DHCP lease. A running udhcpc is
# only asked to renew (SIGUSR1): restarting it would first drop the address,
# and a mere re-association (e.g. after a scan) must not cost the IP.
IF=$1
PID=/var/run/udhcpc.$IF.pid
case "$2" in
CONNECTED)
    if [ -f $PID ] && kill -0 $(cat $PID) 2>/dev/null; then
        kill -USR1 $(cat $PID)
    else
        udhcpc -b -i $IF -p $PID >/dev/null 2>&1
    fi
    ;;
esac
