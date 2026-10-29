#!/bin/sh
# Milestone 1 checks (docs/no_gpl_plan.md 2.4), run once by /init.
echo
echo "=== DP200 milestone 1: $(uname -a)"
echo "--- cmdline: $(cat /proc/cmdline)"
grep -E '^(model name|Features|CPU (implementer|variant|part|revision))' /proc/cpuinfo
echo "--- CPUs online: $(cat /sys/devices/system/cpu/online), framebuffer: $(cat /proc/fb)"
echo "--- clocksource: $(cat /sys/devices/system/clocksource/clocksource0/current_clocksource)"
echo "--- clockevent: $(cat /sys/devices/system/clockevents/clockevent0/current_device)"
echo "--- /proc/interrupts:"
cat /proc/interrupts

# Timekeeping: timer 2 ticks (1 MHz) and uptime across sleep 2 must agree,
# and mv61x0_timer1 must grow by ~200
P=/sys/module/timer_mv61x0/parameters
t0=$(devmem 0xf802002c); u0=$(cut -d' ' -f1 /proc/uptime)
sleep 2
t1=$(devmem 0xf802002c); u1=$(cut -d' ' -f1 /proc/uptime)
echo "--- sleep 2: timer2 $t0 -> $t1 ($(( (t1 - t0) & 0xffffffff )) us), uptime $u0 -> $u1"
echo "--- clocksource glitches: $(cat $P/glitches) (last $(cat $P/glitch_first) -> $(cat $P/glitch_second))"
grep mv61x0 /proc/interrupts
echo "--- timer status $(devmem 0xf8020010), timer1 count $(devmem 0xf802001c)"

# Ethernet (no cable on this printer): the PHY ID read over MDIO must be
# 0x01410dd1 (88E1510); eth0 gets 10.10.0.250/24 (10.10.0.21 is stock Wi-Fi)
echo "--- MDIO PHYs: $(for p in /sys/bus/mdio_bus/devices/*:*; do echo "$p $(cat $p/phy_id)"; done)"
ifconfig eth0 10.10.0.250 netmask 255.255.255.0 up
ifconfig eth0

# USB: the on-board hub 1a40:0101 behind ehci.1, Wi-Fi 1286:2040 (88W8782)
# and camera 0c45:6341 on it. bcdDevice and the endpoints tell the 8782's
# boot ROM from running firmware (they share the product ID).
echo "--- USB devices:"
for d in /sys/bus/usb/devices/[0-9]*-*; do
	case $d in *:*) continue ;; esac
	echo "$(basename $d) $(cat $d/idVendor):$(cat $d/idProduct) bcd=$(cat $d/bcdDevice) cfgs=$(cat $d/bNumConfigurations) ifs=$(cat $d/bNumInterfaces 2>/dev/null) speed=$(cat $d/speed) $(cat $d/manufacturer 2>/dev/null) $(cat $d/product 2>/dev/null)"
done
for e in /sys/bus/usb/devices/*:1.0/ep_*; do
	[ -d "$e" ] && echo "  $e $(cat $e/type) $(cat $e/direction) max=$(cat $e/wMaxPacketSize)"
done

# Wi-Fi (88W8782 via patched mwifiex): firmware load and a PASSIVE scan
# only. No association: the credentials stay on the stock printer.
echo "--- Wi-Fi: waiting for mlan0"
i=0
while [ ! -e /sys/class/net/mlan0 ] && [ $i -lt 20 ]; do
	sleep 1
	i=$((i + 1))
done
iw dev
if [ -e /sys/class/net/mlan0 ]; then
	ifconfig mlan0 up
	echo "--- passive scan:"
	iw dev mlan0 scan passive | grep -E '^BSS|SSID:|signal:|freq:' | head -60
fi

# Webcam: one MJPEG frame into RAM (starts with ff d8 if it is a JPEG)
echo "--- webcam: $(ls /dev/video* 2>/dev/null)"
if [ -e /dev/video0 ]; then
	uvcgrab /dev/video0 /tmp/frame.jpg && hexdump -C /tmp/frame.jpg | head -2
fi
echo "=== shell on the console; type to test UART interrupts"
