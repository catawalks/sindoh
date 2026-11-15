#!/bin/sh
# Switch the dev printer between Klipper builds (docs/dev_printer_testing.md).
# Serve this file from the PC, wget it on the printer, then:  N=b|c|cur ; . ./klippy_switch.sh
#   b, c = dp200-clean stage B / C (klippy from /tmp/kb/$N, firmware from the PC)
#   cur  = back to sindoh-dp200 289952f9 (saved copies)
# Host code and both firmware images change together, then Klipper restarts.
U=http://10.10.0.85:8099/deploy/usb/t
K=/home/klipper/klipper
F=/opt/dp200
kinst() {
    case "$N" in b|c|cur) ;; *) echo "BAD N"; return 1;; esac
    # one-time rollback copies
    [ -d $K/klippy.cur ] || cp -a $K/klippy $K/klippy.cur || return 1
    [ -f $F/fm.bin.cur ] || cp -p $F/fm.bin $F/fm.bin.cur || return 1
    [ -f $F/io.bin.cur ] || cp -p $F/io.bin $F/io.bin.cur || return 1
    if [ "$N" = cur ]; then
        src=$K/klippy.cur; fm=$F/fm.bin.cur; io=$F/io.bin.cur
    else
        src=/tmp/kb/$N/klippy
        [ -f $src/chelper/c_helper.so ] || { echo "NO c_helper.so for $N"; return 1; }
        wget -q -O /tmp/fm-$N.bin $U/fm-clean-$N.bin && wget -q -O /tmp/io-$N.bin $U/io-clean-$N.bin || { echo FETCH_FAIL; return 1; }
        fm=/tmp/fm-$N.bin; io=/tmp/io-$N.bin
    fi
    rm -rf $K/klippy.new && cp -a $src $K/klippy.new || return 1
    [ "$N" = cur ] || echo "dp200-clean-$N" > $K/klippy.new/.version
    chown -R klipper:klipper $K/klippy.new
    touch $K/klippy.new/chelper/c_helper.so
    rm -rf $K/klippy && mv $K/klippy.new $K/klippy || return 1
    cp $fm $F/fm.bin && cp $io $F/io.bin || return 1
    sync
    md5sum $F/fm.bin $F/io.bin $K/klippy/chelper/c_helper.so
    /etc/dp200/rc.dp200 restart-klipper
    echo "KINST_DONE $N"
}
kinst
