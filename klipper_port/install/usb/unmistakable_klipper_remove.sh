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
# tinydebug's lines take HTML: the title in color, "DO NOT POWER OFF" red
red() { case "$1" in "DO NOT POWER OFF") echo "<font color=\"#c00000\">$1</font>" ;; *) echo "$1" ;; esac; }
show() { /app/display.sh '<font color="#0040b0">== KLIPPER REMOVE ==</font>' "`red "$1"`" "`red "$2"`" "`red "$3"`"
         echo "[klipper-remove] $1 $2 $3"; }
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
    if [ -n "$SCREEN_ROOT" ]; then
        # feedback at once: the screen app takes several seconds to start
        show "Cancelled" "Starting the" "Klipper screen..."
        ( sleep 20; killall tinydebug ) >/dev/null 2>&1 &
        chroot $SCREEN_ROOT /usr/bin/env -i \
            PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin HOME=/root \
            /etc/dp200/rc.dp200 restart-screen
    else
        show "Cancelled" "nothing was changed" ""
    fi
    exit 1
}
# Only a real touch counts (keywait exits 0). Pulling the stick makes
# media.connect kill -9 every tinydebug, this keywait too: that cancels.
confirm() {
    while :; do
        /app/tinydebug keywait
        rc=$?
        sleep 1
        [ -f "$ME" ] || cancelled
        [ $rc = 0 ] && return 0
        show "$@"
    done
}

/app/tinydebug wdt disable
kill -9 `pidof stdin2log` 2>/dev/null
kill -9 `pidof appBrowser` 2>/dev/null
screen_off

# The Sindoh app (RESTORE): 1 = the installer's backup on this stick
# (md5-checked, this printer's exact copy); 2 = without it, the factory
# recovery set in mtd5 (Sindoh's own update.tar.bz2, ./app/SVN_GUI): the
# printer then always has a way back, even with the stick lost. That copy
# is the FACTORY version (2017); a printer updated since (2020 firmware)
# should then get Sindoh's update again for a matching app.
RESTORE=0
REC_MTD=5
REC_UBI=2
if [ ! -d $GUI ] && [ -f "$BACKUP/SVN_GUI.tar" ] && [ -f "$BACKUP/SVN_GUI.tar.md5" ]; then
    show "Checking the backup" "of the Sindoh app" "(md5)"
    [ "`cat "$BACKUP/SVN_GUI.tar.md5"`" = "`md5sum < "$BACKUP/SVN_GUI.tar"`" ] \
        && RESTORE=1 || show "Sindoh app backup" "is damaged" ""
fi
if [ ! -d $GUI ] && [ $RESTORE = 0 ] && \
   grep -q "^mtd$REC_MTD: 0c800000 00020000 \"recovery\"" /proc/mtd; then
    RESTORE=2
fi
if [ ! -d $GUI ] && [ $RESTORE = 0 ] && [ $OEM = 0 ]; then
    show "No Sindoh app backup" "on stick or NAND" "Pull stick to cancel"
    while [ -f "$ME" ]; do sleep 1; done
    cancelled
fi
if [ $RESTORE = 2 ]; then
    P2="(factory app, mtd5)"
else
    P2="the Sindoh firmware"
fi
show "Touch to restore" "$P2" "Pull stick to cancel"
confirm "Touch to restore" "$P2" "Pull stick to cancel"

for r in /klipper /mnt/sd; do
    [ -x $r/dp200/dp200-start.sh ] && $r/dp200/dp200-start.sh stop
    for m in home/klipper/printer_data/logs var/log tmp run/wpa_supplicant run dev/shm dev/pts dev sys proc; do
        grep -q " $r/$m " /proc/mounts && umount $r/$m
    done
done
# The app goes to RAM first (/tmp is tmpfs; the stack is stopped, so there
# is room): /klipper has to go before it fits on the NAND, and from here
# on nothing depends on the stick any more
unreadable() {
    rm -rf /tmp/dp200-restore
    show "$1 unreadable" "nothing changed" "Pull stick to reboot"
    /app/tinydebug keywait
    reboot; exit 1
}
rm -rf /tmp/dp200-restore; mkdir -p /tmp/dp200-restore
if [ $RESTORE = 1 ]; then
    show "Reading the backup" "of the Sindoh app" "DO NOT POWER OFF"
    tar -xf "$BACKUP/SVN_GUI.tar" -C /tmp/dp200-restore || unreadable "Backup"
elif [ $RESTORE = 2 ]; then
    # UBI attach as Sindoh's own recovery does; the volume is mounted
    # read-only and only read (UBI itself may still move a block it finds
    # bit errors in: normal housekeeping)
    show "Reading recovery set" "(about 5-10 min)" "DO NOT POWER OFF"
    ATTACHED=0
    if [ ! -e /sys/class/ubi/ubi$REC_UBI ]; then
        ubiattach /dev/ubi_ctrl -m $REC_MTD -d $REC_UBI >/dev/null 2>&1 || unreadable "Recovery set"
        ATTACHED=1
    fi
    mkdir -p /tmp/dp200-rec
    if mount -t ubifs -o ro ubi$REC_UBI:recovery /tmp/dp200-rec; then
        tar -xjf /tmp/dp200-rec/update.tar.bz2 -C /tmp/dp200-restore ./app/SVN_GUI
        umount /tmp/dp200-rec
    fi
    [ $ATTACHED = 1 ] && ubidetach /dev/ubi_ctrl -d $REC_UBI
    [ -f /tmp/dp200-restore/app/SVN_GUI/home.html ] || unreadable "Recovery set"
    mv /tmp/dp200-restore/app/SVN_GUI /tmp/dp200-restore/SVN_GUI
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
if [ $RESTORE != 0 ]; then
    show "Restoring" "the Sindoh app" "DO NOT POWER OFF"
    if cp -a /tmp/dp200-restore/SVN_GUI /app/; then
        show "Sindoh app restored" "Saving, please wait" "DO NOT POWER OFF"
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
if [ $RESTORE = 2 ]; then
    # the factory app next to newer firmware: say how to match them
    show "Factory app back" "Sindoh update for" "latest. Pull stick"
else
    show "Stock firmware back" "" "Pull stick to reboot"
fi
sync
/app/tinydebug keywait
reboot
exit 0
