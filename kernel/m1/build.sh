#!/bin/bash
# Build the DP200 milestone-1 image (docs/no_gpl_plan.md 2.4):
#   m1.uimg = U-Boot legacy uImage of (zImage + appended DTB), with a
#   static musl BusyBox initramfs built into the kernel.
#
# Runs in WSL (Debian 13) or any Debian-like Linux with:
#   build-essential gcc-arm-linux-gnueabihf bc flex bison xz-utils
#   u-boot-tools cpio python3
# Trees and build dirs go to $WORK (needs a case-sensitive file system),
# the results to $OUT. Re-running only rebuilds what changed.
set -euo pipefail

M1=$(cd "$(dirname "$0")" && pwd)
KVER=6.18.59
BBVER=1.38.0
MUSLVER=1.2.6
DL=${DL:-/mnt/d/DP200/kernel/src}
WORK=${WORK:-$HOME/dp200}
OUT=${OUT:-/mnt/d/DP200/kernel/out}
CROSS=arm-linux-gnueabihf-
JOBS=${JOBS:-$(nproc)}

KSRC=$WORK/linux-$KVER
KOUT=$WORK/build-m1
SYSROOT=$WORK/sysroot
BB=$WORK/busybox-$BBVER
IRFS=$WORK/initramfs-m1
KMAKE=(make -C "$KSRC" O="$KOUT" ARCH=arm CROSS_COMPILE=$CROSS)

mkdir -p "$WORK" "$OUT"

# Sources, checked against the sums published by kernel.org, busybox.net
# and musl.libc.org (fetched over HTTPS on 2026-10-28)
check() { echo "$2  $1" | sha256sum -c --quiet; }
check "$DL/linux-$KVER.tar.xz" 53a55ac9863a5547e292b8e381d4e4c2240dd1127d5428a7c44dbc550be23963
check "$DL/busybox/busybox-$BBVER.tar.bz2" 34f9ea6ff8636f2c9241153b9114eefa9e65674a45318ae1ef95bb5f31c53bb2
check "$DL/musl/musl-$MUSLVER.tar.gz" d585fd3b613c66151fc3249e8ed44f77020cb5e6c1e635a616d3f9f82460512a

