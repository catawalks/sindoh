#!/bin/sh
# Build the FM and IO UPC firmware from /home/klipper/kb (a checkout of the
# fork, klipper/FORK) and leave them in /run as fm_load.bin / io_load.bin.
# Log: /run/kbuild_load.log; ends with KBUILD-LOAD DONE or KBUILD-LOAD FAIL.
cd /home/klipper/kb || exit 1
for c in fm io; do
    make clean >/dev/null 2>&1
    cp config/dp200_$c.config .config
    make olddefconfig >/dev/null 2>&1
    if ! make -j2 >/run/kb_$c.log 2>&1; then
        tail -15 /run/kb_$c.log; echo "KBUILD-LOAD FAIL $c"; exit 1
    fi
    cp out/klipper.bin /run/${c}_load.bin
    md5sum /run/${c}_load.bin
done
echo "KBUILD-LOAD DONE"
