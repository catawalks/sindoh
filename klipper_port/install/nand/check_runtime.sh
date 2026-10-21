#!/bin/sh
# Smoke test of an unpacked runtime root (e.g. the installer's dry run):
# do Klipper, Moonraker and the screen UI import without the compilers?
# Run on the stock side:  sh check_runtime.sh /mnt/sd/dryrun_root
R=${1:?usage: check_runtime.sh ROOT}
run() { chroot $R /usr/bin/env -i PATH=/usr/bin:/bin HOME=/tmp "$@"; }
ok=0
for d in proc dev; do grep -q " $R/$d " /proc/mounts || mount --bind /$d $R/$d; done

echo "-- klippy chelper (must load the prebuilt c_helper.so, no gcc in the image)"
run /home/klipper/klippy-env/bin/python -c "
import sys; sys.path.insert(0, '/home/klipper/klipper/klippy')
import chelper
ffi, lib = chelper.get_ffi()
print('chelper ok', lib.stepcompress_fill)" || ok=1
echo "-- klippy imports"
run /home/klipper/klippy-env/bin/python -c "
import sys; sys.path.insert(0, '/home/klipper/klipper/klippy')
import klippy, mcu, toolhead, extras.bed_mesh, extras.upc_stats, extras.upc_clockcheck
print('klippy modules ok')" || ok=1
echo "-- moonraker imports"
run /home/klipper/moonraker-env/bin/python -c "
import sys; sys.path.insert(0, '/home/klipper/moonraker')
import moonraker.server
print('moonraker ok')" || ok=1
echo "-- screen UI"
run /usr/bin/python3 -c "
import sys; sys.path.insert(0, '/usr/local/bin')
from PIL import ImageFont; ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)
import dp200_screen; print('screen ok')" || ok=1
echo "-- binaries"
for b in /usr/bin/ustreamer /usr/sbin/nginx /usr/local/bin/upctool /usr/local/lib/v4l2_time32_shim.so; do
    [ -e $R$b ] && echo "ok $b" || { echo "MISSING $b"; ok=1; }
done
for d in dev proc; do umount $R/$d 2>/dev/null; done
[ $ok = 0 ] && echo "RUNTIME OK" || echo "RUNTIME PROBLEMS"
exit $ok
