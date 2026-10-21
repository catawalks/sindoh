#!/bin/sh
# DP200 Klipper installer - run by the STOCK firmware from a USB stick.
#
# Stick layout (vfat):
#   _update_rodin/unmistakable_klipper_install.she   this script, packed by pack_she.sh
#   _update_rodin/dp200_klipper_payload.tar.gz       Debian runtime root (make_payload.sh)
#   _update_rodin/dp200_klipper_payload.tar.gz.md5
#   _update_rodin/target_sd        (optional, empty file: install to the microSD
#                                   card instead of the internal NAND)
#
# How it runs: mdev -> /usr/sbin/media.connect mounts the stick on /mnt/sda1
# and calls /app/auto_update.sh. That script decrypts every
# _update_rodin/unmistakable*.she into /tmp and runs it with the folder as $1
# (same mechanism as Sindoh's own tools and the Model 1 converter).
#
# Target NAND (default): mtd5 "recovery" (200 MB, not used by the stock boot)
# becomes a UBI volume "klipper" mounted on /klipper. Its old content is first
# saved to the stick (mtd5_recovery_backup.bin) so the remove stick can put it
# back. Target SD: the Debian root goes to /mnt/sd (ext2/3/4 card).
# Both: the stock kernel and root stay as they are, apart from the reversible
# boot hook (/etc/profile line, /etc/dp200-boot.sh, /DEBUG_MACHINE).
#
# Rehearsal: DRY_RUN=1 sh unmistakable_klipper_install.sh <dir>  (or a file
# "dry_run" in the stick folder) does every check and unpacks into
# $DRYDIR (default /mnt/sd/dryrun_root) - no flash erase, no hook, no reboot,
# no touchscreen.
STICK=${1:-/mnt/sda1/_update_rodin}
[ -f "$STICK/dry_run" ] && DRY_RUN=1
DRY_RUN=${DRY_RUN:-0}
[ $DRY_RUN = 1 ] || exec >/dev/console 2>&1
PAYLOAD=$STICK/dp200_klipper_payload.tar.gz
LOG=$STICK/dp200_klipper_install.log
TARGET=nand
[ -f "$STICK/target_sd" ] && TARGET=sd
MTD=5
UBI=2
NAND_MAX_GZ_MB=160          # mtd5 gives ~190 MB of UBIFS; gzip size ~ UBIFS zlib size

if [ $DRY_RUN = 1 ]; then
    ROOT=${DRYDIR:-/mnt/sd/dryrun_root}
    show() { echo "[klipper-install DRY] $1 $2 $3"; echo "$(date) DRY $1 $2 $3" >> $LOG; }
    keywait() { :; }
else
    [ $TARGET = nand ] && ROOT=/klipper || ROOT=/mnt/sd
    show() { /app/display.sh "Klipper install" "$1" "$2" "$3"; echo "[klipper-install] $1 $2 $3"; echo "$(date) $1 $2 $3" >> $LOG; }
    keywait() { /app/tinydebug keywait; }
fi
fail() {
    [ $DRY_RUN = 1 ] || /app/tinydebug led red
    show "FAILED: $1" "$2" "Touch to reboot"
    [ $DRY_RUN = 1 ] && exit 1
    keywait
    sync; reboot; exit 1
}
mb_free() { echo $(( `df -k "$1" | tail -1 | awk '{print $(NF-2)}'` / 1024 )); }

# Take over the screen the way Sindoh's tools do
if [ $DRY_RUN = 0 ]; then
    /app/tinydebug wdt disable
    kill -9 `pidof stdin2log` 2>/dev/null
    kill -9 `pidof appBrowser` 2>/dev/null
    /app/tinydebug wdt disable
fi
show "Klipper installer" "target: $TARGET" ""

