# UPC probe firmware: builds probe_fm.bin and probe_io.bin
#
#   make                         # needs arm-none-eabi-gcc
#
# Reuses the Klipper port's start.S (vectors, stacks, setjmp) and
# linker script so the probe exercises the same startup path.

CROSS ?= arm-none-eabi-
CC = $(CROSS)gcc
OBJCOPY = $(CROSS)objcopy
PORT = ../../klipper/src/upc
COMMON = ../../common
CFLAGS = -march=armv5te -marm -mfloat-abi=soft -Os -Wall -ffreestanding \
         -fno-builtin -ffunction-sections -fdata-sections -I$(COMMON)
LDFLAGS = -nostdlib -nostartfiles -static -Wl,--gc-sections -lgcc

all: probe_fm.bin probe_io.bin

probe_%.ld: $(PORT)/upc.lds.S
	$(CC) -E -P -x c -I. -DCONFIG_UPC_CORE_FM=$(if $(filter fm,$*),1,0) \
	    -DCONFIG_UPC_ITCM_SIZE=0x4000 $< -o $@

probe_%.elf: probe.c thumb_test.S $(PORT)/start.S probe_%.ld
	$(CC) $(CFLAGS) -DPROBE_CORE_FM=$(if $(filter fm,$*),1,0) \
	    probe.c thumb_test.S $(PORT)/start.S -T probe_$*.ld $(LDFLAGS) -o $@

probe_%.bin: probe_%.elf
	$(OBJCOPY) -O binary $< $@

clean:
	rm -f probe_*.ld probe_*.elf probe_*.bin

.PRECIOUS: probe_%.ld probe_%.elf
.PHONY: all clean
