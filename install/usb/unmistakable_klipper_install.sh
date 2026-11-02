#!/bin/sh
# DP200 Klipper installer - run by the STOCK firmware from a USB stick.
#
# Stick layout (vfat):
#   _update_rodin/unmistakable_klipper_install.she   this script, packed by pack_she.sh
#   _update_rodin/dp200_klipper_payload.tar.gz       Debian runtime root (make_payload.sh)
#   _update_rodin/dp200_klipper_payload.tar.gz.md5
#   _update_rodin/dp200_klipper_payload.tar.gz.size  unpacked size in KiB
#   _update_rodin/target_sd        (optional, empty file: install to the microSD
#                                   card instead of the internal NAND)
#   _update_rodin_KlipperRemove/unmistakable_klipper_remove.she  the uninstaller:
#                                   rename this folder to _update_rodin to run it
#
# How it runs: mdev -> /usr/sbin/media.connect mounts the stick on /mnt/sda1
# and calls /app/auto_update.sh. That script decrypts every
# _update_rodin/unmistakable*.she into /tmp and runs it with the folder as $1
# (same mechanism as Sindoh's own tools and the Model 1 converter).
#
# Target NAND (default, 2026-11-02): the Debian root goes into /klipper, a
# directory on the stock root (mtd6, UBIFS), written through the stock
# kernel's own NAND driver. mtd0 (kernel), mtd5 (factory recovery set), the
# U-Boot blocks and the env are never touched. To make room, the Sindoh
# touch-screen front end /app/SVN_GUI (93 MB of HTML, images and fonts for
# its Qt browser; Klipper's screen replaces it) is first saved to the stick
# (dp200_stock_backup/SVN_GUI.tar, md5-checked) and then deleted. The rest of the stock system stays
# (auto_update.sh and its key, upc.ko, Wi-Fi, BusyBox). The remove stick puts
# SVN_GUI back. Target SD: the Debian root goes to /mnt/sd (ext2/3/4 card).
# Both: the boot hook (/etc/profile line, /etc/dp200-boot.sh, /DEBUG_MACHINE).
#
# Rehearsal: DRY_RUN=1 sh unmistakable_klipper_install.sh <dir>  (or a file
# "dry_run" in the stick folder) does every check and unpacks into
# $DRYDIR (default /mnt/sd/dryrun_root) - no NAND change, no hook, no
# reboot, no touchscreen.
STICK=${1:-/mnt/sda1/_update_rodin}
[ -f "$STICK/dry_run" ] && DRY_RUN=1
DRY_RUN=${DRY_RUN:-0}
[ $DRY_RUN = 1 ] || exec >/dev/console 2>&1
PAYLOAD=$STICK/dp200_klipper_payload.tar.gz
LOG=$STICK/dp200_klipper_install.log
BACKUP=$STICK/../dp200_stock_backup
GUI=/app/SVN_GUI
TARGET=nand
[ -f "$STICK/target_sd" ] && TARGET=sd
SPARE_MB=40                 # left free on the stock root after the install
                            # (G-code uploads, the stock side's own files)

if [ $DRY_RUN = 1 ]; then
    ROOT=${DRYDIR:-/mnt/sd/dryrun_root}
    show() { echo "[klipper-install DRY] $1 $2 $3"; echo "$(date) DRY $1 $2 $3" >> $LOG; }
    keywait() { :; }
else
    [ $TARGET = nand ] && ROOT=/klipper || ROOT=/mnt/sd
    show() { /app/display.sh "Klipper install" "$1" "$2" "$3"; echo "[klipper-install] $1 $2 $3"; echo "$(date) $1 $2 $3" >> $LOG; }
    keywait() { /app/tinydebug keywait; }
