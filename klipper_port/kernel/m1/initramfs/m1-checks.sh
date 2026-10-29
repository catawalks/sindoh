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
echo "=== shell on the console; type to test UART interrupts"
