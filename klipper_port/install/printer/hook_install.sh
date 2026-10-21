#!/bin/sh
# Install the boot hook on the stock firmware (root shell or USB installer):
#
#   sh <root>/dp200/hook_install.sh        <root> = /klipper (NAND) or /mnt/sd
#
# What it does (all reversible with hook_remove.sh):
#   1. copies dp200-boot.sh to /etc/dp200-boot.sh (stage 1: finds the Klipper
#      root on NAND mtd5 or the SD card and starts it)
#   2. backs up /etc/profile to /etc/profile.stock and adds one line to
#      /etc/profile that runs /etc/dp200-boot.sh when the stock UI is bypassed
#   3. creates /DEBUG_MACHINE, which makes the stock /etc/profile skip the
#      Sindoh UI/printer app (built-in vendor mechanism)
# Nothing else in the stock NAND root changes.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
MARK="# dp200-klipper hook"

cp "$HERE/dp200-boot.sh" /etc/dp200-boot.sh
chmod 755 /etc/dp200-boot.sh
if grep -q "$MARK" /etc/profile; then
    # an older hook called /mnt/sd/dp200/dp200-start.sh directly: replace it
    sed -i "/$MARK/d" /etc/profile
fi
[ -f /etc/profile.stock ] || cp /etc/profile /etc/profile.stock
# Insert right after the stock 'Bypass AutoRunning' message
sed -i "/echo \"Bypass AutoRunning\"/a\\
	[ -x /etc/dp200-boot.sh ] \&\& /etc/dp200-boot.sh \& $MARK" /etc/profile
grep -q "$MARK" /etc/profile || { echo "patch failed; /etc/profile restored"; cp /etc/profile.stock /etc/profile; exit 1; }
echo "hook added to /etc/profile (backup: /etc/profile.stock)"
touch /DEBUG_MACHINE
sync
echo "done - reboot to start Klipper"
echo "to go back to the stock firmware: sh $HERE/hook_remove.sh && reboot"
