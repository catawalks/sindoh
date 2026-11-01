#!/bin/sh
# Kernel-log watch for every printer test (2026-11-01: a stock UBI write
# error switched the root read-only and went unnoticed for a while).
# Runs on stock (busybox) and mainline (Debian); copy to the printer.
#   klog.sh mark     remember the current end of the kernel log
#   klog.sh check    new alarming lines since the mark, and the root's
#                    mount state; ends with "KLOG OK" or "KLOG ALERT <n>"
# Known boot noise is ignored: the SD probes (EXT3-fs/EXT2-fs unsupported
# features), the stock Wi-Fi driver's CMD_RESP/ADDBA/ASSOC/IOCTL messages
# and UBI's bad-PEB counters. Mainline: the GPIO driver's "(read-only)"
# notes, regulatory.db, the rdinit probe, the 8782's CMD_RESP 0x2xx, and
# "Block protection check failed" (nand_macronix's read-only GET_FEATURES
# probe, unsupported here: block locking stays unused, as on stock).
M=/tmp/klog.mark
case $1 in
mark)
	dmesg | wc -l > $M
	echo "KLOG mark $(cat $M)"
	;;
check)
	from=$(( $(cat $M 2>/dev/null || echo 0) + 1 ))
	alerts=$(dmesg | tail -n +$from |
		grep -i 'error\|fail\|ro_mode\|read-only\|BCH read\|timed out\|refused\|corrupt\|scrub\|tortur\|oops\|bug:\|warning\|call trace\|uncorr\|-EIO\|mark.*bad' |
		grep -v 'EXT[23]-fs (mmcblk0p1): error: couldn.t mount because of unsupported optional features' |
		grep -v 'CMD_RESP: cmd 0x5b error' |
		grep -v 'ADDBA RSP: Failed\|ASSOC_RESP: Association Failed\|IOCTL failed: .* id=0x20000' |
		grep -v 'gpio: 32 lines (read-only)\|regulatory.db\|check access for rdinit=/nonexistent\|CMD_RESP: cmd 0x2[0-9a-f]* error' |
		grep -v 'Block protection check failed' |
		grep -v 'number of bad PEBs\|reserved for bad PEB\|number of corrupted PEBs: *0$')
	n=0
	[ -n "$alerts" ] && n=$(echo "$alerts" | wc -l)
	root=$(grep ' / ' /proc/mounts | grep -v rootfs | sed 's/ 0 0$//')
	case "$root" in
	*ubifs\ ro,*) n=$((n + 1)); alerts="$alerts
root mounted read-only: $root" ;;
	esac
	[ -n "$alerts" ] && echo "$alerts" | sed 's/^/KLOG: /'
	if [ $n -eq 0 ]; then echo "KLOG OK"; else echo "KLOG ALERT $n"; fi
	;;
*)
	echo "usage: $0 mark|check"
	exit 2
	;;
esac
