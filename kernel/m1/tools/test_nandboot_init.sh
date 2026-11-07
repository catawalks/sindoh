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
    -e 's#dp200-hold #dp200_hold #' \
    -e 's#\[ -c /dev/input/event0 \]#:#' \
    -e 's#\[ -b "\$d" \]#isdev "$d"#' \
    -e 's#/dev/mmcblk0p\* /dev/sd?1#/dev/mmcblk0p1 /dev/sda1#' \
    -e 's#/dev/sd?1 /dev/sd?;#/dev/sda1 /dev/sda;#' \
    -e "s#/sys/module/marvell_nand/parameters/write_window#$T/win#" \
    -e "s#/dev/kmsg#$T/kmsg#g" -e 's#\[ -e /dev/ubi0 \]#:#' \
    "$M1/initramfs/nandboot/init" > "$T/init"

run() {	# $1 = scenario name, the rest: variables of the scenario
	name=$1; shift
	rm -rf "$T/newroot" "$T/run" "$T/out" "$T/detached"; : > "$T/kmsg"; mkdir -p "$T/newroot" "$T/run"
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
			remount,rw) return 0 ;;
			"${CARD:-none}") : > "$m/.dp200-root"; mkdir -p "$m/etc/dp200" "$m/run"
				[ "${CARDREV:-}" ] && : > "$m/.dp200-revert"
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
	ubidetach() { log "ubidetach $*"; : > "$T/detached"; }
	dp200_hold() { [ "${TOUCH:-no}" = yes ]; }
	rm() { case "$*" in *.dp200-revert) log "MARKER REMOVED" ;; esac; command rm "$@"; }
	isdev() { case $1 in "${CARD:-none}"|"${STICKDEV:-none}") return 0 ;; esac; return 1; }
	dp200_revert() { log "REVERT window=$(cat "$T/win")"; return ${REVRC:-0}; }
	reboot() { log "reboot $*"; exit 0; }
	setsid() { log "SHELL"; }
	switch_root() { [ -e "$T/detached" ] && det=detached || det=attached
		log "switch_root $* (root $(cat "$T/mounted")) window=$(cat "$T/win") ubi0 $det"; exit 0; }
	cp() { :; }
	. "$T/init"
	) > /dev/null 2>&1
	got=$(grep -E "MARKER|REVERT|switch_root|SHELL|reboot|STOPPED" "$T/out" | sed "s#$T##g" | tr '\n' ' ')
	# every say() line also goes to the kernel log
	grep -q "^dp200-init: " "$T/kmsg" || got="$got (nothing in kmsg)"
	case "$got" in "$want"*) r=ok ;; *) r=FAIL ;; esac
	case "$got" in *"nothing in kmsg"*) r=FAIL ;; esac
	[ $r = ok ] || FAILS=$((FAILS + 1))
	printf '%-36s %-4s %s\n' "$name" "$r" "$got"
}

# the "printer's" devices: a card partition and a stick
SD=/dev/mmcblk0p1 STK=/dev/sda1
FAILS=0
# want: the start of the outcome line
# mtd6 root: attached, its window stays open; a card root: mtd6 closed
want="switch_root /newroot /etc/dp200/init.mainline (root ubi0:filesystem) window=1741,4091 ubi0 attached"
run "mtd6 root" UBIROOT=ok
want="switch_root /newroot /etc/dp200/init.mainline (root /dev/mmcblk0p1) window=none ubi0 detached"
run "marked card first" UBIROOT=ok CARD="${SD:-x}"
run "marked card, mtd6 root broken" UBIROOT=broken CARD="${SD:-x}"
want="REVERT window=none reboot -f"
run "mtd6 root marker -> revert" UBIROOT=revert
want="MARKER REMOVED REVERT window=none reboot -f"
run "card root marker -> removed, revert" UBIROOT=ok CARD="${SD:-x}" CARDREV=1
# a healthy root never asks here, whatever is plugged in or touched
want="switch_root /newroot /etc/dp200/init.mainline (root ubi0:filesystem)"
run "Sindoh stick, held, healthy root" UBIROOT=ok STICKDEV="${STK:-x}" STICKFILE=update.she TOUCH=yes
run "revert stick, held, healthy root" UBIROOT=ok STICKDEV="${STK:-x}" STICKFILE=dp200-revert TOUCH=yes
want="REVERT window=none reboot -f"
run "broken root, held" UBIROOT=broken TOUCH=yes
run "broken root + Sindoh stick, held" UBIROOT=broken STICKDEV="${STK:-x}" STICKFILE=update.she TOUCH=yes
want="SHELL reboot -f"
run "broken root, not held" UBIROOT=broken TOUCH=no
want="REVERT window=none SHELL STOPPED"
run "revert fails" UBIROOT=revert REVRC=1
[ $FAILS = 0 ] && echo "decisions: all as expected" || echo "decisions: $FAILS FAILED"

# The built image's initramfs list (if there is one): every tool that
# dp200-revert.sh checks for and that the init calls is in it, and the
# UBI/NAND tools are mtd-utils binaries, not BusyBox links (other options).
L=${IRFS_LIST:-$HOME/dp200/initramfs-m1-nandboot/initramfs.list}
if [ -f "$L" ]; then
	bad=0
	for t in ubiattach ubidetach ubiformat ubimkvol ubiupdatevol flash_erase \
		 nandwrite bzip2 tar cmp od awk md5sum mountpoint switch_root \
		 tee setsid cttyhack dirname id basename dp200-hold dp200-revert.sh; do
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
