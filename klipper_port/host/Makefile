# Build upctool as a static armhf binary (runs on the stock BusyBox/glibc
# 2.15 userland and inside a Debian chroot alike).
#
#   make                       # uses arm-linux-gnueabihf-gcc
#   make CC="zig cc -target arm-linux-musleabihf -mcpu=cortex_a9-neon-d32-fp16"
#
# A static link avoids any dependency on the printer's old glibc.
# The Marvell PJ4 has VFPv3-D16: code must never touch d16-d31, hence
# -mfpu=vfpv3-d16 (gcc) / "-neon-d32" (zig/clang).

CC ?= arm-linux-gnueabihf-gcc
ifeq ($(origin CC),default)
CC = arm-linux-gnueabihf-gcc
endif
ARCHFLAGS ?= -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=hard
CFLAGS ?= -O2 -Wall -Wextra -Wno-unused-parameter -std=gnu99 $(ARCHFLAGS)
LDFLAGS ?= -static

upctool: upctool.c ../common/upc_hw.h ../common/upc_ipc.h
	$(CC) $(CFLAGS) -o $@ upctool.c $(LDFLAGS)

clean:
	rm -f upctool

.PHONY: clean
