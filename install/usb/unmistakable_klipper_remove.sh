#!/bin/sh
# DP200 Klipper uninstaller - run by the stock /app/auto_update.sh from a USB
# stick (_update_rodin/unmistakable_klipper_remove.she, packed by pack_she.sh).
# Restores the stock boot (removes the /etc/profile hook, /etc/dp200-boot.sh
# and /DEBUG_MACHINE).
#
# NAND installs: if the stick also holds mtd5_recovery_backup.bin (+ .md5),
# saved by the installer, the "recovery" partition gets its factory content
# back (otherwise the Klipper volume just stays there, unused by the stock boot).
# SD installs: the Debian root on the card stays (reinstall = hook only).
#
# Full revert to OEM in one stick: put this .she next to Sindoh's OEM update
# files (_update_rodin/update.she, image.*). auto_update.sh runs every
# unmistakable*.she BEFORE update.she, so this script removes the hook and
# then returns (no reboot) to let the OEM update flash the stock firmware.
exec >/dev/console 2>&1
STICK=${1:-/mnt/sda1/_update_rodin}
MTD=5
UBI=2
BACKUP=$STICK/mtd${MTD}_recovery_backup.bin
OEM=0
[ -f "$STICK/update.she" ] && OEM=1
show() { /app/display.sh "Klipper remove" "$1" "$2" "$3"; echo "[klipper-remove] $1 $2 $3"; }

/app/tinydebug wdt disable
kill -9 `pidof stdin2log` 2>/dev/null
kill -9 `pidof appBrowser` 2>/dev/null

RESTORE=0
if [ -f "$BACKUP" ] && [ -f "$BACKUP.md5" ]; then
    show "Checking NAND backup" "(md5)" ""
    [ "`awk '{print $1}' "$BACKUP.md5"`" = "`md5sum "$BACKUP" | awk '{print $1}'`" ] && RESTORE=1 \
        || show "NAND backup damaged" "it will NOT be used" ""
fi
if [ $RESTORE = 1 ]; then
    show "Touch to restore" "Sindoh firmware" "+ NAND recovery area"
else
    show "Touch to restore" "the Sindoh firmware" "Power off to cancel"
fi
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
rm -f /DEBUG_MACHINE /etc/dp200-boot.sh
sync

if [ $RESTORE = 1 ]; then
    show "Restoring NAND" "recovery area" "DO NOT POWER OFF"
    grep -q " /klipper " /proc/mounts && umount /klipper
    [ -e /sys/class/ubi/ubi$UBI ] && ubidetach -d $UBI
    if flash_erase /dev/mtd$MTD 0 0 && nandwrite -p -q /dev/mtd$MTD "$BACKUP"; then
        show "NAND restored" "" ""
    else
        show "NAND restore FAILED" "stock boot is OK" "(area unused by it)"
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
show "Stock boot restored" "Remove the stick" "Touch to reboot"
/app/tinydebug keywait
reboot
exit 0
