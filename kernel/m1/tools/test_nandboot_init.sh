#!/bin/sh
# Offline test of initramfs/nandboot/init's decisions (no root, no
# hardware): every command that touches the system is a shell function
# that logs, and a scenario chooses what the "printer" has. Run with dash
# or busybox sh:  sh tools/test_nandboot_init.sh
M1=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
# the init with its absolute paths moved into $T, exec switch_root logged
sed -e "s#/newroot#$T/newroot#g" -e "s#/run#$T/run#g" \
    -e "s#^PATH=.*#:#" -e 's#^exec switch_root#switch_root#' \
    -e 's#dp200-revert.sh 2>#dp200_revert 2>#' \
    -e 's#\[ -c /dev/input/event0 \]#:#' \
    -e 's#\[ -b "\$d" \]#isdev "$d"#' \
    -e 's#/dev/mmcblk0p\* /dev/sd?1#/dev/mmcblk0p1 /dev/sda1#' \
    -e 's#/dev/sd?1 /dev/sd?;#/dev/sda1 /dev/sda;#' \
    -e "s#/sys/module/marvell_nand/parameters/write_window#$T/win#" \
    "$M1/initramfs/nandboot/init" > "$T/init"

run() {	# $1 = scenario name, the rest: variables of the scenario
	name=$1; shift
	rm -rf "$T/newroot" "$T/run" "$T/out"; mkdir -p "$T/newroot" "$T/run"
	echo 1741,4091 > "$T/win"
	(
	export "$@"
	log() { echo "$*" >> "$T/out"; }
	mount() {	# the last two arguments: device, directory
		eval d=\${$(($# - 1))}; eval m=\${$#}
		case "$d $m" in
		*" $T/newroot")
			case $d in
			ubi0:filesystem) [ "${UBIROOT:-}" ] || return 1
				[ "$UBIROOT" = revert ] && : > "$m/.dp200-revert"
				[ "$UBIROOT" = broken ] || { mkdir -p "$m/etc/dp200" "$m/run"
				: > "$m/etc/dp200/init.mainline"; chmod +x "$m/etc/dp200/init.mainline"; } ;;
			"${CARD:-none}") : > "$m/.dp200-root"; mkdir -p "$m/etc/dp200" "$m/run"
				: > "$m/etc/dp200/init.mainline"; chmod +x "$m/etc/dp200/init.mainline" ;;
			*) return 1 ;;
			esac
			echo "$d" > "$T/mounted" ;;
		*/stick)
			[ "$d" = "${STICKDEV:-none}" ] || return 1
			mkdir -p "$m/_update_rodin"; : > "$m/_update_rodin/${STICKFILE}" ;;
		esac
		return 0
	}
	umount() { [ "$1" = "$T/newroot" ] && rm -rf "$T/newroot" && mkdir -p "$T/newroot"; return 0; }
	mountpoint() { return 1; }
	ls() { return 0; }
	sleep() { [ "$1" = 3600 ] && { log STOPPED; exit 0; }; :; }
	mkdir() { command mkdir "$@" 2>/dev/null; return 0; }
	tee() { cat >> "$T/out"; }
	ubiattach() { log "ubiattach $*"; }
	ubidetach() { log "ubidetach $*"; }
	timeout() { [ "${TOUCH:-no}" = yes ]; }
	isdev() { case $1 in "${CARD:-none}"|"${STICKDEV:-none}") return 0 ;; esac; return 1; }
	dp200_revert() { log "REVERT window=$(cat "$T/win")"; return ${REVRC:-0}; }
	reboot() { log "reboot $*"; exit 0; }
	setsid() { log "SHELL"; }
	switch_root() { log "switch_root $* (root $(cat "$T/mounted"))"; exit 0; }
	cp() { :; }
	. "$T/init"
	) > /dev/null 2>&1
	printf '%-28s ' "$name"; grep -E "REVERT|switch_root|SHELL|reboot|STOPPED" "$T/out" | tr '\n' ' '; echo
}

# the "printer's" devices: a card partition and a stick
SD=/dev/mmcblk0p1 STK=/dev/sda1
run "mtd6 root" UBIROOT=ok
run "marked card first" UBIROOT=ok CARD="${SD:-x}"
run "root marker -> revert" UBIROOT=revert
run "Sindoh stick, touched" UBIROOT=ok STICKDEV="${STK:-x}" STICKFILE=update.she TOUCH=yes
run "Sindoh stick, no touch" UBIROOT=ok STICKDEV="${STK:-x}" STICKFILE=update.she TOUCH=no
run "revert stick, touched" UBIROOT=ok STICKDEV="${STK:-x}" STICKFILE=dp200-revert TOUCH=yes
run "broken root, touched" UBIROOT=broken TOUCH=yes
run "broken root, no touch" UBIROOT=broken TOUCH=no
run "revert fails" UBIROOT=revert REVRC=1

# The built image's initramfs list (if there is one): every tool that
# dp200-revert.sh checks for and that the init calls is in it, and the
# UBI/NAND tools are mtd-utils binaries, not BusyBox links (other options).
L=${IRFS_LIST:-$HOME/dp200/initramfs-m1-nandboot/initramfs.list}
if [ -f "$L" ]; then
	bad=0
	for t in ubiattach ubidetach ubiformat ubimkvol ubiupdatevol flash_erase \
		 nandwrite bzip2 tar cmp od awk md5sum mountpoint switch_root \
		 timeout tee setsid cttyhack dd dp200-revert.sh; do
		grep -qE "^(file|slink) /[a-z/]*/$t " "$L" || { echo "MISSING $t"; bad=1; }
	done
	for t in ubiattach ubidetach ubiformat ubimkvol ubiupdatevol flash_erase nandwrite; do
		grep -qE "^slink /[a-z/]*/$t " "$L" && { echo "BUSYBOX LINK $t"; bad=1; }
	done
	grep -q "^file /usr/sbin/recovery.md5 " "$L" || { echo "MISSING recovery.md5"; bad=1; }
	[ $bad = 0 ] && echo "initramfs list: all revert and init tools present"
else
	echo "(no $L: build VARIANT=nandboot for the list check)"
fi
