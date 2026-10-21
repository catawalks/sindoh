# Network settings (WiFi + Ethernet)

Touch screen: **SYSTEM → NETWORK**. It's also reachable from the "Waiting
for Klipper" and error pages.

- **Overview:** for WiFi (`mlan0`) and Ethernet (`eth0`): link (network
  name / cable), IP / netmask, gateway, **MAC address**, and mode
  (DHCP or static). Also the DNS server(s). Refreshed every 3 s.
- **WIFI:** the WiFi setup (scan, keyboard, hidden, forget: docs/wifi.md).
- **WIFI IP / ETHERNET IP:**
  - choose **DHCP** or **STATIC**;
  - static fields (IP, netmask, gateway, DNS) are entered on a numeric
    keypad and validated: the IP must be 4 numbers 0–255, the netmask a
    contiguous mask, and gateway/DNS are optional;
  - **SAVE & APPLY** asks first, since the connection can drop for a moment.

## How it's applied

| Piece | Where | Role |
|---|---|---|
| `install/display/dp200_net.py` | chroot | Port info: /sys for MAC and link, `SIOCGIFADDR`/`SIOCGIFNETMASK` ioctls for the address, `/proc/net/route` for the gateway, `/etc/resolv.conf`. Debian's `ip ... dev X` fails on kernel 3.2 ("RTNETLINK answers: Invalid argument"). It writes `/etc/dp200/network.json` (compact JSON) and touches `/run/dp200/net-apply`. |
| `install/printer/dp200-netd.sh` | stock side, started by dp200-start.sh | Loop (3 s). On the trigger it applies both ports: static = stop udhcpc, `ifconfig`, default route, resolv.conf; DHCP = start udhcpc. Ethernet: DHCP starts when a cable is plugged in, stops when pulled. Keeps the chroot's resolv.conf in sync. Log: `<root>/var/log/dp200-netd.log`. |
| `install/printer/dp200-wifi-action.sh` | stock side | On WiFi (re)connect: static → re-apply; same network → DHCP renew; **different network → new DHCP client**. Before that fix, a switch kept the old network's lease. |

`network.json` example:
```json
{"mlan0":{"mode":"dhcp"},"eth0":{"mode":"static","ip":"10.0.0.50","mask":"255.255.255.0","gw":"10.0.0.1","dns":"10.0.0.1"}}
```

## Preferred network (2026-10-22)

The printer had dropped from Niholedotcom to the second saved network,
Fios-kVGD7, **which is a different router and subnet**: 192.168.1.204,
unreachable from 10.10.0.x. `wpa_supplicant` never leaves a working
lower-priority network by itself. The screen app's watchdog now checks every
10 min: if a saved network with a higher priority is in range (better than
-70 dBm), it switches to it, and the back-up networks stay enabled.

## Not done

- No IPv6 settings; no VLANs; one DNS server per port.
- The stock side's /etc/resolv.conf is shared, so the last port applied wins.
