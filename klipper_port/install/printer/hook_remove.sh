#!/bin/sh
# Restore the stock boot: removes the hook line, /etc/dp200-boot.sh and the
# /DEBUG_MACHINE flag. The Klipper root (NAND volume or SD card) stays.
#   sh <root>/dp200/hook_remove.sh && reboot
# (By hand: rm /DEBUG_MACHINE /etc/dp200-boot.sh; cp /etc/profile.stock /etc/profile)
set -e
if [ -f /etc/profile.stock ]; then
    cp /etc/profile.stock /etc/profile
else
    sed -i '/# dp200-klipper hook/d' /etc/profile
fi
rm -f /DEBUG_MACHINE /etc/dp200-boot.sh /etc/dp200-nand
sync
echo "stock boot restored - reboot now"
