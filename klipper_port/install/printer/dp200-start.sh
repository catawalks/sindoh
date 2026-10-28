#!/bin/sh
# Started at boot by /etc/dp200-boot.sh (the /etc/profile hook) on the stock
# (BusyBox) side. Enters the Debian root filesystem this script lives in -
# the UBI volume on internal NAND (/klipper) or the microSD card (/mnt/sd) -
# and starts the UPC bridge, Klipper, Moonraker, webcam, screen and nginx.
#
#   <root>/dp200/dp200-start.sh          start (default)
#   <root>/dp200/dp200-start.sh stop     stop everything, UPC cores held
#
# /etc/profile also runs for every ssh login, so a lock directory makes
# sure this only starts once per boot.

ROOT=$(cd "$(dirname "$0")/.." && pwd)
LOG=$ROOT/var/log/dp200-start.log
LOCK=/tmp/dp200-started

in_root() {
    chroot $ROOT /usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
        HOME=/root "$@"
}

# proc/sys and the chroot's own /dev (see dp200-mounts.sh)
. $(dirname "$0")/dp200-mounts.sh

mount_root() {
    dp200_mount_root
    grep -q " $ROOT/run " /proc/mounts || mount -t tmpfs -o size=16m,mode=755 run $ROOT/run
    grep -q " $ROOT/tmp " /proc/mounts || mount -t tmpfs -o size=64m,mode=1777 tmp $ROOT/tmp
    # On NAND, keep the chatty logs in RAM (flash wear); they are lost at
    # power-off. The SD card keeps them on the card.
    if grep -q " $ROOT ubifs " /proc/mounts; then
        for d in var/log home/klipper/printer_data/logs; do
            grep -q " $ROOT/$d " /proc/mounts || mount -t tmpfs -o size=16m,mode=755 logs $ROOT/$d
        done
        chown $(grep '^klipper:' $ROOT/etc/passwd | cut -d: -f3,4) \
            $ROOT/home/klipper/printer_data/logs 2>/dev/null
    fi
}

case "$1" in
stop)
    in_root /etc/dp200/rc.dp200 stop
    rm -rf $LOCK
    exit 0
    ;;
esac

mkdir $LOCK 2>/dev/null || exit 0

# Wait for the stock boot to mount the card
i=0
while [ ! -x $ROOT/etc/dp200/rc.dp200 ] && [ $i -lt 30 ]; do
    sleep 1; i=$((i + 1))
done
if [ ! -x $ROOT/etc/dp200/rc.dp200 ]; then
    echo "dp200-start: no Debian root on $ROOT" > /dev/console
    rm -rf $LOCK
    exit 1
fi
mount_root
mkdir -p $ROOT/var/log
exec >> $LOG 2>&1
echo "==== dp200-start $(date) root=$ROOT"

# The stock app is not running (/DEBUG_MACHINE), but make sure of it,
# and free port 80 for nginx (lighttpd is started by /test/run.sh).
killall UIManager 2>/dev/null
# (killall can't match the app: its name is longer than the 15-char comm field)
for p in $(ps | grep '[g]emstone-debug_stripped' | awk '{print $1}'); do kill $p; done
sleep 1
# The stock touchscreen browser keeps ~100 MB of the 494 MB RAM (no swap:
# the kernel has no CONFIG_SWAP); klippy + Moonraker need it.
killall appBrowser 2>/dev/null
# /etc/profile starts /app/recovery.check.sh before the DEBUG_MACHINE check.
# It relaunches lighttpd every 60 s (and kills it whenever mjpg_streamer has
# leaked > 50 threads), which would fight nginx for port 80: stop it first.
for p in $(ps | grep '[r]ecovery.check' | awk '{print $1}'); do kill $p; done
killall lighttpd 2>/dev/null
# The stock root crontab also starts lighttpd every minute when none is
# running; it then takes port 80 whenever nginx restarts (rc.dp200 restart).
# Run crond from a copy without that line; the stock crontab is untouched.
if [ -f /var/spool/cron/crontabs/root ]; then
    mkdir -p /tmp/dp200-crontabs
    grep -v lighttpd /var/spool/cron/crontabs/root > /tmp/dp200-crontabs/root
    killall crond 2>/dev/null
    crond -l 9 -c /tmp/dp200-crontabs
fi
# The stock mjpg_streamer (YUYV + software JPEG, ~1 core) holds /dev/video0;
# ustreamer in the chroot replaces it (rc.dp200 start_webcam)
killall mjpg_streamer 2>/dev/null
# upc.ko is loaded by the stock /app/module_load.sh
grep -q '^upc ' /proc/modules || insmod /app/upc.ko
# USB accelerometer on the front port (docs/input_shaping.md): the kernel has
# no CDC-ACM driver, so give Klipper's USB ID to the built-in generic USB
# serial driver; a Klipper board then shows up as /dev/ttyUSB0.
echo 1d50 614e > /sys/bus/usb-serial/drivers/generic/new_id 2>/dev/null

# The kernel's text console blanks the panel after 600 s without keyboard
# input (consoleblank, read-only here) and touches don't count. The stock app
# kept it awake; now turn the console screensaver off (setterm -blank 0).
for t in /dev/tty0 /dev/tty1; do printf '\033[9;0]\033[14;0]' > $t 2>/dev/null; done
echo 0 > /sys/class/graphics/fb0/blank 2>/dev/null

# WiFi: joining the owner's network was the stock app's job (see dp200-wifi.sh)
sh $ROOT/dp200/dp200-wifi.sh $ROOT
# network settings from the touch screen (DHCP/static per port, Ethernet hotplug)
mkdir -p $ROOT/run/dp200
if ! { [ -f /var/run/dp200-netd.pid ] && kill -0 $(cat /var/run/dp200-netd.pid) 2>/dev/null; }; then
    sh $ROOT/dp200/dp200-netd.sh $ROOT </dev/null >> $ROOT/var/log/dp200-netd.log 2>&1 &
    echo $! > /var/run/dp200-netd.pid
fi
# Clock: the stock app set it (hwclock); without it the printer thinks it's
# 2013 (wrong log names, file dates, Moonraker history). One-shot NTP once
# the network is up, then save it to the RTC (CR2032 on the board).
( sleep 20; ntpd -n -q -p pool.ntp.org && hwclock -w -u ) </dev/null >/dev/null 2>&1 &
# front power button (hold 5 s = forced shutdown) and the screen's
# reboot/power-off requests
if ! { [ -f /var/run/dp200-powerkey.pid ] && kill -0 $(cat /var/run/dp200-powerkey.pid) 2>/dev/null; }; then
    sh $ROOT/dp200/dp200-powerkey.sh $ROOT </dev/null >> $ROOT/var/log/dp200-powerkey.log 2>&1 &
    echo $! > /var/run/dp200-powerkey.pid
fi
# the touch screen (in the chroot) talks to wpa_supplicant's control socket
mkdir -p $ROOT/run/wpa_supplicant
grep -q " $ROOT/run/wpa_supplicant " /proc/mounts || \
    mount --bind /var/run/wpa_supplicant $ROOT/run/wpa_supplicant
# Marvell's mlanutl (stock firmware) for scans that keep the association;
# runs fine in the chroot. Copied at boot, not shipped in our payload.
cp /lib/modules/8782/mlanutl $ROOT/run/mlanutl 2>/dev/null

in_root /etc/dp200/rc.dp200 start
