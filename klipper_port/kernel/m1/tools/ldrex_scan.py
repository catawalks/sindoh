"""Count LDREX sites in an ARM kernel image: single ones vs runs of 5
(the vendor's PJ4B erratum 6011 form), and the cache-op wrapper
(cpsid i; dsb; mov r3,#0x32; subs; bne). Args: image [System.map]."""
import bisect
import collections
import struct
import sys

img = open(sys.argv[1], 'rb').read()
BASE = 0xc0008000
syms = []
if len(sys.argv) > 2:
    for line in open(sys.argv[2]):
        a, t, n = line.split()[:3]
        if t in 'tTwW':
            syms.append((int(a, 16), n))
    syms.sort()
addrs = [a for a, _ in syms]


def name(va):
    j = bisect.bisect_right(addrs, va) - 1
    return syms[j][1] if j >= 0 else '?'


words = struct.unpack('<%dI' % (len(img) // 4), img[:len(img) // 4 * 4])
runs = collections.Counter()
single_funcs = collections.Counter()
i = 0
n = len(words)
while i < n:
    w = words[i]
    # LDREX/LDREXD/LDREXB/LDREXH, any condition
    if (w & 0x0f900fff) == 0x01900f9f:
        j = i
        while j < n and (words[j] & 0x0f900fff) == 0x01900f9f:
            j += 1
        runs[j - i] += 1
        if j - i == 1 and syms:
            single_funcs[name(BASE + 4 * i)] += 1
        i = j
    else:
        i += 1
print('LDREX runs by length:', dict(sorted(runs.items())))
if syms:
    print('functions with a single LDREX (top 25):')
    for f, c in single_funcs.most_common(25):
        print(f'  {c:3d} {f}')
# cpsid i (0xf10c0080) followed by dsb sy (0xf57ff04f), mov r3,#0x32 (0xe3a03032)
wrap = 0
for k in range(n - 2):
    if words[k] == 0xf10c0080 and words[k + 1] == 0xf57ff04f and words[k + 2] == 0xe3a03032:
        wrap += 1
        if syms:
            print('  wrapper in', name(BASE + 4 * k))
print('cache-op wrappers:', wrap)
