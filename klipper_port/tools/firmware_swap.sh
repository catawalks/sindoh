#!/bin/sh
# Swap only the UPC firmware images on the dev printer (klippy unchanged):
#   FM=<file on the PC server> IO=<file or empty> ; . ./kfw.sh
# The images in use are saved once as fm.bin.tip / io.bin.tip (8203a7d7).
U=http://10.10.0.85:8099/deploy/usb/t
F=/opt/dp200
kfw() {
    [ -f $F/fm.bin.tip ] || cp -p $F/fm.bin $F/fm.bin.tip
    [ -f $F/io.bin.tip ] || cp -p $F/io.bin $F/io.bin.tip
    if [ "$FM" = tip ]; then cp $F/fm.bin.tip $F/fm.bin; cp $F/io.bin.tip $F/io.bin
    else
        wget -q -O /tmp/kfw_fm.bin $U/$FM || { echo FETCH_FAIL; return 1; }
        cp /tmp/kfw_fm.bin $F/fm.bin
        if [ -n "$IO" ]; then wget -q -O /tmp/kfw_io.bin $U/$IO || { echo FETCH_FAIL; return 1; }; cp /tmp/kfw_io.bin $F/io.bin; fi
    fi
    sync; md5sum $F/fm.bin $F/io.bin
    /etc/dp200/rc.dp200 restart-klipper
    echo KFW_DONE
}
kfw
