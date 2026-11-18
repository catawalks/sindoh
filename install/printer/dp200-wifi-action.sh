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
    # power saving after each (re)connection: on with our kernel (2026-11-17:
    # off, the AP dropped us every 91 s; on, no drop in hours), off with the
    # stock 3.2 kernel (2026-11-02: on, reason 15 drops every few minutes).
    # etc/dp200/wifi_power_save holding "on" or "off" overrides both.
    case "$(uname -r)" in 3.*) PS=off ;; *) PS=on ;; esac
    PSF=$ROOT/etc/dp200/wifi_power_save
    [ -s $PSF ] && case "$(cat $PSF)" in on|off) PS=$(cat $PSF) ;; esac
    iwconfig $IF power $PS 2>/dev/null || iw dev $IF set power_save $PS 2>/dev/null
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
