#!/bin/bash
# Build a DP200 mainline test image (docs/no_gpl_plan.md 2.4 and on):
# a U-Boot legacy uImage of (zImage + appended DTB) with a static musl
# BusyBox initramfs built in.
#
#   VARIANT=base (default)  $OUT/m1.uimg           milestone 1 + extras
#   VARIANT=net             $OUT/m1-net.uimg       Wi-Fi join + kexec loader
#   VARIANT=upc             $OUT/m1-upc.uimg       UPC driver (/dev/upc0/1)
#   VARIANT=sd              $OUT/m1-sd.uimg        SD socket, read-only use
#   VARIANT=gpio            $OUT/m1-gpio.uimg      GPIO banks, nothing driven
#   VARIANT=eth             $OUT/m1-eth.uimg       small Ethernet + kexec loader
#
# A variant merges variants/<v>.config after m1.config, uses
# variants/<v>.dts (the base DTS with nodes enabled) if present, and adds
# initramfs/<v>/ plus its userspace (below). See README.md.
#
# Runs in WSL (Debian 13) or any Debian-like Linux with:
#   build-essential gcc-arm-linux-gnueabihf bc flex bison xz-utils
#   u-boot-tools cpio python3 rsync pkgconf
# Trees and build dirs go to $WORK (needs a case-sensitive file system),
# the results to $OUT. Re-running only rebuilds what changed.
set -euo pipefail

M1=$(cd "$(dirname "$0")" && pwd)
KVER=6.18.59
BBVER=1.38.0
MUSLVER=1.2.6
LIBNLVER=3.12.0
IWVER=6.17
WPAVER=2.12
KEXECVER=2.0.32
VARIANT=${VARIANT:-base}
DL=${DL:-/mnt/d/DP200/kernel/src}
WORK=${WORK:-$HOME/dp200}
OUT=${OUT:-/mnt/d/DP200/kernel/out}
CROSS=arm-linux-gnueabihf-
JOBS=${JOBS:-$(nproc)}

case $VARIANT in
base)	USERSPACE="iw uvcgrab" ;;
net)	USERSPACE="iw uvcgrab wpa" ;;
upc)	USERSPACE="iw uvcgrab upctool" ;;
sd|gpio) USERSPACE="iw uvcgrab" ;;
eth)	USERSPACE="kexec" ;;	# small loader: no Wi-Fi, no firmware
*)	echo "unknown VARIANT=$VARIANT (base net upc sd gpio eth)" >&2; exit 1 ;;
esac
if [ "$VARIANT" = base ]; then
	NAME=m1
	KOUT=$WORK/build-m1
	IRFS=$WORK/initramfs-m1
else
	NAME=m1-$VARIANT
	KOUT=$WORK/build-m1-$VARIANT
	IRFS=$WORK/initramfs-m1-$VARIANT
fi

# THUMB2=1: Thumb-2 kernel (smaller; not yet proven on the PJ4B-MP)
if [ "${THUMB2:-0}" = 1 ]; then
	NAME=$NAME-t2
	KOUT=$KOUT-t2
fi
# SMP=1: SMP even for the uniprocessor variants (net, eth), e.g. to tell a
# UP-only bug from a variant bug. No kexec then (ARM needs CPU hotplug).
if [ "${SMP:-0}" = 1 ]; then
	NAME=$NAME-smp
	KOUT=$KOUT-smp
fi

KSRC=$WORK/linux-$KVER
SYSROOT=$WORK/sysroot
BB=$WORK/busybox-$BBVER
KMAKE=(make -C "$KSRC" O="$KOUT" ARCH=arm CROSS_COMPILE=$CROSS)
MUSLCC=$SYSROOT/bin/musl-gcc

mkdir -p "$WORK" "$OUT"

# Sources, checked against the sums published by kernel.org, busybox.net,
# musl.libc.org and GitHub (libnl); wpa_supplicant against its GPG
# signature (Jouni Malinen, EC4A A0A9 91A5 F246 4582 D52D 2B6E F432 EFC8 95FA)
check() { echo "$2  $1" | sha256sum -c --quiet; }
check "$DL/linux-$KVER.tar.xz" 53a55ac9863a5547e292b8e381d4e4c2240dd1127d5428a7c44dbc550be23963
check "$DL/busybox/busybox-$BBVER.tar.bz2" 34f9ea6ff8636f2c9241153b9114eefa9e65674a45318ae1ef95bb5f31c53bb2
check "$DL/musl/musl-$MUSLVER.tar.gz" d585fd3b613c66151fc3249e8ed44f77020cb5e6c1e635a616d3f9f82460512a
check "$DL/libnl/libnl-$LIBNLVER.tar.gz" fc51ca7196f1a3f5fdf6ffd3864b50f4f9c02333be28be4eeca057e103c0dd18
check "$DL/iw/iw-$IWVER.tar.xz" 7d182e498289ab39b257da6780d562e415377107f50358ee5b55b8cfe40b1e33
check "$DL/wpa/wpa_supplicant-$WPAVER.tar.gz" 08e23937e16d0155e55cab2b51f51fbe10d80a1aa91c4e15442645059b737ef6
check "$DL/kexec/kexec-tools-$KEXECVER.tar.xz" 8f81422a5fd2362cf6cb001b511e535565ed0f32c2f4451fb5eb68fed6710a5d

