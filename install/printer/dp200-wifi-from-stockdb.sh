#!/bin/sh
# Join a WiFi network that the stock Sindoh firmware has saved, without the
# stock app: reads SSID + passphrase from /app/nvram/karas.db (RECD_SSIDBOOK)
# and hands them to the running wpa_supplicant. The passphrase is never
# printed.   sh dp200-wifi-from-stockdb.sh "SSID"
SSID=$1
DB=/app/nvram/karas.db
IF=mlan0
[ -n "$SSID" ] || { echo "usage: $0 SSID"; exit 2; }
PSK=$(sqlite3 $DB "select Passkey1 from recd_SSIDBOOK where SSID='$SSID' and length(Passkey1)>0 order by NO desc limit 1;")
[ -n "$PSK" ] || { echo "no saved passphrase for '$SSID'"; exit 1; }
W="wpa_cli -i $IF"
N=$($W add_network | tail -1)
$W set_network $N ssid "\"$SSID\"" >/dev/null
$W set_network $N psk "\"$PSK\"" >/dev/null
PSK=
$W select_network $N >/dev/null
for i in $(seq 1 20); do
    $W status | grep -q '^wpa_state=COMPLETED' && break
    sleep 1
done
$W status | grep -E '^(wpa_state|ssid)='
killall udhcpc 2>/dev/null
udhcpc -n -q -i $IF -p /var/run/udhcpc.$IF.pid >/dev/null 2>&1
ifconfig $IF | grep 'inet '
