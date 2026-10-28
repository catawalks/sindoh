#!/bin/sh
# Build cdc-acm.ko (USB CDC-ACM serial) for the DP200's vendor kernel
# 3.2.0-g67a8e16 without Marvell's SDK: vanilla Linux 3.2 + the printer's own
# config (docs/kernel/vendor_3.2.0-g67a8e16.config). The vendor kernel has no
# CONFIG_MODVERSIONS, so only the vermagic string has to match:
#   3.2.0-g67a8e16 SMP preempt mod_unload ARMv7 p2v8
# Also builds mbcache.ko, which the printer ships as a stock module, so the
# two builds can be compared (same structures -> same field offsets).
#
# Runs on the printer inside the Debian chroot (native armel GCC 14):
#   chroot /mnt/sd sh /usr/src/dp200/klipper_port/install/kernel_modules/build_cdc_acm.sh
# Needs /usr/src/kbuild/linux-3.2.tar.xz (kernel.org, sha256 checked).
set -e
K=/usr/src/kbuild
PORT=/usr/src/dp200/klipper_port
cd $K
rm -rf linux-3.2 mbtest

# Only what a module build needs (the SD card is small): all Kconfig and
# Makefiles, arch/arm, include, scripts, kernel; no other arches, no docs,
# no driver/fs/net/sound sources except the ones built here.
X="--exclude=linux-3.2/Documentation --exclude=linux-3.2/firmware --exclude=linux-3.2/tools"
for a in alpha avr32 blackfin c6x cris frv h8300 hexagon ia64 m32r m68k microblaze mips \
         mn10300 openrisc parisc powerpc s390 score sh sparc tile um unicore32 x86 xtensa; do
    X="$X --exclude=linux-3.2/arch/$a"
done
for d in drivers sound net fs crypto security block ipc mm virt samples; do
    X="$X --exclude=linux-3.2/$d/*.c"
done
tar -xJf linux-3.2.tar.xz --wildcards $X
tar -xJf linux-3.2.tar.xz linux-3.2/drivers/usb/class linux-3.2/fs/mbcache.c
cd linux-3.2

# Kernel 3.2 knows GCC up to 4.x; GCC 14 needs its own compiler header
cp include/linux/compiler-gcc4.h include/linux/compiler-gcc14.h

# Vanilla 3.2 has no ARCH_MV61X0 (Marvell's machine). Any ARMv7 SMP machine
# gives the same generic code and structures; Versatile Express CA9 is one.
cp $PORT/docs/kernel/vendor_3.2.0-g67a8e16.config .config
sed -i -e '/CONFIG_ARCH_MV61X0/d' \
       -e 's/^CONFIG_LOCALVERSION=.*/CONFIG_LOCALVERSION="-g67a8e16"/' \
       -e 's/^CONFIG_LOCALVERSION_AUTO=y/# CONFIG_LOCALVERSION_AUTO is not set/' \
       -e 's/^# CONFIG_USB_ACM is not set/CONFIG_USB_ACM=m/' \
       -e 's/^CONFIG_CROSS_COMPILE=.*/CONFIG_CROSS_COMPILE=""/' .config
printf 'CONFIG_ARCH_VEXPRESS=y\nCONFIG_ARCH_VEXPRESS_CA9X4=y\n' >> .config
yes "" | make ARCH=arm oldconfig > ../oldconfig.log 2>&1 || true

# Options of the vendor config that vanilla 3.2 doesn't know or changed
grep '^CONFIG_' $PORT/docs/kernel/vendor_3.2.0-g67a8e16.config | sort > ../cfg_vendor.txt
grep '^CONFIG_' .config | sort > ../cfg_build.txt
comm -23 ../cfg_vendor.txt ../cfg_build.txt > ../cfg_lost.txt || true

# 2012 kernel, 2025 compiler: no PIE/PIC (Debian default), no stack
# protector, gnu89 inline semantics, common symbols, no unaligned accesses
# (the vendor kernel was built with GCC 4.6, which didn't emit them),
# GCC 14's new hard errors back to warnings.
KCF="-fno-pie -fno-pic -fno-stack-protector -fgnu89-inline -fcommon -mno-unaligned-access -fpermissive -Wno-error"
HCF="-fcommon -fpermissive -Wno-error -std=gnu89"
make ARCH=arm KCFLAGS="$KCF" HOSTCFLAGS="$HCF" modules_prepare
make ARCH=arm KCFLAGS="$KCF" HOSTCFLAGS="$HCF" M=drivers/usb/class modules

mkdir -p ../mbtest
cp fs/mbcache.c ../mbtest/
echo 'obj-m := mbcache.o' > ../mbtest/Makefile
make ARCH=arm KCFLAGS="$KCF" HOSTCFLAGS="$HCF" M=$K/mbtest modules

cd $K
mkdir -p out
cp linux-3.2/drivers/usb/class/cdc-acm.ko mbtest/mbcache.ko out/
for m in out/cdc-acm.ko out/mbcache.ko; do
    cp $m $m.debug
    strip --strip-debug $m
done
# (no modinfo in the chroot)
strings -a out/cdc-acm.ko | grep -E '^(vermagic|license|depends)='
sha256sum out/cdc-acm.ko
echo BUILD OK
