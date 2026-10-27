#!/bin/sh
# Custom boot logo for Sindoh DP200 / 3DWOX printers - run by the stock
# /app/auto_update.sh from a USB stick (<model folder>/unmistakable_bootlogo.she,
# made by sindoh_bootlogo.py). The .she also holds bootlogo_new.bin, which
# auto_update.sh extracts next to this script in /tmp.
#
# Where the logo lives (TARGET):
#   mtd   the NAND partition "boot-logo" (DP200, 3DWOX 1, 2X Prime_r1)
#   file  /boot/bootlogo.bin on the eMMC, loaded by U-Boot (1X, 7X, 2X Prime_r2)
#   auto  the 2X: file on Prime_r2 boards, mtd otherwise
#
# 1. finds the logo and checks the new image;
# 2. saves the current logo to the stick once (bootlogo_original.bin): put
#    that file through sindoh_bootlogo.py again to go back;
# 3. asks for a touch, writes the logo, reads it back to check it;
# 4. sets the boot progress bar colour (U-Boot variable bar_color).
#
# Rehearsal: an empty file "dry_run" next to the .she runs every check but
# writes nothing (no backup, no flash, no U-Boot variable).
#
# Settings below are filled in by sindoh_bootlogo.py.
SIZE=@SIZE@
MD5=@MD5@
BAR_COLOR=@BAR_COLOR@
TARGET=@TARGET@
exec >/dev/console 2>&1
STICK=${1:-/mnt/sda1/_update_rodin}
DIR=$(dirname "$0")
NEW=$DIR/bootlogo_new.bin
LOGO_FILE=/boot/bootlogo.bin
show() {
    [ -x /app/display.sh ] && /app/display.sh "Boot logo" "$1" "$2" "$3"
    echo "[bootlogo] $1 $2 $3"
}
fail() { show "$1" "$2" "Logo NOT changed"; sleep 5; exit 1; }
DRY=0
[ -f "$STICK/dry_run" ] && DRY=1

if [ "$TARGET" = auto ]; then
    BOARD=$(cat /sys/kernel/board_name 2>/dev/null)
    case "$BOARD" in
        ""|Prime_r1) TARGET=mtd ;;
        *) TARGET=file ;;
    esac
fi

[ "$(stat -c %s "$NEW")" = "$SIZE" ] || fail "Image damaged" "(size)"
[ "$(md5sum "$NEW" | awk '{print $1}')" = "$MD5" ] || fail "Image damaged" "(md5)"
CUR=/tmp/bootlogo_cur.bin
if [ "$TARGET" = mtd ]; then
    # the partition, by name (not by number, in case another model differs)
    MTD=$(grep '"boot-logo"' /proc/mtd | cut -d: -f1)
    [ -n "$MTD" ] || fail "No boot-logo" "partition found"
    PART_SIZE=$((0x$(grep '"boot-logo"' /proc/mtd | awk '{print $2}')))
    [ "$PART_SIZE" -ge "$SIZE" ] || fail "Image too big" "for this printer"
    dd if=/dev/$MTD of=$CUR bs=$SIZE count=1 2>/dev/null
    WHERE=/dev/$MTD
else
    [ -e $LOGO_FILE ] || fail "No $LOGO_FILE" "on this printer"
    # may be a symlink to a stock logo: read through it, never write through it
    cat $LOGO_FILE > $CUR || fail "Can't read" "$LOGO_FILE"
    WHERE=$LOGO_FILE
fi
if cmp -s $CUR "$NEW"; then
    show "This logo is" "already installed" "Remove the stick"
    rm -f $CUR "$NEW"
    exit 0
fi
if [ $DRY = 1 ]; then
    show "Dry run: checks OK" "$WHERE, bar $BAR_COLOR" "nothing written"
    rm -f $CUR "$NEW"
    exit 0
fi
# keep the first logo ever replaced (normally the factory one)
if [ ! -f "$STICK/bootlogo_original.bin" ]; then
    cp $CUR "$STICK/bootlogo_original.bin" && sync
fi

if [ -x /app/tinydebug ]; then
    show "Touch to install" "the new boot logo" "Power off to cancel"
    /app/tinydebug keywait
fi
show "Writing logo" "DO NOT POWER OFF" ""
if [ "$TARGET" = mtd ]; then
    if command -v flash_eraseall >/dev/null; then
        flash_eraseall /dev/$MTD
    else
        flash_erase /dev/$MTD 0 0
    fi || fail "Erase failed" ""
    nandwrite -p /dev/$MTD "$NEW" || fail "Write failed" "power off, retry"
    sync
    dd if=/dev/$MTD of=$CUR bs=$SIZE count=1 2>/dev/null
else
    RO=0
    if ! touch /boot/.bootlogo_rw 2>/dev/null; then
        RO=1
        mount -o remount,rw / || fail "Can't write" "/boot"
    fi
    rm -f /boot/.bootlogo_rw
    # new file next to it, then rename: replaces a symlink, not its target
    cp "$NEW" $LOGO_FILE.new && sync || fail "Write failed" "(copy)"
    mv -f $LOGO_FILE.new $LOGO_FILE && sync || fail "Write failed" "(rename)"
    cat $LOGO_FILE > $CUR
    [ $RO = 1 ] && mount -o remount,ro /
fi
cmp -s $CUR "$NEW" || fail "Check failed" "power off, retry"
rm -f $CUR "$NEW"

if [ "$BAR_COLOR" != "keep" ] && command -v fw_printenv >/dev/null; then
    [ "$(fw_printenv -n bar_color 2>/dev/null)" = "$BAR_COLOR" ] || fw_setenv bar_color $BAR_COLOR
fi
show "Boot logo updated" "Remove the stick" "Shown at next boot"
sleep 3
exit 0
