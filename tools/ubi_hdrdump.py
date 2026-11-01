# Read-only: the UBI header pages (page 0 = EC header, page 1 = VID header)
# of every block of an MTD device, as the running kernel reads them
# (corrected reads). Writes them to OUT (2 x 2048 bytes per block) and
# prints how many are erased (all 0xff) or failed to read.
#   ubi_hdrdump.py DEV OUT
#   ubi_hdrdump.py --compare A B     (block numbers whose headers differ)
import os, sys

if sys.argv[1] == '--compare':
    a, b = (open(p, 'rb').read() for p in sys.argv[2:4])
    diff = [i for i in range(min(len(a), len(b)) // 4096)
            if a[i * 4096:(i + 1) * 4096] != b[i * 4096:(i + 1) * 4096]]
    print('COMPARE blocks %d, differing %d: %s' % (len(a) // 4096, len(diff),
                                                    diff[:40]))
    for i in diff[:8]:
        for pg in (0, 1):
            x = a[i * 4096 + pg * 2048:i * 4096 + pg * 2048 + 2048]
            y = b[i * 4096 + pg * 2048:i * 4096 + pg * 2048 + 2048]
            if x != y:
                print('  block %d page %d: A %s%s  B %s%s' % (
                    i, pg, x[:16].hex(), ' (all ff)' if x.count(255) == 2048 else '',
                    y[:16].hex(), ' (all ff)' if y.count(255) == 2048 else ''))
    sys.exit(0)

dev, out = sys.argv[1], sys.argv[2]
fd = os.open(dev, os.O_RDONLY)
size = os.lseek(fd, 0, 2)
erased = [0, 0]
fails = 0
with open(out, 'wb') as f:
    for blk in range(size // 131072):
        for pg in (0, 1):
            try:
                d = os.pread(fd, 2048, blk * 131072 + pg * 2048)
            except OSError:
                fails += 1
                d = b'?' * 2048
            if d.count(255) == 2048:
                erased[pg] += 1
            f.write(d)
print('HDR %s blocks %d erased EC %d VID %d failed %d' % (
    dev, size // 131072, erased[0], erased[1], fails))
