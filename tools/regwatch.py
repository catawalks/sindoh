#!/usr/bin/env python3
"""Watch physical register words for changes (read only), to find an input.

Usage: regwatch.py SECONDS LEARN_SECONDS BASE:LEN [BASE:LEN ...]
Polls every 20 ms. Bits that change during the first LEARN_SECONDS are
treated as noise and ignored (other bits of the same word are still
watched); after that every other change is printed with a timestamp.
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
noise = {}                     # address -> bits that changed while learning
print('watching %d words; learning noise for %.0f s' % (len(prev), learn), flush=True)
announced = False
while time.time() - t0 < secs:
    time.sleep(0.02)
    cur = snap()
    t = time.time() - t0
    for a, v in cur.items():
        bits = (v ^ prev[a]) & ~noise.get(a, 0)
        if bits:
            if t < learn:
                noise[a] = noise.get(a, 0) | bits
            else:
                print('%7.2f %08x: %08x -> %08x (bits %08x)' % (t, a, prev[a], v, bits), flush=True)
    if t >= learn and not announced:
        announced = True
        for a in sorted(noise):
            print('noisy %08x bits %08x (ignored)' % (a, noise[a]), flush=True)
        print('learned noise in %d words; press now' % len(noise), flush=True)
    prev = cur
