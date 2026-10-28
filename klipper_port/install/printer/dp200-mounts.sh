# Sourced by dp200-start.sh and build_rootfs_native.sh (stock BusyBox side).
# Mounts the API filesystems of the Debian chroot at $ROOT.
#
# The chroot gets its OWN /dev instead of a bind mount of the stock one:
# the stock mdev /dev has every node at 0660 root:root (even /dev/null), so
# non-root users in Debian (_apt, klipper) could not open null/urandom.
# The kernel has no getrandom(), so /dev/urandom must be readable by all.

dp200_mount_root() {
    grep -q " $ROOT/proc " /proc/mounts || mount -t proc proc $ROOT/proc
    grep -q " $ROOT/sys " /proc/mounts || mount -t sysfs sysfs $ROOT/sys
    if ! grep -q " $ROOT/dev " /proc/mounts; then
        mount -t tmpfs -o mode=755,size=512k dev $ROOT/dev
        mknod -m 666 $ROOT/dev/null c 1 3
        mknod -m 666 $ROOT/dev/zero c 1 5
        mknod -m 666 $ROOT/dev/full c 1 7
        mknod -m 666 $ROOT/dev/random c 1 8
        mknod -m 666 $ROOT/dev/urandom c 1 9
        mknod -m 666 $ROOT/dev/tty c 5 0
        mknod -m 666 $ROOT/dev/ptmx c 5 2
        ln -s /proc/self/fd $ROOT/dev/fd
        ln -s /proc/self/fd/0 $ROOT/dev/stdin
        ln -s /proc/self/fd/1 $ROOT/dev/stdout
        ln -s /proc/self/fd/2 $ROOT/dev/stderr
        mkdir -p $ROOT/dev/pts $ROOT/dev/shm
        # root-only devices for upctool (UPC cores, DTCM/XENA via /dev/mem)
        # and the touch screen UI (panel framebuffer, touch controller)
        for d in upc0 upc1 mem console fb0 event0; do
            [ -e /dev/$d ] && cp -a /dev/$d $ROOT/dev/
        done
        # cartridge chip bridge (DS2465 on i2c-3): group klipper, for the
        # read-only [dp200_cartridge] Klipper module
        if [ -e /dev/i2c-3 ]; then
            cp -a /dev/i2c-3 $ROOT/dev/
            chown 0:$(grep '^klipper:' $ROOT/etc/group | cut -d: -f3) $ROOT/dev/i2c-3
            chmod 660 $ROOT/dev/i2c-3
        fi
        # USB serial (major 188; accelerometer board, docs/input_shaping.md):
        # nothing adds nodes to this /dev later, so create them now, group
        # klipper. Opening one with no board plugged in just fails.
        for n in 0 1 2 3; do
            mknod -m 660 $ROOT/dev/ttyUSB$n c 188 $n
            chown 0:$(grep '^klipper:' $ROOT/etc/group | cut -d: -f3) $ROOT/dev/ttyUSB$n
        done
        # webcam (uvcvideo): group "video" (gid 44 in the Debian root) so
        # ustreamer runs as the klipper user
        for d in /dev/video*; do
            [ -e $d ] || continue
            cp -a $d $ROOT/dev/ && chown 0:44 $ROOT$d && chmod 660 $ROOT$d
        done
    fi
    grep -q " $ROOT/dev/pts " /proc/mounts || mount -o bind /dev/pts $ROOT/dev/pts
    grep -q " $ROOT/dev/shm " /proc/mounts || mount -t tmpfs -o size=32m shm $ROOT/dev/shm
    cp /etc/resolv.conf $ROOT/etc/resolv.conf 2>/dev/null
    return 0
}

dp200_umount_root() {
    for m in tmp run/wpa_supplicant run dev/shm dev/pts dev sys proc; do
        grep -q " $ROOT/$m " /proc/mounts && umount $ROOT/$m
    done
    return 0
}
