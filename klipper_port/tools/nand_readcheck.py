# Read an MTD device page by page (corrected reads) and compare its md5
# with a known-good value (the stock kernel's dumps of 2026-10-26,
# nand_images/md5sums.txt). Prints time, read errors and md5 match.
# usage: python3 nand_readcheck.py DEV EXPECTED_MD5 [DEV MD5 ...]
import hashlib, os, sys, time

args = sys.argv[1:]
for dev, want in zip(args[0::2], args[1::2]):
    fd = os.open(dev, os.O_RDONLY)
    size = os.lseek(fd, 0, 2)
    h, err, t = hashlib.md5(), 0, time.time()
    for off in range(0, size, 2048):
        try:
            h.update(os.pread(fd, 2048, off))
        except OSError:
            err += 1
            h.update(b'?' * 2048)
    os.close(fd)
    got = h.hexdigest()
    print('CHECK %s %.1fs errors %d md5 %s %s' % (dev, time.time() - t, err,
          got[:8], 'OK' if got == want else 'MISMATCH (want %s)' % want[:8]),
          flush=True)
