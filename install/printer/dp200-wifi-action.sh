#!/bin/sh
# wpa_cli action script (dp200-wifi.sh): $1 = interface, $2 = CONNECTED|DISCONNECTED.
# On every (re)connection make sure the address fits the network:
#  - static settings (network.json via dp200-netd.sh): re-applied
#  - same network as before: a running udhcpc only renews (SIGUSR1) - a mere
#    re-association (e.g. after a scan) must not cost the address
#  - a different network: new DHCP client (the old lease belongs elsewhere)
IF=$1
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PID=/var/run/udhcpc.$IF.pid
LAST=/var/run/dp200-wifi.$IF.ssid
case "$2" in
CONNECTED)
    SSID=$(wpa_cli -i $IF status | sed -n 's/^ssid=//p')
    if grep -q "\"$IF\":{[^}]*\"mode\":\"static\"" $ROOT/etc/dp200/network.json 2>/dev/null; then
        sh $ROOT/dp200/dp200-netd.sh $ROOT apply $IF
    elif [ -f $PID ] && kill -0 $(cat $PID) 2>/dev/null && [ "$SSID" = "$(cat $LAST 2>/dev/null)" ]; then
        kill -USR1 $(cat $PID)
    else
        [ -f $PID ] && kill $(cat $PID) 2>/dev/null
        udhcpc -b -i $IF -p $PID >/dev/null 2>&1
    fi
    echo "$SSID" > $LAST
    ;;
esac
