#!/bin/sh
# full variant: read-only overview of every enabled block (built, not yet
# booted: check each section against its own variant's results)
dmesg | grep -i 'upc\|sdhci\|mmc\|gpio\|i2c\|rtc\|consoleblank'
echo "--- cmdline: $(cat /proc/cmdline)"
echo "--- block devices: $(ls /sys/block)"
echo "--- RTC: $(cat /sys/class/rtc/rtc0/date 2>/dev/null) $(cat /sys/class/rtc/rtc0/time 2>/dev/null)"
echo "--- UPC: $(ls /dev/upc* 2>/dev/null), CPUSoftReset $(devmem 0xf9208154), XIRD1 $(devmem 0xf920965c)"
echo "--- i2c: $(ls /dev/i2c-* 2>/dev/null)"
echo "--- input: $(ls /dev/input 2>/dev/null)"
