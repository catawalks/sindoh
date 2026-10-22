#!/usr/bin/env python3
"""Read physical memory through mmap of /dev/mem, 4 KiB at a time (read only).
Usage: memdump.py ADDR LENGTH OUTFILE   (stops early if a page faults)."""
import mmap, os, sys

addr, length, out = int(sys.argv[1], 0), int(sys.argv[2], 0), sys.argv[3]
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
with open(out, 'wb') as f:
    for off in range(0, length, 4096):
        m = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=addr + off)
        page = m[:]
        m.close()
        f.write(page); f.flush(); os.fsync(f.fileno())
        print('%08x ok' % (addr + off), flush=True)
