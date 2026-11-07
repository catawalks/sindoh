#!/usr/bin/env python3
# pcs_dump.py [PHYS]: print the PC samples (patch 0017) left in RAM by the
# boot before, from any kernel that leaves the page alone (nanddbg maps only
# the first 4 KB of 0x1e100000; the samples are in the page after it).
# Needs root and /dev/mem without STRICT_DEVMEM (our builds). Read-only.
# Resolve the PCs with the System.map of the kernel that wrote them
# (e.g. m1-nandboot-nandpcs-System.map): python3 -I pcs_dump.py | ...
import mmap
import os
import struct
import sys

PHYS = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x1e101000
MAGIC, CPUS, N = 0x3153434e, 2, 60
ENT = 32  # seq us jif pc lr sp cpsr pad

fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=PHYS)
magic, boot = struct.unpack_from("<II", m, 0)
if magic != MAGIC:
    sys.exit("no samples at %#x (magic %#x)" % (PHYS, magic))
print("samples of boot %u" % boot)
for cpu in range(CPUS):
    ents = []
    for i in range(N):
        e = struct.unpack_from("<8I", m, 64 + (cpu * N + i) * ENT)
        if e[0]:
            ents.append(e)
    ents.sort()
    for seq, us, jif, pc, lr, sp, cpsr, _ in ents[-10:]:
        print("cpu%u #%u %u us jif %08x pc %08x lr %08x sp %08x cpsr %08x mode %02x"
              % (cpu, seq, us, jif, pc, lr, sp, cpsr, cpsr & 0x1f))