fi
# set once a NAND install starts changing the stock root: a failure then
# removes the partial /klipper and puts SVN_GUI back, so the stock firmware
# boots as before
UNDO=0
undo() {
    show "Undoing the install" "(stock firmware back)" "DO NOT POWER OFF"
    rm -rf /klipper
    if [ ! -d $GUI ] && [ -f "$BACKUP/SVN_GUI.tar" ]; then
        tar -xf "$BACKUP/SVN_GUI.tar" -C /app
    fi
    sync
}
fail() {
    [ $UNDO = 1 ] && undo
    [ $DRY_RUN = 1 ] || /app/tinydebug led red
    show "FAILED: $1" "$2" "Touch to reboot"
    [ $DRY_RUN = 1 ] && exit 1
    keywait
    sync; reboot; exit 1
}
mb_free() { echo $(( `df -k "$1" | tail -1 | awk '{print $(NF-2)}'` / 1024 )); }
size_mb() { echo $(( `ls -l "$1" | awk '{print $5}'` / 1048576 )); }
du_mb() { du -sk "$1" | awk '{print int($1 / 1024)}'; }

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
# DP200 or Stanley Model 1 alike; but upctool and cdc-acm.ko are built and
# tested for this kernel build (Sindoh's 2020 firmware, RODIN_200730_2)
KVER=3.2.0-g67a8e16
[ "`uname -r`" = $KVER ] || fail "firmware too old/new" "apply Sindoh 2020 update"
GZ_MB=$(size_mb "$PAYLOAD")
RAW_MB=$(( `cat "$PAYLOAD.size" 2>/dev/null || echo 3000000` / 1024 ))
UPGRADE=0
if [ $TARGET = nand ]; then
    # the stock layout, root on the UBIFS volume of mtd6
    grep -q '^mtd6: [0-9a-f]* 00020000 "filesystem"' /proc/mtd || fail "unexpected NAND layout" "mtd6 is not filesystem"
    grep -q '^ubi0:filesystem / ubifs ' /proc/mounts || fail "unexpected root" "not ubi0:filesystem"
    [ -x /klipper/etc/dp200/rc.dp200 ] && UPGRADE=1
    # Room: UBIFS zlib keeps ~ the gzip size (measured 2026-11-02); with a
    # margin of 1/4. An upgrade frees the old copy first.
    NEED_MB=$(( GZ_MB + GZ_MB / 4 + SPARE_MB ))
    HAVE_MB=$(mb_free /)
    # (du on UBIFS counts uncompressed sizes: SVN_GUI is mostly PNG and
    # fonts, which UBIFS stores nearly as is; the check after the unpack
    # catches a shortfall and undoes the install)
    [ $UPGRADE = 1 ] && HAVE_MB=$(( HAVE_MB + `du_mb /klipper` ))
    [ -d $GUI ] && HAVE_MB=$(( HAVE_MB + `du_mb $GUI` ))
    [ $HAVE_MB -ge $NEED_MB ] || fail "not enough NAND space" "need $NEED_MB MB, $HAVE_MB MB"
    if [ -d $GUI ] && [ ! -f "$BACKUP/SVN_GUI.tar" ]; then
        [ "$(mb_free "$STICK")" -ge $(( `du_mb $GUI` + 10 )) ] || fail "USB stick too full" "need 100 MB for the backup"
    fi
else
    grep -q " /mnt/sd " /proc/mounts || fail "no microSD card" "at /mnt/sd"
    FSTYPE=`grep " /mnt/sd " /proc/mounts | awk '{print $3}'`
    case "$FSTYPE" in ext2|ext3|ext4) ;; *) fail "SD card is $FSTYPE" "needs ext2/3/4" ;; esac
    [ -x /mnt/sd/etc/dp200/rc.dp200 ] && UPGRADE=1
    NEED_MB=$(( RAW_MB + 200 ))
    [ $UPGRADE = 1 ] || [ "$(mb_free /mnt/sd)" -ge $NEED_MB ] || fail "SD card too full" "need $NEED_MB MB"
