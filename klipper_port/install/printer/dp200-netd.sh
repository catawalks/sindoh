#!/bin/sh
# Network settings service (stock BusyBox side, started by dp200-start.sh).
#
# <root>/etc/dp200/network.json holds per-interface settings written by the
# touch screen, e.g.
#   {"mlan0": {"mode": "dhcp"},
#    "eth0": {"mode": "static", "ip": "10.0.0.50", "mask": "255.255.255.0",
#             "gw": "10.0.0.1", "dns": "10.0.0.1"}}
# Missing interface or file = DHCP. The screen (inside the chroot) can't run
# the stock tools, so it writes the file and touches <root>/run/dp200/net-apply;
# this loop applies it within ~3 s. It also starts DHCP on Ethernet when a cable
# is plugged in, and is used by dp200-wifi-action.sh on WiFi (re)connects.
#
#   dp200-netd.sh ROOT            run the loop (background)
#   dp200-netd.sh ROOT apply IF   apply the settings of one interface now
ROOT=${1:?usage: dp200-netd.sh ROOT [apply IF]}
CONF=$ROOT/etc/dp200/network.json
TRIGGER=$ROOT/run/dp200/net-apply

# get IF KEY -> value from network.json (flat JSON written by the screen; no jq here)
get() {
    [ -f $CONF ] || return
    tr -d '\n ' < $CONF | sed -n "s/.*\"$1\":{\([^}]*\)}.*/\1/p" | tr ',' '\n' |
        sed -n "s/^\"$2\":\"\(.*\)\"$/\1/p"
}

dhcp_running() { [ -f /var/run/udhcpc.$1.pid ] && kill -0 $(cat /var/run/udhcpc.$1.pid) 2>/dev/null; }
dhcp_stop() { dhcp_running $1 && kill $(cat /var/run/udhcpc.$1.pid); rm -f /var/run/udhcpc.$1.pid; }

write_dns() {        # $1 = nameserver; stock side and the Klipper chroot
    echo "nameserver $1" > /etc/resolv.conf
    cp /etc/resolv.conf $ROOT/etc/resolv.conf 2>/dev/null
}

apply() {
    IF=$1
    if [ "$(get $IF mode)" = static ]; then
        IP=$(get $IF ip); MASK=$(get $IF mask); GW=$(get $IF gw); DNS=$(get $IF dns)
        [ -n "$IP" ] && [ -n "$MASK" ] || { echo "dp200-netd: $IF static without ip/mask"; return 1; }
        dhcp_stop $IF
        ifconfig $IF $IP netmask $MASK up
        while route del default dev $IF 2>/dev/null; do :; done
        [ -n "$GW" ] && route add default gw $GW dev $IF
        [ -n "$DNS" ] && write_dns $DNS
        echo "dp200-netd: $IF static $IP/$MASK gw ${GW:--} dns ${DNS:--}"
    else
        # DHCP: wired only with a cable; WiFi only when associated (the
        # wpa_cli action script handles reconnects)
        if [ $IF = eth0 ] && [ "$(cat /sys/class/net/eth0/carrier 2>/dev/null)" != 1 ]; then
            dhcp_stop $IF
            return 0
        fi
        dhcp_running $IF || udhcpc -b -i $IF -p /var/run/udhcpc.$IF.pid >/dev/null 2>&1
        # udhcpc's default script writes /etc/resolv.conf; keep the chroot in sync
        cp /etc/resolv.conf $ROOT/etc/resolv.conf 2>/dev/null
    fi
}

if [ "$2" = apply ]; then
    apply $3
    exit
fi

ip link set eth0 up 2>/dev/null
LAST_CARRIER=
while true; do
    if [ -f $TRIGGER ]; then
        rm -f $TRIGGER
        apply eth0
        apply mlan0
    fi
    C=$(cat /sys/class/net/eth0/carrier 2>/dev/null)
    if [ "$C" != "$LAST_CARRIER" ]; then           # cable plugged in / pulled
        LAST_CARRIER=$C
        apply eth0
    fi
    # keep the chroot's DNS in step with DHCP renewals
    cmp -s /etc/resolv.conf $ROOT/etc/resolv.conf || cp /etc/resolv.conf $ROOT/etc/resolv.conf 2>/dev/null
    sleep 3
done