# 1. Kernel tree: vanilla + our files + the Kconfig/Makefile/CPU hooks
[ -d "$KSRC" ] || tar -C "$WORK" -xJf "$DL/linux-$KVER.tar.xz"
cp -r "$M1/src/." "$KSRC/"
for p in "$M1"/patches/*.patch; do
	if ! patch -d "$KSRC" -p1 -R -s -f --dry-run < "$p" > /dev/null 2>&1; then
		patch -d "$KSRC" -p1 -N -s < "$p"
	fi
done

# 2. musl for armhf, plus the kernel UAPI headers BusyBox needs
if [ ! -f "$SYSROOT/lib/libc.a" ]; then
	rm -rf "$WORK/musl-$MUSLVER"
	tar -C "$WORK" -xzf "$DL/musl/musl-$MUSLVER.tar.gz"
	(cd "$WORK/musl-$MUSLVER" &&
	 ./configure --target=arm-linux-gnueabihf --prefix="$SYSROOT" \
		--syslibdir="$SYSROOT/lib" --disable-shared --enable-wrapper=gcc \
		CROSS_COMPILE=$CROSS CFLAGS=-Os > /dev/null &&
	 make -j"$JOBS" > /dev/null && make install > /dev/null)
fi
if [ ! -f "$SYSROOT/include/linux/version.h" ]; then
	make -C "$KSRC" O="$WORK/build-hdr" ARCH=arm headers_install \
		INSTALL_HDR_PATH="$SYSROOT" > /dev/null
fi

# 3. BusyBox (static, musl)
if [ ! -x "$BB/busybox" ] || [ "$M1/busybox.config" -nt "$BB/busybox" ]; then
	rm -rf "$BB"
	tar -C "$WORK" -xjf "$DL/busybox/busybox-$BBVER.tar.bz2"
	make -C "$BB" allnoconfig > /dev/null
	# BusyBox's kconfig ignores reassignments: drop the old lines first
	tr -d '\r' < "$M1/busybox.config" > "$BB/m1.config"
	for s in $(grep -o '^CONFIG_[A-Za-z0-9_]*' "$BB/m1.config"); do
		sed -i -e "/^$s=/d" -e "/^# $s is not set/d" "$BB/.config"
	done
	cat "$BB/m1.config" >> "$BB/.config"
	{ yes "" || true; } | make -C "$BB" oldconfig > /dev/null
	python3 -I "$M1/checkconfig.py" "$BB/.config" "$M1/busybox.config"
	make -C "$BB" -j"$JOBS" CC="$SYSROOT/bin/musl-gcc" CROSS_COMPILE=$CROSS \
		busybox > /dev/null
fi
[ -f "$BB/busybox.links" ] || make -C "$BB" busybox.links > /dev/null

# 4. Initramfs list (gen_init_cpio format), applet links from busybox.links
mkdir -p "$IRFS"
tr -d '\r' < "$M1/initramfs/init" > "$IRFS/init"
{
	echo "dir /dev 0755 0 0"
	echo "nod /dev/console 0600 0 0 c 5 1"
	for d in proc sys bin sbin usr usr/bin usr/sbin root; do
		echo "dir /$d 0755 0 0"
	done
	echo "dir /tmp 1777 0 0"
	echo "file /bin/busybox $BB/busybox 0755 0 0"
	echo "file /init $IRFS/init 0755 0 0"
	grep -v '^/bin/busybox$' "$BB/busybox.links" | sort -u |
		while read -r l; do echo "slink $l /bin/busybox 0777 0 0"; done
} > "$IRFS/initramfs.list"

# 5. Kernel: tinyconfig + m1.config, every fragment line must survive
mkdir -p "$KOUT"
"${KMAKE[@]}" tinyconfig > /dev/null
tr -d '\r' < "$M1/m1.config" |
	sed "s#@INITRAMFS_LIST@#$IRFS/initramfs.list#" > "$KOUT/m1.config"
(cd "$KSRC" && ARCH=arm CROSS_COMPILE=$CROSS \
	scripts/kconfig/merge_config.sh -m -O "$KOUT" "$KOUT/.config" \
	"$KOUT/m1.config" > /dev/null)
"${KMAKE[@]}" olddefconfig > /dev/null
python3 -I "$M1/checkconfig.py" "$KOUT/.config" "$KOUT/m1.config"
"${KMAKE[@]}" -j"$JOBS" zImage dtbs

# 6. zImage + DTB, wrapped for bootm (load = entry = 0x8000)
DTB=$KOUT/arch/arm/boot/dts/marvell/88pa6170-dp200.dtb
cat "$KOUT/arch/arm/boot/zImage" "$DTB" > "$OUT/m1-zImage-dtb.bin"
mkimage -A arm -O linux -T kernel -C none -a 0x00008000 -e 0x00008000 \
	-n "DP200 M1 linux-$KVER" -d "$OUT/m1-zImage-dtb.bin" "$OUT/m1.uimg" > /dev/null
cp "$KOUT/vmlinux" "$OUT/m1-vmlinux"
cp "$KOUT/System.map" "$OUT/m1-System.map"
cp "$KOUT/.config" "$OUT/m1-full.config"
cp "$DTB" "$OUT/m1.dtb"
(cd "$OUT" && {
	echo "built $(date -u +%Y-%m-%dT%H:%MZ) linux-$KVER"
	stat -c '%n %s bytes' m1.uimg m1-zImage-dtb.bin m1.dtb
	md5sum m1.uimg m1-zImage-dtb.bin
	mkimage -l m1.uimg
} | tee m1-info.txt)
