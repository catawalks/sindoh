#!/bin/sh
# Back to stock from our kernel (docs/kernel/revert_to_stock_plan.md):
# Sindoh's recovery sequence with the DP200 (rodin) file names, from the
# factory recovery set in mtd5. Runs as root on the mainline kernel with the
# guarded NAND write path (patch 0010); busybox sh + mtd-utils.
#
#   dp200-revert.sh [--dry-run] [--check] [--part root|kernel|logo|all] [--with-logo]
#
#   --check    only the read-only checks (recovery set, mtd0 U-Boot block)
#   --dry-run  checks, then print every erase/write instead of doing it
#   --part     one area only; "all" (default) = root, then the kernel last
#   --with-logo  "all" also writes the factory logo (default: logo kept)
#
# Never written: U-Boot (mtd0 blocks 0-1), mtd1 env, mtd2 bbt, mtd4 backup,
# mtd5 recovery. The driver refuses those anyway. The write window is open
# only around each write and closed on every exit.
set -u
WIN=/sys/module/marvell_nand/parameters/write_window
REC=/run/dp200-recovery
MNT=/run/dp200-newroot
MANIFEST=$(cd "$(dirname "$0")" && pwd)/recovery.md5
DRY=false CHECK=false PART=all LOGO=false
UBI_REC=12 UBI_ROOT=13	# ubi device numbers used here (stock uses 0-2)
KIMG=pa6170_rodin_nand.bin
LOGOIMG=boot-logo_rodin.bin
ROOTIMG=nandrootfs.ubifs
APPS=update.tar.bz2

while [ $# -gt 0 ]; do
	case $1 in
	--dry-run) DRY=true ;;
	--check) CHECK=true ;;
	--part) PART=$2; shift ;;
	--with-logo) LOGO=true ;;
	*) echo "unknown option $1"; exit 2 ;;
	esac
	shift
done
case $PART in root|kernel|logo|all) ;; *) echo "bad --part $PART"; exit 2 ;; esac

say() { echo "== $*"; }
fail() { echo "FAIL: $*"; exit 1; }
run() {
	if $DRY; then echo "   would run: $*"; else echo "   $*"; "$@"; fi
}
window() {
	if $DRY; then echo "   would set window $1"; return; fi
	echo "$1" > $WIN || fail "window $1"
	[ "$1" = none ] || echo "   window $(cat $WIN)"
}
cleanup() {
	[ -w $WIN ] && echo none > $WIN
	mountpoint -q $MNT 2>/dev/null && umount $MNT
	[ -e /dev/ubi$UBI_ROOT ] && ubidetach -d $UBI_ROOT 2>/dev/null
	mountpoint -q $REC 2>/dev/null && umount $REC
	[ -e /dev/ubi$UBI_REC ] && ubidetach -d $UBI_REC 2>/dev/null
}
trap cleanup EXIT
trap 'exit 1' INT TERM

mtdnum() {	# mtd number by name
	grep "\"$1\"" /proc/mtd | sed 's/^mtd\([0-9]*\):.*/\1/'
}
be32() {	# be32 at offset $2 of file/device $1
	dd if="$1" bs=1 skip="$2" count=4 2>/dev/null | od -An -tx1 | tr -d ' \n' |
		{ read h; echo $((0x$h)); }
}

# ---- checks (read-only) ----
say "checks"
[ "$(id -u)" = 0 ] || fail "run as root"
[ -e $WIN ] || fail "no write_window: not the guarded mainline kernel"
[ "$(cat $WIN)" = none ] || fail "write window not closed at start"
for t in ubiattach ubidetach ubiformat ubimkvol ubiupdatevol flash_erase nandwrite bzip2 tar cmp; do
	command -v $t >/dev/null || fail "$t missing (mtd-utils, bzip2)"
done
M0=$(mtdnum kernel) M3=$(mtdnum boot-logo) M5=$(mtdnum recovery) M6=$(mtdnum filesystem)
[ "$M0/$M3/$M5/$M6" = 0/3/5/6 ] || fail "unexpected MTD layout $M0/$M3/$M5/$M6"
grep -q "^mtd6: 12660000 00020000" /proc/mtd || fail "mtd6 size"
grep -q "^mtd0: 00800000 00020000" /proc/mtd || fail "mtd0 size"
[ "$(awk '$2 == "/" { t = $3 } END { print t }' /proc/mounts)" = ubifs ] &&
	fail "the root is on mtd6: run from RAM or SD"
grep -q "^ubi[0-9]*:filesystem \|^ubi[0-9]*_0 " /proc/mounts &&
	fail "a UBI root volume is mounted"

