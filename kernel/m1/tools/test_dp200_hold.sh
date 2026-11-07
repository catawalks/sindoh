#!/bin/sh
# Offline test of tools/dp200-hold.c: built for the PC, fed input events
# through a FIFO (the PC's struct input_event layout, from the same
# headers). Run in WSL: sh tools/test_dp200_hold.sh
M1=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
gcc -O2 -Wall -o "$T/hold" "$M1/tools/dp200-hold.c" || exit 1
python3 - "$T" <<'EOF'
import os, struct, subprocess, sys, time
T = sys.argv[1]
EV = 'llHHi'            # timeval, type, code, value (native)
def ev(t, c, v): return struct.pack(EV, 0, 0, t, c, v)
SYN = ev(0, 0, 0)
def frame(x=100, y=200):              # one touch sample, as bu21029 sends it
    return ev(3, 0x35, x) + ev(3, 0x36, y) + SYN
LIFT = SYN                             # an empty frame: lifted
def held_for(t0, secs, step=0.05):     # samples every 50 ms for secs
    return [(t0 + i * step, frame()) for i in range(int(secs / step))]
def case(name, queued, script, want):
    f = os.path.join(T, 'ev'); os.path.exists(f) and os.remove(f); os.mkfifo(f)
    fd = os.open(f, os.O_RDWR)          # keeps a writer: no POLLHUP
    os.write(fd, queued)
    p = subprocess.Popen([os.path.join(T, 'hold'), f, '3', '2'],
                         stdout=subprocess.PIPE, text=True)
    t0 = time.time()
    for at, data in script:
        time.sleep(max(0, at - (time.time() - t0)))
        os.write(fd, data)
    out, _ = p.communicate(timeout=15)
    os.close(fd)
    res = 'held' if p.returncode == 0 else 'no' if p.returncode == 1 else 'error'
    print('%-40s %-5s %s' % (name, res, 'ok' if res == want else 'FAIL'))
    return res == want
ok = all([
    case('no touch', b'', [], 'no'),
    case('queued frames (2026-11-07) are not a touch', frame() * 3, [], 'no'),
    case('queued, then frames inside the drain', frame() * 3, held_for(0.0, 0.4), 'no'),
    case('one-frame glitch', b'', [(1.0, frame()), (1.05, LIFT)], 'no'),
    case('fresh press held 2 s', b'', held_for(1.0, 2.3), 'held'),
    case('released (empty frame) after 1 s', b'', held_for(1.0, 1.0) + [(2.05, LIFT)], 'no'),
    case('released (silence) after 1 s', b'', held_for(1.0, 1.0), 'no'),
    case('BTN_TOUCH 0 releases', b'', held_for(1.0, 1.0) + [(2.05, ev(1, 330, 0) + SYN)], 'no'),
    case('phantom samples streaming all along', b'', held_for(0.0, 4.0), 'no'),
    case('finger already down, then lifted, then held', b'', held_for(0.0, 1.2) + held_for(1.6, 2.3), 'held'),
    case('tap, then a held press', b'', held_for(0.8, 0.3) + [(1.15, LIFT)] + held_for(1.4, 2.3), 'held'),
])
print('all ok' if ok else 'FAILURES')
sys.exit(0 if ok else 1)
EOF
