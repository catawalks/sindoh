#!/usr/bin/env python3
"""Watch physical register words for changes (read only), to find an input.

Usage: regwatch.py SECONDS LEARN_SECONDS BASE:LEN [BASE:LEN ...]
Polls every 20 ms. Words that change during the first LEARN_SECONDS are
treated as noise and ignored; after that every change of any other word is
printed with a timestamp and the changed bits.
"""
import mmap, os, struct, sys, time

secs, learn = float(sys.argv[1]), float(sys.argv[2])
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
regions = []
for spec in sys.argv[3:]:
    base, length = (int(v, 0) for v in spec.split(':'))
    page = base & ~0xfff
    m = mmap.mmap(fd, (base - page + length + 0xfff) & ~0xfff, mmap.MAP_SHARED,
                  mmap.PROT_READ, offset=page)
    regions.append((base, base - page, length, m))


def snap():
    out = {}
    for base, off, length, m in regions:
        for i in range(0, length, 4):
            out[base + i] = struct.unpack_from('<I', m, off + i)[0]
    return out


t0 = time.time()
prev = snap()
noisy = set()
print('watching %d words; learning noise for %.0f s' % (len(prev), learn), flush=True)
while time.time() - t0 < secs:
    time.sleep(0.02)
    cur = snap()
    t = time.time() - t0
    for a, v in cur.items():
        if v != prev[a]:
            if t < learn:
                noisy.add(a)
            elif a not in noisy:
                print('%7.2f %08x: %08x -> %08x (bits %08x)' % (t, a, prev[a], v, prev[a] ^ v), flush=True)
    if learn <= t < learn + 0.03:
        print('learned %d noisy words; press now' % len(noisy), flush=True)
    prev = cur