# ---- checks (nothing is changed yet)
[ -f "$PAYLOAD" ] || fail "no payload" "dp200_klipper_payload"
[ -f /app/upc.ko ] || fail "not a DP200?" "/app/upc.ko missing"
GZ_MB=$(( `ls -l "$PAYLOAD" | awk '{print $5}'` / 1048576 ))
UPGRADE=0
if [ $TARGET = nand ]; then
    grep -q "^mtd$MTD: 0c800000 00020000 \"recovery\"" /proc/mtd || fail "unexpected NAND layout" "mtd$MTD is not recovery"
    [ $GZ_MB -le $NAND_MAX_GZ_MB ] || fail "payload too big" "$GZ_MB MB > $NAND_MAX_GZ_MB MB"
    # an existing Klipper volume? (upgrade). A dry run never attaches mtd5:
    # UBI may write to a partition it attaches (scrubbing, wear levelling).
    if [ -e /sys/class/ubi/ubi$UBI ] || { [ $DRY_RUN = 0 ] && ubiattach -m $MTD -d $UBI >/dev/null 2>&1; }; then
        grep -q '^klipper$' /sys/class/ubi/ubi$UBI/ubi${UBI}_*/name 2>/dev/null && UPGRADE=1
        [ $UPGRADE = 1 ] || [ $DRY_RUN = 1 ] || ubidetach -d $UBI 2>/dev/null
    fi
    if [ $UPGRADE = 0 ]; then
        STICK_FREE=$(mb_free "$STICK")
        [ "$STICK_FREE" -ge 210 ] || fail "USB stick too full" "need 210 MB for the NAND backup"
    fi
else
    grep -q " /mnt/sd " /proc/mounts || fail "no microSD card" "at /mnt/sd"
    FSTYPE=`grep " /mnt/sd " /proc/mounts | awk '{print $3}'`
    case "$FSTYPE" in ext2|ext3|ext4) ;; *) fail "SD card is $FSTYPE" "needs ext2/3/4" ;; esac
    [ -x /mnt/sd/etc/dp200/rc.dp200 ] && UPGRADE=1
    NEED_MB=$(( `cat "$PAYLOAD.size" 2>/dev/null || echo 3000000` / 1024 + 200 ))
    [ $UPGRADE = 1 ] || [ "$(mb_free /mnt/sd)" -ge $NEED_MB ] || fail "SD card too full" "need $NEED_MB MB"
fi
[ $DRY_RUN = 1 ] && { mkdir -p $ROOT; NEED_MB=$(( `cat "$PAYLOAD.size" 2>/dev/null || echo 0` / 1024 + 50 ));
    [ "$(mb_free $ROOT)" -ge $NEED_MB ] || fail "no room for the rehearsal" "need $NEED_MB MB in $ROOT"; }

show "Checking payload" "(md5, ~1 min)" "DO NOT POWER OFF"
if [ -f "$PAYLOAD.md5" ]; then
    WANT=`awk '{print $1}' "$PAYLOAD.md5"`
    HAVE=`md5sum "$PAYLOAD" | awk '{print $1}'`
    [ "$WANT" = "$HAVE" ] || fail "payload damaged" "md5 mismatch"
fi

# ---- confirm on the touchscreen
if [ $UPGRADE = 1 ]; then
    show "Klipper found ($TARGET)" "Touch to UPGRADE" "(config is kept)"
else
    show "Touch to INSTALL" "Klipper ($TARGET)" "Power off to cancel"
fi
keywait

# ---- stop a running Klipper stack and unmount its chroot
if [ $DRY_RUN = 0 ]; then
    for r in /klipper /mnt/sd; do
        [ -x $r/dp200/dp200-start.sh ] && $r/dp200/dp200-start.sh stop
        for m in home/klipper/printer_data/logs var/log tmp run/wpa_supplicant run dev/shm dev/pts dev sys proc; do
            grep -q " $r/$m " /proc/mounts && umount $r/$m
        done
    done
fi

