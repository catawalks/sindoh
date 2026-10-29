#!/bin/sh
# Ethernet loader checks (replaces the full m1-checks.sh in this variant),
# then the fast path: unless stopped, run ethload with the defaults from
# /etc/ethload.conf (build.sh: ETHLOAD_PC, ETHLOAD_PORT, ETHLOAD_FILE) to
# kexec the kernel the PC serves. Kernel arguments override them:
# ethload.pc=ADDR ethload.port=N ethload.file=NAME, ethload.off skips it.
echo
echo "=== DP200 eth loader: $(uname -a)"
echo "--- cmdline: $(cat /proc/cmdline)"
echo "--- MDIO PHYs: $(for p in /sys/bus/mdio_bus/devices/*:*; do echo "$p $(cat $p/phy_id)"; done)"
echo "--- PHY reset GPIO 62 (bank B bit 30): in $(devmem 0xf8041000) out $(devmem 0xf8041004) dir $(devmem 0xf8041008) pincfg $(devmem 0xf80410f8)"

PC= PORT=8000 FILE= AUTO=1
[ -f /etc/ethload.conf ] && . /etc/ethload.conf
for a in $(cat /proc/cmdline); do
	case $a in
	ethload.pc=*)	PC=${a#*=} ;;
	ethload.port=*)	PORT=${a#*=} ;;
	ethload.file=*)	FILE=${a#*=} ;;
	ethload.off)	AUTO=0 ;;
	esac
done

echo "=== type 'ethload <pc-address> [file]' (static 10.10.0.250/24),"
echo "    or 'ethload dhcp <pc-address> [file]'"
[ $AUTO = 1 ] && [ -n "$PC" ] && [ -n "$FILE" ] || exit 0

echo "=== fast path: ethload $PC $FILE (port $PORT) in 3 s; press Enter for a shell"
if read -t 3 _; then
	echo "=== fast path stopped"
	exit 0
fi
PORT=$PORT ethload "$PC" "$FILE" || echo "=== fast path failed: shell"
