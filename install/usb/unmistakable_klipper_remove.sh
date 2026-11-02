#!/bin/sh
# DP200 Klipper uninstaller - run by the stock /app/auto_update.sh from a USB
# stick (_update_rodin/unmistakable_klipper_remove.she, packed by
# pack_she.sh). On the install stick it ships as _update_rodin_KlipperRemove/:
# rename the install folder back, then this one to _update_rodin.
#
# Restores the stock boot (removes the /etc/profile hook, /etc/dp200-boot.sh
# and /DEBUG_MACHINE). NAND installs (/klipper on the stock root): deletes
# /klipper and puts the Sindoh front end /app/SVN_GUI back from the backup
# the installer saved on the stick (dp200_stock_backup/<MAC>/SVN_GUI.tar).
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
# one backup per printer (one stick can serve several): named by the
# Ethernet MAC address, which U-Boot passes to every DP200 board
PRINTER_ID=`tr -d : < /sys/class/net/eth0/address 2>/dev/null`
BACKUP=$STICK/../dp200_stock_backup/${PRINTER_ID:-unknown}
GUI=/app/SVN_GUI
OEM=0
[ -f "$STICK/update.she" ] && OEM=1
show() { /app/display.sh "Klipper remove" "$1" "$2" "$3"; echo "[klipper-remove] $1 $2 $3"; }
ME=$STICK/unmistakable_klipper_remove.she     # gone = the stick was pulled

# The Klipper touch screen would keep reading touches under these
# messages: stop it, and start it again if the removal is cancelled
SCREEN_ROOT=
screen_off() {
    for r in /klipper /mnt/sd; do
        p=`cat $r/run/dp200/screen.pid 2>/dev/null`
        [ -n "$p" ] && kill -0 $p 2>/dev/null || continue
        kill $p
        SCREEN_ROOT=$r
    done
}
cancelled() {
    echo "[klipper-remove] stick removed: cancelled"
    killall tinydebug 2>/dev/null
    [ -n "$SCREEN_ROOT" ] && chroot $SCREEN_ROOT /usr/bin/env -i \
        PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
        /etc/dp200/rc.dp200 restart-screen
    exit 1
}
# Only a real touch counts (keywait exits 0). Pulling the stick makes
# media.connect kill -9 every tinydebug, this keywait too: that cancels.
confirm() {
    while :; do
        /app/tinydebug keywait
        rc=$?
        sleep 2
        [ -f "$ME" ] || cancelled
        [ $rc = 0 ] && return 0
        show "$@"
    done
}

/app/tinydebug wdt disable
kill -9 `pidof stdin2log` 2>/dev/null
kill -9 `pidof appBrowser` 2>/dev/null
screen_off

# The Sindoh app: from the stick's backup, checked against its md5
RESTORE=0
if [ ! -d $GUI ] && [ -f "$BACKUP/SVN_GUI.tar" ] && [ -f "$BACKUP/SVN_GUI.tar.md5" ]; then
    show "Checking the backup" "of the Sindoh app" "(md5)"
    [ "`cat "$BACKUP/SVN_GUI.tar.md5"`" = "`md5sum < "$BACKUP/SVN_GUI.tar"`" ] \
        && RESTORE=1 || show "Sindoh app backup" "is damaged" ""
fi
if [ ! -d $GUI ] && [ $RESTORE = 0 ] && [ $OEM = 0 ]; then
    show "No Sindoh app backup" "on this stick" "Pull stick to cancel"
    while [ -f "$ME" ]; do sleep 1; done
    cancelled
fi
show "Touch to restore" "the Sindoh firmware" "Pull stick to cancel"
confirm "Touch to restore" "the Sindoh firmware" "Pull stick to cancel"

for r in /klipper /mnt/sd; do
    [ -x $r/dp200/dp200-start.sh ] && $r/dp200/dp200-start.sh stop
    for m in home/klipper/printer_data/logs var/log tmp run/wpa_supplicant run dev/shm dev/pts dev sys proc; do
        grep -q " $r/$m " /proc/mounts && umount $r/$m
    done
done
# The app goes to RAM first (/tmp is tmpfs; the stack is stopped, so there
# is room): /klipper has to go before it fits on the NAND, and from here
# on nothing depends on the stick any more
if [ $RESTORE = 1 ]; then
    show "Reading the backup" "of the Sindoh app" "DO NOT POWER OFF"
    rm -rf /tmp/dp200-restore; mkdir -p /tmp/dp200-restore
    if ! tar -xf "$BACKUP/SVN_GUI.tar" -C /tmp/dp200-restore; then
        rm -rf /tmp/dp200-restore
        show "Backup unreadable" "nothing changed" "Pull stick to reboot"
        /app/tinydebug keywait
        reboot; exit 1
    fi
fi
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
    if cp -a /tmp/dp200-restore/SVN_GUI /app/; then
        show "Sindoh app restored" "" ""
    else
        show "Restore FAILED" "use Sindoh update" "to repair the app"
        sleep 5
    fi
    rm -rf /tmp/dp200-restore
    sync
fi

if [ $OEM = 1 ]; then
    # hand over to the OEM update.she on the same stick (it shows its own
    # screens and asks for a touch before flashing)
    show "Klipper hook removed" "Starting the OEM" "firmware update..."
    sleep 3
    exit 0
fi
show "Stock firmware back" "" "Pull stick to reboot"
sync
/app/tinydebug keywait
reboot
exit 0
