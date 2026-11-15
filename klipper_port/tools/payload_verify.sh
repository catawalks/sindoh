#!/bin/sh
# Verify the payload in /mnt/sd/payload_out: key files and what must not be in it.
P=/mnt/sd/payload_out/dp200_klipper_payload.tar.gz
L=/tmp/kpayv.log
exec > $L 2>&1
ls -l /mnt/sd/payload_out; cat $P.md5 $P.size
echo "md5 now: $(md5sum < $P)"
T="chroot /mnt/sd /usr/bin/tar"
$T -tzf - < $P > /tmp/paylist.txt
echo "entries: $(wc -l < /tmp/paylist.txt)"
echo "--- must be absent (expect nothing):"
grep -e 'wpa_supplicant.*\.conf' -e 'printer_data/gcodes/.' -e 'printer_data/logs/.' -e 'printer_data/database/.' -e 'pa6170' -e '\.git/' -e 'network\.json' /tmp/paylist.txt | head -10
echo "--- kernel images (expect nothing):"
grep -i -e 'uimage' -e '\.uimg' -e 'zImage' -e '^\./boot/.' /tmp/paylist.txt | head
rm -rf /tmp/payx; mkdir -p /tmp/payx
mountpoint -q /mnt/sd/tmp || mount --bind /tmp /mnt/sd/tmp
$T -xzf - -C /tmp/payx ./home/klipper/klipper/klippy/.version ./home/klipper/klipper/klippy/chelper/c_helper.so \
   ./opt/dp200/fm.bin ./opt/dp200/io.bin ./home/klipper/printer_data/config ./usr/local/bin/dp200_screen.py \
   ./usr/local/bin/dp200_wifi.py ./etc/dp200/rc.dp200 ./etc/dp200/build ./dp200/dp200-netd.sh < $P
cd /tmp/payx
cat home/klipper/klipper/klippy/.version etc/dp200/build
md5sum home/klipper/klipper/klippy/chelper/c_helper.so opt/dp200/fm.bin opt/dp200/io.bin home/klipper/printer_data/config/* \
   usr/local/bin/dp200_screen.py usr/local/bin/dp200_wifi.py etc/dp200/rc.dp200 dp200/dp200-netd.sh
grep -c axis_twist home/klipper/printer_data/config/printer.cfg
grep -n "pinned_commit" home/klipper/printer_data/config/dp200_moonraker.conf
ls /tmp/payx/opt/dp200/ 2>/dev/null; grep -c "^./opt/dp200/" /tmp/paylist.txt
cd /; rm -rf /tmp/payx
echo KPAYV_DONE
