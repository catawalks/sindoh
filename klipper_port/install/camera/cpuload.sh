#!/bin/sh
# CPU load sampler for the stock BusyBox side (2 cores, HZ=100).
#   sh cpuload.sh SECONDS [process-name ...]
# Prints total CPU busy % (of both cores together) and each process's CPU %
# of ONE core (100 = one core fully used) over the interval.
T=${1:-20}; shift
NAMES=${*:-ustreamer python3 nginx}
cpu() { awk '/^cpu /{busy=$2+$3+$4+$7+$8; total=busy+$5+$6; print busy, total}' /proc/stat; }
ptime() {   # utime+stime of all pids with that comm, in ticks
    s=0
    for p in $(pidof "$1"); do
        t=$(awk '{print $14+$15}' /proc/$p/stat 2>/dev/null); s=$((s + ${t:-0}))
    done
    echo $s
}
set -- $(cpu); B0=$1; T0=$2
for n in $NAMES; do eval "P0_$(echo $n | tr -c 'a-zA-Z0-9\n' _)=$(ptime $n)"; done
sleep $T
set -- $(cpu); B1=$1; T1=$2
echo "total CPU busy: $(( 100 * (B1 - B0) / (T1 - T0) ))% of 2 cores"
for n in $NAMES; do
    v=$(echo $n | tr -c 'a-zA-Z0-9\n' _)
    eval "p0=\$P0_$v"; p1=$(ptime $n)
    echo "  $n: $(( (p1 - p0) * 100 / (T * 100) ))% of one core"
done
free | awk '/Mem/{printf "  RAM used %d MB of %d MB\n", $3/1024, $2/1024}'
