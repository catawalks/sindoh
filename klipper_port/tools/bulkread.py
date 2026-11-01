# read an mtd device page by page (corrected reads), N passes; print the
# pages that returned an ECC error in each pass
import os, sys, time
dev, passes = sys.argv[1], int(sys.argv[2])
first = int(sys.argv[3]) if len(sys.argv) > 3 else 0   # chip page of offset 0
fd = os.open(dev, os.O_RDONLY)
size = os.lseek(fd, 0, 2)
for r in range(passes):
    bad, t = [], time.time()
    for off in range(0, size, 2048):
        try:
            os.pread(fd, 2048, off)
        except OSError:
            bad.append(first + off // 2048)
    print('PASS', r + 1, 'errors', len(bad), '%.0fs' % (time.time() - t), bad[:15], flush=True)
