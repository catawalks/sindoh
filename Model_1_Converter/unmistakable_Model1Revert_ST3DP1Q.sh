#!/bin/sh
# Undo unmistakable_Model1Fix: set a Stanley Model 1 that was converted to a
# DP200Q back to its Stanley model ID (TLI).
#
# Model1Fix changes only the printer's model ID, from ST3DP1 or ST3DP1Q to
# 3DP200Q (one row in /app/nvram/karas.db). The original ID is not kept
# anywhere. THIS VARIANT sets ST3DP1Q: the stock ST3DP1 with the Q that
# Sindoh's open-filament script appends (keeps open-filament mode).
# unmistakable_Model1Revert.she (same script) sets the stock ST3DP1.
#
# Safety:
#   - only acts when the current ID is 3DP200Q; anything else is left alone
#   - a genuine Sindoh DP200Q also has 3DP200Q: the screen says this script is
#     only for converted Stanley printers
#   - only a real touch confirms; pulling the USB stick cancels
#
# What it changes: it runs Sindoh's own karas_pinetree_util.sh --set-tli,
# the same command Model1Fix ran, so everything Model1Fix changed goes back:
# the model ID, the time zone (US), vendor and user ID (STANLEY, MODEL 1),
# the boot logo (mtd3, /app/boot-logo_stanley.bin) and its boot-bar color
# (U-Boot env: bar_color 1, boot_time 17, lcd_type 1), the homepage file
# and the /backup copy of karas.db.
#
# Run by the stock /app/auto_update.sh from _update_rodin/ on a USB stick.
exec >/dev/console 2>&1
NEW_TLI=ST3DP1Q
FROM_TLI=3DP200Q
DB=${DB:-/app/nvram/karas.db}
UTIL=${UTIL:-/app/karas_pinetree_util.sh}   # (DB=, UTIL=, NO_REBOOT=1: testing)
STICK=${1:-/mnt/sda1/_update_rodin}
ME=$STICK/unmistakable_Model1Revert.she
[ -f "$ME" ] || ME=`ls "$STICK"/unmistakable_Model1Revert*.she 2>/dev/null | head -1`

show() { /app/display.sh '<font color="#0040b0">== MODEL 1 REVERT ==</font>' "$1" "$2" "$3"; echo "[model1-revert] $1 $2 $3"; }
# Only a real touch counts (keywait exits 0). Removing the stick makes
# Sindoh's media.connect kill -9 every tinydebug, this keywait too.
confirm() {
    while :; do
        /app/tinydebug keywait
        rc=$?
        sleep 1
        [ -f "$ME" ] || { echo "[model1-revert] stick removed: cancelled"; exit 1; }
        [ $rc = 0 ] && return 0
        show "$@"
    done
}

/app/tinydebug wdt disable
kill -9 `pidof stdin2log` 2>/dev/null
kill -9 `pidof appBrowser` 2>/dev/null
/app/tinydebug wdt disable

TLI=`sqlite3 $DB "select MachineTLI from INST_MACHINE"`
if [ "$TLI" != "$FROM_TLI" ]; then
    show "Model ID: $TLI" "not $FROM_TLI: skip" "Pull stick to exit"
    while [ -f "$ME" ]; do sleep 1; done
    [ -n "$NO_REBOOT" ] || $UTIL --reboot
    exit 0
fi
show "Model ID: $TLI" "Touch to continue" "Pull stick to cancel"
confirm "Model ID: $TLI" "Touch to continue" "Pull stick to cancel"
show "Only for a Stanley" "that Model1Fix made" "Touch: set $NEW_TLI"
confirm "Only for a Stanley" "that Model1Fix made" "Touch: set $NEW_TLI"

show "Setting $NEW_TLI" "logo and settings" "DO NOT POWER OFF"
$UTIL --set-tli $NEW_TLI
sync
TLI=`sqlite3 $DB "select MachineTLI from INST_MACHINE"`
if [ "$TLI" = "$NEW_TLI" ]; then
    show "Model ID set:" "$TLI" "Pull stick to reboot"
else
    show "Model ID NOT changed" "($TLI)" "Pull stick to reboot"
fi
# pulling the stick ends the wait too
/app/tinydebug keywait
[ -n "$NO_REBOOT" ] || $UTIL --reboot
exit 0
