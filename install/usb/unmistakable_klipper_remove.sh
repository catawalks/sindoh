#!/bin/sh
# DP200 Klipper uninstaller - run by the stock /app/auto_update.sh from a USB
# stick (_update_rodin/unmistakable_klipper_remove.she, packed by
# pack_she.sh). On the install stick it ships as _update_rodin_KlipperRemove/:
# rename the install folder back, then this one to _update_rodin.
#
# Restores the stock boot (removes the /etc/profile hook, /etc/dp200-boot.sh
# and /DEBUG_MACHINE). NAND installs (/klipper on the stock root): deletes
# /klipper and puts the Sindoh front end /app/SVN_GUI back from the backup
# the installer saved on the stick (dp200_stock_backup/SVN_GUI.tar).
# Without that backup it refuses to delete anything: Sindoh's OEM update (or
# the recovery set in mtd5) restores the app instead.
# SD installs: the Debian root on the card stays (reinstall = hook only).
#
# Full revert to OEM in one stick: put this .she next to Sindoh's OEM update
# files (_update_rodin/update.she, image.*). auto_update.sh runs every
# unmistakable*.she BEFORE update.she, so this script removes the hook and
# then returns (no reboot) to let the OEM update flash the stock firmware.
exec >/dev/console 2>&1
STICK=${1:-/mnt/sda1/_update_rodin}
BACKUP=$STICK/../dp200_stock_backup
GUI=/app/SVN_GUI
OEM=0
[ -f "$STICK/update.she" ] && OEM=1
show() { /app/display.sh "Klipper remove" "$1" "$2" "$3"; echo "[klipper-remove] $1 $2 $3"; }

/app/tinydebug wdt disable
kill -9 `pidof stdin2log` 2>/dev/null
kill -9 `pidof appBrowser` 2>/dev/null

# The Sindoh app: from the stick's backup, checked against its md5
RESTORE=0
if [ ! -d $GUI ] && [ -f "$BACKUP/SVN_GUI.tar" ] && [ -f "$BACKUP/SVN_GUI.tar.md5" ]; then
    show "Checking the backup" "of the Sindoh app" "(md5)"
    [ "`cat "$BACKUP/SVN_GUI.tar.md5"`" = "`md5sum < "$BACKUP/SVN_GUI.tar"`" ] \
        && RESTORE=1 || show "Sindoh app backup" "is damaged" ""
fi
if [ ! -d $GUI ] && [ $RESTORE = 0 ] && [ $OEM = 0 ]; then
    show "No Sindoh app backup" "on this stick" "Touch to reboot"
    /app/tinydebug keywait
    reboot; exit 1
fi
show "Touch to restore" "the Sindoh firmware" "Power off to cancel"
/app/tinydebug keywait

for r in /klipper /mnt/sd; do
    [ -x $r/dp200/dp200-start.sh ] && $r/dp200/dp200-start.sh stop
    for m in home/klipper/printer_data/logs var/log tmp run/wpa_supplicant run dev/shm dev/pts dev sys proc; do
        grep -q " $r/$m " /proc/mounts && umount $r/$m
    done
done
if [ -f /etc/profile.stock ]; then
    cp /etc/profile.stock /etc/profile
else
    sed -i '/# dp200-klipper hook/d' /etc/profile
fi
rm -f /DEBUG_MACHINE /etc/dp200-boot.sh /etc/dp200-nand
sync

if [ -d /klipper ] && ! grep -q " /klipper " /proc/mounts; then
    show "Removing Klipper" "from the NAND" "DO NOT POWER OFF"
    rm -rf /klipper
    sync
fi
if [ $RESTORE = 1 ]; then
    show "Restoring" "the Sindoh app" "DO NOT POWER OFF"
    if tar -xf "$BACKUP/SVN_GUI.tar" -C /app; then
        show "Sindoh app restored" "" ""
    else
        show "Restore FAILED" "use Sindoh's update" "to repair the app"
        sleep 5
    fi
    sync
fi

if [ $OEM = 1 ]; then
    # hand over to the OEM update.she on the same stick (it shows its own
    # screens and asks for a touch before flashing)
    show "Klipper hook removed" "Starting the OEM" "firmware update..."
    sleep 3
    exit 0
fi
show "Stock firmware restored" "Remove the stick" "Touch to reboot"
/app/tinydebug keywait
reboot
exit 0
