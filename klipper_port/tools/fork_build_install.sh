#!/bin/sh
# Install the build made by ktip.sh (/tmp/kt): klippy + c_helper.so + fm/io,
# then restart Klipper. Also drops copies in the gcodes folder so the PC can
# fetch them over Moonraker (tipbuild_*).
K=/home/klipper/klipper
F=/opt/dp200
S=/tmp/kt
ktinst() {
    [ -f $S/fm.bin ] && [ -f $S/io.bin ] && [ -f $S/klipper/klippy/chelper/c_helper.so ] || { echo "build incomplete"; return 1; }
    G=/home/klipper/printer_data/gcodes
    cp $S/fm.bin $G/tipbuild_fm.bin; cp $S/io.bin $G/tipbuild_io.bin
    cp $S/klipper/klippy/chelper/c_helper.so $G/tipbuild_c_helper.so
    chown klipper:klipper $G/tipbuild_*
    rm -rf $K/klippy.new && cp -a $S/klipper/klippy $K/klippy.new || return 1
    chown -R klipper:klipper $K/klippy.new
    touch $K/klippy.new/chelper/c_helper.so
    rm -rf $K/klippy && mv $K/klippy.new $K/klippy || return 1
    cp $S/fm.bin $F/fm.bin && cp $S/io.bin $F/io.bin || return 1
    sync
    md5sum $F/fm.bin $F/io.bin $K/klippy/chelper/c_helper.so; cat $K/klippy/.version
    /etc/dp200/rc.dp200 restart-klipper
    echo KTINST_DONE
}
ktinst
