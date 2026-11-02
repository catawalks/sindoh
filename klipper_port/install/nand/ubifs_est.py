# Estimate UBIFS zlib usage of the files in a GNU tar -tvv listing: each
# file is stored as 4 KiB blocks, each zlib-compressed on its own (kept raw
# when that doesn't help), plus ~ node headers. Run in the chroot: python3 -I ubifs_est.py LIST
import os, sys, zlib
raw = comp = n = 0
for line in open(sys.argv[1]):
    f = line.split()
    if not f or f[0][0] != '-':
        n += 1
        continue
    path = line.split(None, 5)[5].rstrip('\n')[1:]
    n += 1
    try:
        with open(path, 'rb') as fh:
            while True:
                b = fh.read(4096)
                if not b:
                    break
                raw += len(b)
                c = len(zlib.compress(b, 6))
                comp += min(c, len(b)) + 48      # data node header
    except OSError:
        pass
meta = n * 400                                   # inode + dentry nodes, index share
print('files+dirs %d  raw %d MB  zlib-4k %d MB  +meta %d MB  = %d MB'
      % (n, raw >> 20, comp >> 20, meta >> 20, (comp + meta) >> 20))
