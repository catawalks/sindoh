#!/bin/sh
# Ethernet loader checks (replaces the full m1-checks.sh in this variant)
echo
echo "=== DP200 eth loader: $(uname -a)"
echo "--- cmdline: $(cat /proc/cmdline)"
echo "--- MDIO PHYs: $(for p in /sys/bus/mdio_bus/devices/*:*; do echo "$p $(cat $p/phy_id)"; done)"
echo "--- PHY reset GPIO 62 (bank B bit 30): in $(devmem 0xf8041000) out $(devmem 0xf8041004) dir $(devmem 0xf8041008) pincfg $(devmem 0xf80410f8)"
echo "=== type 'ethload <pc-address> [file]' (static 10.10.0.250/24),"
echo "    or 'ethload dhcp <pc-address> [file]'"
