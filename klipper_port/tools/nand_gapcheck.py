# Read-only: random pages of an MTD device with random pauses between the
# reads (0-30 ms), each compared with a known-good copy of the partition.
# Catches reads whose data is shifted by stale FIFO bytes after an idle gap
# (2026-11-01), which sequential passes can hide.
#   nand_gapcheck.py DEV REFERENCE_FILE READS
import os, random, sys, time

dev, ref, n = sys.argv[1], open(sys.argv[2], 'rb').read(), int(sys.argv[3])
fd = os.open(dev, os.O_RDONLY)
pages = min(os.lseek(fd, 0, 2), len(ref)) // 2048
rnd = random.Random(20261101)
bad, errs, t = [], 0, time.time()
for i in range(n):
    p = rnd.randrange(pages)
    time.sleep(rnd.choice((0, 0, 0.001, 0.005, 0.03)))
    try:
        d = os.pread(fd, 2048, p * 2048)
    except OSError:
        errs += 1
        continue
    if d != ref[p * 2048:(p + 1) * 2048]:
        bad.append(p)
print('GAP %s reads %d wrong %d errors %d %.0fs first wrong: %s' % (
    dev, n, len(bad), errs, time.time() - t, bad[:10]), flush=True)
