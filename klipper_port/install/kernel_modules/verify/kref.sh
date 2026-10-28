#!/bin/sh
# Compile vanilla 3.2 USB core + tty objects with the cdc-acm build setup (comparison only)
set -e
cd /usr/src/kbuild
tar -xJf linux-3.2.tar.xz linux-3.2/drivers/usb/core linux-3.2/drivers/tty/tty_port.c \
    linux-3.2/drivers/tty/tty_buffer.c linux-3.2/drivers/tty/tty_io.c linux-3.2/drivers/tty/tty_ioctl.c
cd linux-3.2
KCF="-fno-pie -fno-pic -fno-stack-protector -fgnu89-inline -fcommon -mno-unaligned-access -fpermissive -Wno-error"
HCF="-fcommon -fpermissive -Wno-error -std=gnu89"
make ARCH=arm KCFLAGS="$KCF" HOSTCFLAGS="$HCF" drivers/usb/core/urb.o drivers/usb/core/usb.o \
    drivers/usb/core/message.o drivers/usb/core/driver.o drivers/tty/tty_port.o \
    drivers/tty/tty_buffer.o drivers/tty/tty_io.o drivers/tty/tty_ioctl.o
O=/home/klipper/printer_data/logs/x_kfuncs
for f in drivers/usb/core/urb.o drivers/usb/core/usb.o drivers/usb/core/message.o drivers/usb/core/driver.o \
         drivers/tty/tty_port.o drivers/tty/tty_buffer.o drivers/tty/tty_io.o drivers/tty/tty_ioctl.o; do
    cp $f $O/ours_$(basename $f)
done
chmod 644 $O/*
echo REF OK
