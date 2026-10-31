#!/bin/sh
# WiFi client for Klipper mode (stock BusyBox side, run by dp200-start.sh).
#
# The stock /etc/profile loads the WiFi driver and starts wpa_supplicant with
# a placeholder config BEFORE the /DEBUG_MACHINE check, but joining the
# owner's network is the stock app's job - and that app does not run in
# Klipper mode. This script takes over:
#   1. first run: creates <root>/etc/dp200/wpa_supplicant.conf and imports
#      the SECURED networks saved by the stock firmware (/app/nvram/karas.db);
#      open networks are not imported (no auto-joining of hotspots)
#   2. leaves the stock wpa_supplicant running (dp200_wifi.py loads the saved
#      networks into it; the touch screen adds/forgets networks the same way)
#   3. runs wpa_cli in action mode: on every (re)connect the DHCP client is
#      restarted (dp200-wifi-action.sh); wired Ethernet gets DHCP too
#
#   sh dp200-wifi.sh [ROOT]
ROOT=${1:-$(cd "$(dirname "$0")/.." && pwd)}
IF=mlan0
CONF=$ROOT/etc/dp200/wpa_supplicant.conf
DB=/app/nvram/karas.db
ACTION=$ROOT/dp200/dp200-wifi-action.sh

log() { echo "dp200-wifi: $*"; }

import_stock() {
    mkdir -p $(dirname $CONF)
    umask 077
    {
        echo "# Written by dp200-wifi.sh; the touch screen adds/removes networks here."
        echo "ctrl_interface=/var/run/wpa_supplicant"
        [ -f $DB ] && sqlite3 $DB "
            select 'network={' || x'0a' ||
                   '	ssid=' || lower(hex(SSID)) || x'0a' ||
                   '	psk=\"' || Passkey1 || '\"' || x'0a' ||
                   '	key_mgmt=WPA-PSK' || x'0a' ||
                   '	priority=' || (case when SSID = '$CUR' then 20
                                         when ifSelected = 1 then 10 else 5 end) || x'0a' ||
                   '}'
            from recd_SSIDBOOK
            where length(SSID) > 0 and AuthType <> 0
              and length(Passkey1) between 8 and 63
            group by SSID having NO = max(NO);" 2>/dev/null
    } > $CONF
    chmod 600 $CONF
    log "created $CONF with $(grep -c '^network=' $CONF) network(s) from the stock settings"
}

[ -d /proc/mwlan ] || [ -e /sys/class/net/$IF ] || log "no WiFi module"
# the network the radio is on right now (if any) gets the top priority
CUR=$(wpa_cli -i $IF status 2>/dev/null | sed -n 's/^ssid=//p' | sed "s/'/''/g")
[ -f $CONF ] || import_stock

# The stock wpa_supplicant keeps running: restarting it leaves the Marvell
# driver unable to scan for a while. The saved networks are loaded into it by
# "dp200_wifi.py apply" (rc.dp200, inside the chroot, over the control socket).
# pidof first: under Debian (a mainline boot, ROOT=/), procps' bare "ps"
# only lists processes on the current terminal
if ! { pidof wpa_supplicant >/dev/null 2>&1 || ps | grep -q '[w]pa_supplicant'; }; then
    log "no wpa_supplicant running - starting it like the stock boot"
    mkdir -p /var/run/wpa_supplicant
    if [ "$ROOT" = / ]; then
        # mainline (mwifiex): nl80211 and this root's own config; the stock
        # /etc/wpa_supplicant.conf only exists on the stock side
        [ -e /sys/class/net/$IF ] && wpa_supplicant -Dnl80211 -P /var/run/wpa_supplicant.$IF.pid \
            -i$IF -c$CONF -B
    else
        iwpriv $IF regioncode 48 2>/dev/null
        wpa_supplicant -Dwext -P /var/run/wpa_supplicant.$IF.pid -O /var/run/wpa_supplicant \
            -i$IF -c/etc/wpa_supplicant.conf -B
    fi
fi
{ ps -ef 2>/dev/null || ps; } | grep -q '[w]pa_cli.*-a' || wpa_cli -B -i $IF -a $ACTION || log "wpa_cli action daemon failed"

# Ethernet, if a cable is plugged in
if [ "$(cat /sys/class/net/eth0/carrier 2>/dev/null)" = 1 ]; then
    udhcpc -b -i eth0 -p /var/run/udhcpc.eth0.pid >/dev/null 2>&1
fi
log "started on $IF"
