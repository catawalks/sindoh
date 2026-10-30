#!/bin/sh
# i2c variant: bus 2 (touch) registered, read-only checks. No touchscreen
# driver is loaded and nothing is written to any I2C device. Bus 3 (the
# filament cartridge chip) is disabled in the DT and never touched.
dmesg | grep -i 'i2c\|designware'
ls /dev/i2c-* 2>/dev/null
echo "--- i2c-2 registers: enable $(devmem 0xf80a206c) status $(devmem 0xf80a2070) comp-param $(devmem 0xf80a20f4) comp-type $(devmem 0xf80a20fc)"
echo "--- touch reset GPIO 66 (bank 2 bit 2): in $(devmem 0xf8042000) out $(devmem 0xf8042004) dir $(devmem 0xf8042008) pincfg $(devmem 0xf8042088)"
echo "--- probe 0x40 with a read (no command byte):"
i2cdetect -y -r 2 0x40 0x40