# ---- prepare the target
if [ $DRY_RUN = 0 ] && [ $TARGET = nand ] && [ $UPGRADE = 0 ]; then
    show "Saving NAND backup" "to the USB stick" "DO NOT POWER OFF"
    # -o no OOB, -b skip bad blocks: the exact stream "nandwrite -p" writes
    # back (it skips bad blocks the same way) - see the remove script
    nanddump -o -b -q -f "$STICK/mtd${MTD}_recovery_backup.bin" /dev/mtd$MTD || fail "NAND backup failed" "nothing changed"
    md5sum "$STICK/mtd${MTD}_recovery_backup.bin" > "$STICK/mtd${MTD}_recovery_backup.bin.md5"
    sync
    show "Formatting NAND" "(recovery area)" "DO NOT POWER OFF"
    ubidetach -d $UBI 2>/dev/null
    ubiformat /dev/mtd$MTD -y || fail "ubiformat failed" "see install log"
    ubiattach -m $MTD -d $UBI || fail "ubiattach failed" "see install log"
    [ -e /dev/ubi$UBI ] || mknod /dev/ubi$UBI c `tr : ' ' < /sys/class/ubi/ubi$UBI/dev`
    ubimkvol /dev/ubi$UBI -N klipper -m || fail "ubimkvol failed" "see install log"
fi
if [ $DRY_RUN = 0 ] && [ $TARGET = nand ]; then
    mkdir -p /klipper
    grep -q " /klipper " /proc/mounts || mount -t ubifs -o compr=zlib ubi$UBI:klipper /klipper \
        || fail "mount failed" "ubi$UBI:klipper"
fi

# keep the user's printer config across an upgrade
CFG=$ROOT/home/klipper/printer_data/config
rm -rf /tmp/klipper_cfg_keep /tmp/klipper_cfg_new
[ -d $CFG ] && cp -a $CFG /tmp/klipper_cfg_keep

show "Installing..." "(5-20 minutes)" "DO NOT POWER OFF"
tar -xzf "$PAYLOAD" -C $ROOT || fail "unpack failed" "see install log"
mkdir -p $ROOT/proc $ROOT/sys $ROOT/dev $ROOT/tmp $ROOT/run
chmod 1777 $ROOT/tmp
if [ -d /tmp/klipper_cfg_keep ]; then
    # keep the user's printer.cfg (calibration, SAVE_CONFIG data) and other
    # files, but take dp200_*.cfg (port-owned) from the new payload
    mkdir -p /tmp/klipper_cfg_new
    cp -a $CFG/dp200_*.cfg /tmp/klipper_cfg_new/ 2>/dev/null
    cp -a /tmp/klipper_cfg_keep/. $CFG/
    cp -a /tmp/klipper_cfg_new/. $CFG/
fi
sync

# ---- verify the unpacked root
for f in etc/dp200/rc.dp200 dp200/dp200-start.sh dp200/dp200-boot.sh dp200/hook_install.sh \
         usr/bin/python3 home/klipper/klippy-env/bin/python home/klipper/klipper/klippy/klippy.py \
         home/klipper/moonraker/moonraker/moonraker.py opt/dp200/fm.bin opt/dp200/io.bin \
         usr/local/bin/upctool home/klipper/printer_data/config/printer.cfg; do
    # -L: venv pythons are absolute symlinks, valid only inside the chroot
    [ -e $ROOT/$f ] || [ -L $ROOT/$f ] || fail "incomplete install" "missing /$f"
done
[ -n "`ls $ROOT/home/klipper/klipper/klippy/chelper/c_helper.so 2>/dev/null`" ] || fail "incomplete install" "no c_helper.so"
USED=`du -sk $ROOT | awk '{print int($1 / 1024)}'`
show "Unpacked OK" "$USED MB in $ROOT" ""

if [ $DRY_RUN = 1 ]; then
    show "DRY RUN complete" "nothing was flashed" "remove $ROOT when done"
    exit 0
fi

show "Installing boot hook" "" "DO NOT POWER OFF"
sh $ROOT/dp200/hook_install.sh || fail "hook failed" "see install log"
sync

/app/tinydebug led green 2>/dev/null
show "DONE - remove stick" "Web UI: http://<ip>/" "Touch to reboot"
keywait
sync
reboot
exit 0
