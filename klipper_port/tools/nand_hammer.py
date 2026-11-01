# back-to-back reads of chip pages of /dev/mtd5 (hash afterwards)
import os, sys, hashlib, collections
fd = os.open('/dev/mtd5', os.O_RDONLY)
n = int(sys.argv[1])
for p in map(int, sys.argv[2:]):
    got, err = [], 0
    for i in range(n):
        try:
            got.append(os.pread(fd, 2048, (p - 9024) * 2048))
        except OSError:
            err += 1
    c = collections.Counter(hashlib.md5(d).hexdigest()[:8] for d in got)
    print('H3', p, 'err', err, dict(c), flush=True)
