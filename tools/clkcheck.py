"""Check timer_read_time continuity across Timer1 reloads: run kemu's setup, then poll get_clock.
usage: clkcheck.py KLIPPER_TREE klipper.bin fm|io N"""
import os, sys, runpy
N = int(sys.argv.pop())
sys.argv = [sys.argv[0]] + sys.argv[1:]
src = open(os.path.join(os.path.dirname(__file__), 'kemu.py'), encoding='utf-8-sig').read()
# Execute kemu up to (not including) the identify phase, then poll clocks
src = src.split('# Identify: fetch the compressed data dictionary')[0]
g = {'__name__': 'kemu', '__file__': __file__}
exec(compile(src, 'kemu.py', 'exec'), g)
data = b''
while True:
    r = g['transact']('identify offset=%d count=40' % len(data), 'identify_response')
    if not r['data']:
        break
    data += bytes(r['data'])
g['parser'].process_identify(data)
prev = None; reloads = 0; last_t1 = None; bad = 0
for i in range(N):
    g['run'](200000)
    c = g['transact']('get_clock', 'clock')['clock']
    t1 = g['state'].get('t1', 0)
    if last_t1 is not None and t1 > last_t1:
        reloads += 1
    last_t1 = t1
    if prev is not None:
        d = (c - prev) & 0xffffffff
        if d == 0 or d > 0x80000000:
            bad += 1
            print('NON-MONOTONIC at sample %d: %#x -> %#x (t1 %#x)' % (i, prev, c, t1))
    prev = c
print('samples %d, timer1 reloads seen %d, non-monotonic %d, final clock %#x' % (N, reloads, bad, prev))