ubiattach -m $M5 -d $UBI_REC >/dev/null || fail "attach recovery (mtd5)"
mkdir -p $REC
mount -t ubifs -o ro ubi$UBI_REC:recovery $REC || fail "mount recovery"
echo "   recovery set:"
for f in $KIMG $LOGOIMG $ROOTIMG $APPS; do
	[ -f $REC/$f ] || fail "$f missing in mtd5"
	echo "     $(md5sum < $REC/$f | cut -c1-32)  $(wc -c < $REC/$f)  $f"
done
if [ -f "$MANIFEST" ]; then
	(cd $REC && md5sum -c "$MANIFEST" >/dev/null 2>&1) || fail "recovery set differs from $MANIFEST"
	echo "   matches $MANIFEST"
else
	echo "   (no $MANIFEST yet: sums printed only)"
fi
bzip2 -t $REC/$APPS 2>/dev/null || fail "$APPS damaged"
echo "   $APPS: bzip2 test OK"
# the U-Boot block on flash must be the one in the image: then it is never
# written and the kernel part alone is the whole difference
cmp -s -n 262144 /dev/mtd$M0 $REC/$KIMG || fail "mtd0 U-Boot block differs from $KIMG"
echo "   mtd0 U-Boot block = $KIMG's"
if cmp -s -n $(wc -c < $REC/$KIMG) /dev/mtd$M0 $REC/$KIMG; then
	echo "   mtd0 already holds the stock kernel"
fi
VID=$(be32 /dev/mtd$M6 16) DATA=$(be32 /dev/mtd$M6 20)
[ "$(dd if=/dev/mtd$M6 bs=4 count=1 2>/dev/null)" = "UBI#" ] || fail "mtd6 PEB 0 has no UBI EC header"
echo "   mtd6 UBI: VID header offset $VID, data offset $DATA"
[ "$VID" = 2048 ] || fail "unexpected VID header offset $VID"
NB=$(( $(cat /sys/class/mtd/mtd$M6/size) / 131072 ))
echo "   mtd6: $NB blocks, $(cat /sys/class/mtd/mtd$M6/bad_blocks) bad"
$CHECK && { say "checks done"; exit 0; }

# ---- writes ----
do_root() {
	say "root (mtd6): format, stock root, apps"
	window 1741,4091
	run ubiformat /dev/mtd$M6 -y -q -O $VID || fail "ubiformat"
	run ubiattach -m $M6 -d $UBI_ROOT || fail "attach mtd6"
	run ubimkvol /dev/ubi$UBI_ROOT -N filesystem -m || fail "ubimkvol"
	run ubiupdatevol /dev/ubi${UBI_ROOT}_0 $REC/$ROOTIMG || fail "ubiupdatevol"
	run mkdir -p $MNT
	run mount -t ubifs ubi$UBI_ROOT:filesystem $MNT || fail "mount new root"
	run tar xjf $REC/$APPS -C $MNT || fail "extract apps"
	run sync
	$DRY || [ -f $MNT/etc/profile ] || fail "new root has no /etc/profile"
	run umount $MNT
	run ubidetach -d $UBI_ROOT
	window none
}
do_logo() {
	say "logo (mtd3): factory logo"
	window 69,76
	run flash_erase -q /dev/mtd$M3 0 0 || fail "erase mtd3"
	run nandwrite -q -p /dev/mtd$M3 $REC/$LOGOIMG || fail "write mtd3"
	window none
	$DRY || cmp -s -n $(wc -c < $REC/$LOGOIMG) /dev/mtd$M3 $REC/$LOGOIMG || fail "mtd3 verify"
}
do_kernel() {
	say "kernel (mtd0 0x40000-0x7fffff): stock kernel; U-Boot block untouched"
	K=/run/dp200-kernel.bin
	dd if=$REC/$KIMG of=$K bs=131072 skip=2 2>/dev/null || fail "split image"
	window 2,63
	run flash_erase -q /dev/mtd$M0 0x40000 62 || fail "erase mtd0 kernel area"
	run nandwrite -q -p -s 0x40000 /dev/mtd$M0 $K || fail "write mtd0"
	window none
	$DRY || cmp -s -n $(wc -c < $REC/$KIMG) /dev/mtd$M0 $REC/$KIMG || fail "mtd0 verify"
	rm -f $K
}

case $PART in
root) do_root ;;
logo) do_logo ;;
kernel) do_kernel ;;
all) do_root; $LOGO && do_logo; do_kernel ;;
esac
say "done$($DRY && echo ' (dry run: nothing written)')"