# 1. Kernel tree: vanilla + our files + the Kconfig/Makefile/CPU hooks
[ -d "$KSRC" ] || tar -C "$WORK" -xJf "$DL/linux-$KVER.tar.xz"
cp -r "$M1/src/." "$KSRC/"
for p in "$M1"/patches/*.patch; do
	if ! patch -d "$KSRC" -p1 -R -s -f --dry-run < "$p" > /dev/null 2>&1; then
		patch -d "$KSRC" -p1 -N -s < "$p"
	fi
done

# 2. musl for armhf, plus the kernel UAPI headers the userspace needs
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
	python3 -I "$M1/checkconfig.py" "$BB/.config" "$BB/m1.config"
	make -C "$BB" -j"$JOBS" CC="$MUSLCC" CROSS_COMPILE=$CROSS \
		busybox > /dev/null
	rm -f "$BB/busybox.links"
fi
[ -f "$BB/busybox.links" ] || make -C "$BB" busybox.links > /dev/null

# 4. Extra userspace, each static against musl
build_libnl() {
	local src=$WORK/libnl-$LIBNLVER
	[ -f "$SYSROOT/lib/libnl-genl-3.a" ] && return
	rm -rf "$src"
	tar -C "$WORK" -xzf "$DL/libnl/libnl-$LIBNLVER.tar.gz"
	(cd "$src" &&
	 ./configure --host=arm-linux-gnueabihf --prefix="$SYSROOT" \
		--disable-shared --enable-static --disable-cli --disable-debug \
		CC="$MUSLCC" > /dev/null &&
	 make -j"$JOBS" > /dev/null && make install > /dev/null)
}
build_iw() {	# iw: Wi-Fi scans and link state
	IW=$WORK/iw-$IWVER
	build_libnl
	[ -x "$IW/iw" ] && return
	rm -rf "$IW"
	tar -C "$WORK" -xJf "$DL/iw/iw-$IWVER.tar.xz"
	make -C "$IW" -j"$JOBS" CC="$MUSLCC" LDFLAGS=-static \
		PKG_CONFIG="pkg-config --static" \
		PKG_CONFIG_LIBDIR="$SYSROOT/lib/pkgconfig" > /dev/null
	${CROSS}strip "$IW/iw"
}
build_uvcgrab() {	# one MJPEG frame from the webcam
	"$MUSLCC" -static -Os -Wall -o "$WORK/uvcgrab" "$M1/tools/uvcgrab.c"
	${CROSS}strip "$WORK/uvcgrab"
}
build_wpa() {	# wpa_supplicant + wpa_passphrase, WPA2-PSK over nl80211
	WPA=$WORK/wpa_supplicant-$WPAVER/wpa_supplicant
	build_libnl
	if [ ! -x "$WPA/wpa_supplicant" ] ||
	   [ "$M1/wpa_supplicant.config" -nt "$WPA/wpa_supplicant" ]; then
		rm -rf "$WORK/wpa_supplicant-$WPAVER"
		tar -C "$WORK" -xzf "$DL/wpa/wpa_supplicant-$WPAVER.tar.gz"
		tr -d '\r' < "$M1/wpa_supplicant.config" > "$WPA/.config"
		make -C "$WPA" -j"$JOBS" CC="$MUSLCC" LDFLAGS=-static \
			LIBNL_INC="$SYSROOT/include/libnl3" \
			LIBS="-lnl-genl-3 -lnl-3" \
			wpa_supplicant wpa_passphrase > /dev/null
		${CROSS}strip "$WPA/wpa_supplicant" "$WPA/wpa_passphrase"
	fi
}
build_kexec() {	# kexec-tools, for netload
	KX=$WORK/kexec-tools-$KEXECVER
	[ -x "$KX/build/sbin/kexec" ] && return
	rm -rf "$KX"
	tar -C "$WORK" -xJf "$DL/kexec/kexec-tools-$KEXECVER.tar.xz"
	(cd "$KX" &&
	 ./configure --host=arm-linux-gnueabihf --without-xen --without-zlib \
		--without-lzma CC="$MUSLCC" LDFLAGS=-static > /dev/null &&
	 make -j"$JOBS" > /dev/null)
	${CROSS}strip "$KX/build/sbin/kexec"
}
build_upctool() {	# host/upctool, the stock-compatible UPC tool
	"$MUSLCC" -static -O2 -Wall -std=gnu99 -o "$WORK/upctool" \
		"$M1/../../host/upctool.c"
	${CROSS}strip "$WORK/upctool"
}
for u in $USERSPACE; do "build_$u"; done

# 5. Wi-Fi firmware from the stock rootfs (a Marvell binary: never commit
#    it, and don't publish the images that contain it)
FW8782=${FW8782:-/mnt/d/DP200/backup/171114_4_open/lib/firmware/mrvl/usb8782_uapsta.bin}
if [ "$VARIANT" != eth ]; then
	echo "6c11556fd22089c7f084613549a721e2  $FW8782" | md5sum -c --quiet
fi
if [ "$VARIANT" = upc ]; then
	(cd "$M1/../../prebuilt" && md5sum -c --quiet) <<-EOF
	96cddffd5fccf68ca6e742b8ee783708  probe_io.bin
	1ec429d52b1a15dae194fbb8b579c1cc  probe_fm.bin
	EOF
fi

# 6. Initramfs list (gen_init_cpio format), applet links from busybox.links
rm -rf "$IRFS" && mkdir -p "$IRFS"
for f in init m1-checks.sh; do
	tr -d '\r' < "$M1/initramfs/$f" > "$IRFS/$f"
done
tr -d '\r' < "$M1/initramfs/net/netload" > "$IRFS/netload"
tr -d '\r' < "$M1/initramfs/net/udhcpc.script" > "$IRFS/udhcpc.script"
if [ -d "$M1/initramfs/$VARIANT" ]; then
	for f in "$M1/initramfs/$VARIANT"/*; do
		tr -d '\r' < "$f" > "$IRFS/$(basename "$f")"
	done
fi
# eth: the fast path's defaults (the PC's HTTP server, the file name
# tools/eth_kernel_boot.sh publishes the next test kernel under, and the
# kexec watchdog in seconds: user-approved 2026-10-29, 0 turns it off)
if [ "$VARIANT" = eth ]; then
	printf 'PC=%s\nPORT=%s\nFILE=%s\nWDT=%s\n' "${ETHLOAD_PC:-10.10.0.85}" \
		"${ETHLOAD_PORT:-8099}" "${ETHLOAD_FILE:-next-zImage-dtb.bin}" \
		"${ETHLOAD_WDT:-60}" > "$IRFS/ethload.conf"
fi
{
	echo "dir /dev 0755 0 0"
	echo "nod /dev/console 0600 0 0 c 5 1"
	for d in proc sys bin sbin usr usr/bin usr/sbin usr/share \
		 usr/share/udhcpc root etc mnt lib lib/firmware \
		 lib/firmware/mrvl; do
		echo "dir /$d 0755 0 0"
	done
	echo "dir /tmp 1777 0 0"
	echo "file /bin/busybox $BB/busybox 0755 0 0"
	echo "file /init $IRFS/init 0755 0 0"
	echo "file /etc/m1-checks.sh $IRFS/m1-checks.sh 0755 0 0"
	echo "file /usr/share/udhcpc/default.script $IRFS/udhcpc.script 0755 0 0"
	[ "$VARIANT" != eth ] &&
		echo "file /lib/firmware/mrvl/usb8782_uapsta.bin $FW8782 0644 0 0"
	[ -f "$IRFS/ethload" ] &&
		echo "file /usr/bin/ethload $IRFS/ethload 0755 0 0"
	[ -f "$IRFS/eth-pinmux.sh" ] &&
		echo "file /etc/eth-pinmux.sh $IRFS/eth-pinmux.sh 0755 0 0"
	[ -f "$IRFS/ethload.conf" ] &&
		echo "file /etc/ethload.conf $IRFS/ethload.conf 0644 0 0"
	[ -f "$IRFS/variant.sh" ] &&
		echo "file /etc/m1-variant.sh $IRFS/variant.sh 0755 0 0"
	[ -f "$IRFS/xena-dump.sh" ] &&
		echo "file /usr/bin/xena-dump $IRFS/xena-dump.sh 0755 0 0"
	[ -f "$IRFS/xena-padmap.sh" ] &&
		echo "file /usr/bin/xena-padmap $IRFS/xena-padmap.sh 0755 0 0"
	for u in $USERSPACE; do
		case $u in
		iw)	echo "file /usr/sbin/iw $IW/iw 0755 0 0" ;;
		uvcgrab) echo "file /usr/bin/uvcgrab $WORK/uvcgrab 0755 0 0" ;;
		wpa)	echo "file /usr/sbin/wpa_supplicant $WPA/wpa_supplicant 0755 0 0"
			echo "file /usr/bin/wpa_passphrase $WPA/wpa_passphrase 0755 0 0"
			echo "file /usr/bin/wifi-join $IRFS/wifi-join 0755 0 0"
			;;
		kexec)	echo "file /usr/sbin/kexec $KX/build/sbin/kexec 0755 0 0"
			echo "file /usr/bin/netload $IRFS/netload 0755 0 0" ;;
		upctool) echo "file /usr/bin/upctool $WORK/upctool 0755 0 0"
			# the passive probe firmware (upc_fw/probe, prebuilt), for
			# upctool load; md5 checked like the Wi-Fi firmware
			echo "dir /lib/firmware/upc 0755 0 0"
			for c in io fm; do
				echo "file /lib/firmware/upc/probe_$c.bin $M1/../../prebuilt/probe_$c.bin 0644 0 0"
			done ;;
		esac
	done
	grep -v '^/bin/busybox$' "$BB/busybox.links" | sort -u |
		while read -r l; do echo "slink $l /bin/busybox 0777 0 0"; done
} > "$IRFS/initramfs.list"

# 7. Kernel: tinyconfig + m1.config (+ the variant), every line must stick
mkdir -p "$KOUT"
"${KMAKE[@]}" tinyconfig > /dev/null
{
	tr -d '\r' < "$M1/m1.config"
	if [ -f "$M1/variants/$VARIANT.config" ]; then
		tr -d '\r' < "$M1/variants/$VARIANT.config"
	fi
	if [ "${THUMB2:-0}" = 1 ]; then
		echo "CONFIG_THUMB2_KERNEL=y"
	fi
	if [ "${SMP:-0}" = 1 ]; then
		echo "CONFIG_SMP=y"
		echo "CONFIG_NR_CPUS=2"
		echo "# CONFIG_KEXEC is not set"
	fi
} | sed "s#@INITRAMFS_LIST@#$IRFS/initramfs.list#" > "$KOUT/m1.config"
(cd "$KSRC" && ARCH=arm CROSS_COMPILE=$CROSS \
	scripts/kconfig/merge_config.sh -m -O "$KOUT" "$KOUT/.config" \
	"$KOUT/m1.config" > /dev/null)
"${KMAKE[@]}" olddefconfig > /dev/null
python3 -I "$M1/checkconfig.py" "$KOUT/.config" "$KOUT/m1.config"
"${KMAKE[@]}" -j"$JOBS" zImage dtbs

# 8. The DTB: the base board, or the variant's DTS on top of it
DTB=$KOUT/arch/arm/boot/dts/marvell/88pa6170-dp200.dtb
if [ -f "$M1/variants/$VARIANT.dts" ]; then
	DTB=$KOUT/$NAME.dtb
	cpp -nostdinc -undef -D__DTS__ -x assembler-with-cpp \
		-I "$KSRC/include" -I "$KSRC/scripts/dtc/include-prefixes" \
		-I "$KSRC/arch/arm/boot/dts/marvell" \
		"$M1/variants/$VARIANT.dts" |
		"$KOUT/scripts/dtc/dtc" -q -I dts -O dtb -o "$DTB" -
fi

# 9. zImage + DTB, wrapped for bootm (load = entry = 0x8000)
cat "$KOUT/arch/arm/boot/zImage" "$DTB" > "$OUT/$NAME-zImage-dtb.bin"
mkimage -A arm -O linux -T kernel -C none -a 0x00008000 -e 0x00008000 \
	-n "DP200 $NAME linux-$KVER" -d "$OUT/$NAME-zImage-dtb.bin" \
	"$OUT/$NAME.uimg" > /dev/null
cp "$KOUT/vmlinux" "$OUT/$NAME-vmlinux"
cp "$KOUT/System.map" "$OUT/$NAME-System.map"
cp "$KOUT/.config" "$OUT/$NAME-full.config"
cp "$DTB" "$OUT/$NAME.dtb"
(cd "$OUT" && {
	echo "built $(date -u +%Y-%m-%dT%H:%MZ) $NAME linux-$KVER"
	stat -c '%n %s bytes' "$NAME.uimg" "$NAME-zImage-dtb.bin" "$NAME.dtb"
	md5sum "$NAME.uimg" "$NAME-zImage-dtb.bin"
	mkimage -l "$NAME.uimg"
} | tee "$NAME-info.txt")
