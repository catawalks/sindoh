# Additional build rules for the Marvell 88PA6170 UPC cores (Sindoh DP200)

CROSS_PREFIX=arm-none-eabi-

dirs-y += src/upc src/generic

# No -ffreestanding/-fno-builtin: Klipper's generated compile_time_request.c
# needs strcmp() on constant strings folded at compile time.
CFLAGS += -march=armv5te -mfloat-abi=soft -fno-pie -Os -Isrc/upc/include
ifeq ($(CONFIG_UPC_THUMB),y)
CFLAGS += -mthumb -mthumb-interwork
else
CFLAGS += -marm
endif

CFLAGS_klipper.elf += -nostdlib -nostartfiles -static
CFLAGS_klipper.elf += -T $(OUT)src/upc/upc.ld -Wl,--gc-sections -lgcc
$(OUT)klipper.elf: $(OUT)src/upc/upc.ld

# Add source files
src-y += upc/main.c upc/timer.c upc/gpio.c
src-y += generic/crc16_ccitt.c generic/timer_irq.c generic/serial_irq.c
src-$(CONFIG_WANT_ADC) += upc/adc.c

OBJS_klipper.elf += $(OUT)src/upc/start.o

$(OUT)src/upc/start.o: src/upc/start.S $(OUT)autoconf.h
	@echo "  Assembling $@"
	$(Q)$(CC) $(filter-out -flto=auto -fwhole-program,$(CFLAGS)) -c $< -o $@

# Raw ITCM image for 'upctool load'
target-y += $(OUT)klipper.bin

$(OUT)klipper.bin: $(OUT)klipper.elf
	@echo "  Creating ITCM image $@"
	$(Q)$(OBJCOPY) -O binary $< $@
	$(Q)$(PYTHON) -c "import os,sys; n=os.path.getsize(sys.argv[1]); print('  ITCM image: %d of %d bytes' % (n, $(CONFIG_UPC_ITCM_SIZE))); sys.exit(n > $(CONFIG_UPC_ITCM_SIZE))" $@
