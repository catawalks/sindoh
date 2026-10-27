#!/bin/sh
# Custom boot logo for Sindoh DP200 / 3DWOX printers - run by the stock
# /app/auto_update.sh from a USB stick (_update_rodin/unmistakable_bootlogo.she,
# made by sindoh_bootlogo.py). The .she also holds bootlogo_new.bin, which
# auto_update.sh extracts next to this script in /tmp.
#
# 1. finds the "boot-logo" flash partition in /proc/mtd and checks the image
#    fits it;
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
exec >/dev/console 2>&1
STICK=${1:-/mnt/sda1/_update_rodin}
DIR=$(dirname "$0")
NEW=$DIR/bootlogo_new.bin
show() {
    [ -x /app/display.sh ] && /app/display.sh "Boot logo" "$1" "$2" "$3"
    echo "[bootlogo] $1 $2 $3"
}
fail() { show "$1" "$2" "Logo NOT changed"; sleep 5; exit 1; }
DRY=0
[ -f "$STICK/dry_run" ] && DRY=1

# the partition, by name (not by number, in case another model differs)
MTD=$(grep '"boot-logo"' /proc/mtd | cut -d: -f1)
[ -n "$MTD" ] || fail "No boot-logo" "partition found"
PART_SIZE=$((0x$(grep '"boot-logo"' /proc/mtd | awk '{print $2}')))
[ "$PART_SIZE" -ge "$SIZE" ] || fail "Image too big" "for this printer"
[ "$(stat -c %s "$NEW")" = "$SIZE" ] || fail "Image damaged" "(size)"
[ "$(md5sum "$NEW" | awk '{print $1}')" = "$MD5" ] || fail "Image damaged" "(md5)"

CUR=/tmp/bootlogo_cur.bin
dd if=/dev/$MTD of=$CUR bs=$SIZE count=1 2>/dev/null
if cmp -s $CUR "$NEW"; then
    show "This logo is" "already installed" "Remove the stick"
    rm -f $CUR "$NEW"
    exit 0
fi
if [ $DRY = 1 ]; then
    show "Dry run: checks OK" "/dev/$MTD, bar $BAR_COLOR" "nothing written"
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
if command -v flash_eraseall >/dev/null; then
    flash_eraseall /dev/$MTD
else
    flash_erase /dev/$MTD 0 0
fi || fail "Erase failed" ""
nandwrite -p /dev/$MTD "$NEW" || fail "Write failed" "power off, retry"
sync
dd if=/dev/$MTD of=$CUR bs=$SIZE count=1 2>/dev/null
cmp -s $CUR "$NEW" || fail "Check failed" "power off, retry"
rm -f $CUR "$NEW"

if [ "$BAR_COLOR" != "keep" ] && command -v fw_printenv >/dev/null; then
    [ "$(fw_printenv -n bar_color 2>/dev/null)" = "$BAR_COLOR" ] || fw_setenv bar_color $BAR_COLOR
fi
show "Boot logo updated" "Remove the stick" "Shown at next boot"
sleep 3
exit 0