fi
[ $DRY_RUN = 1 ] && { mkdir -p $ROOT; NEED_MB=$(( RAW_MB + 50 ));
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

# keep the user's printer config across an upgrade (RAM: /tmp is tmpfs)
CFG=$ROOT/home/klipper/printer_data/config
rm -rf /tmp/klipper_cfg_keep /tmp/klipper_cfg_new
[ -d $CFG ] && cp -a $CFG /tmp/klipper_cfg_keep

# ---- prepare the target
if [ $DRY_RUN = 0 ] && [ $TARGET = nand ]; then
    if [ -d $GUI ]; then
        if [ ! -f "$BACKUP/SVN_GUI.tar" ]; then
            show "Saving the Sindoh app" "to the USB stick" "DO NOT POWER OFF"
            mkdir -p "$BACKUP"
            # a tar keeps owners and modes (the stick is vfat); checked
            # against a fresh tar stream of the same directory
            tar -cf "$BACKUP/SVN_GUI.tmp" -C /app SVN_GUI && sync && \
                [ "`tar -cf - -C /app SVN_GUI | md5sum`" = "`md5sum < "$BACKUP/SVN_GUI.tmp"`" ] \
                || fail "backup failed" "nothing changed"
            mv "$BACKUP/SVN_GUI.tmp" "$BACKUP/SVN_GUI.tar"
            md5sum < "$BACKUP/SVN_GUI.tar" > "$BACKUP/SVN_GUI.tar.md5"
            sync
        fi
        UNDO=1
        rm -rf $GUI
    fi
    UNDO=1
    # an upgrade replaces the whole root (the config is kept above)
    rm -rf /klipper
    sync
    mkdir -p /klipper
    # New files on the root are compressed with zlib (UBIFS default here is
    # LZO: ~25% bigger). Only affects files written from now on; the option
    # is gone at the next boot, the stock files stay as they are.
    mount -o remount,compr=zlib / || echo "zlib remount refused: LZO"
fi

show "Installing..." "(5-20 minutes)" "DO NOT POWER OFF"
tar -xzf "$PAYLOAD" -C $ROOT || fail "unpack failed" "see install log"
mkdir -p $ROOT/proc $ROOT/sys $ROOT/dev $ROOT/tmp $ROOT/run
chmod 1777 $ROOT/tmp
if [ -d /tmp/klipper_cfg_keep ]; then
    # keep the user's printer.cfg (calibration, SAVE_CONFIG data) and other
    # files, but take dp200_*.cfg (port-owned) from the new payload
    mkdir -p /tmp/klipper_cfg_new
    # (dp200_*.cfg.off = port files shipped disabled, e.g. the accelerometer;
    # an enabled copy the user made stays as it was)
    cp -a $CFG/dp200_*.cfg $CFG/dp200_*.cfg.off /tmp/klipper_cfg_new/ 2>/dev/null
    cp -a /tmp/klipper_cfg_keep/. $CFG/
    cp -a /tmp/klipper_cfg_new/. $CFG/
fi
# logs in RAM on NAND (dp200-start.sh)
[ $TARGET = nand ] && touch $ROOT/etc/dp200/on_nand
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
[ $TARGET = nand ] && [ $DRY_RUN = 0 ] && \
    { [ "$(mb_free /)" -ge 10 ] || fail "NAND full after unpack" "$(mb_free /) MB free"; }
show "Unpacked OK" "$USED MB in $ROOT" "$( [ $TARGET = nand ] && echo "$(mb_free /) MB free" )"

if [ $DRY_RUN = 1 ]; then
    show "DRY RUN complete" "nothing was flashed" "remove $ROOT when done"
    exit 0
fi

show "Installing boot hook" "" "DO NOT POWER OFF"
sh $ROOT/dp200/hook_install.sh || fail "hook failed" "see install log"
UNDO=0
rm -f /etc/dp200-nand          # (old mtd5 marker)
sync

/app/tinydebug led green 2>/dev/null
show "DONE - remove stick" "Web UI: http://<ip>/" "Touch to reboot"
keywait
sync
reboot
exit 0
