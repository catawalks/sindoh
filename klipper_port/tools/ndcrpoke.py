# Test-only: set or clear NDCR bits 14 / 23 of the NAND controller once,
# while it is idle (like the vendor's probe-time value). Register write
# only; no NAND command. usage: ndcrpoke.py VALUE_OF_BITS (e.g. 0x800000)
import mmap, os, struct, sys
ALLOWED = (1 << 14) | (1 << 23)
want = int(sys.argv[1], 0)
assert want & ~ALLOWED == 0, 'only bits 14 and 23'
fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0xf9082000)
old = struct.unpack('<I', m[0:4])[0]
assert not old & (1 << 28), 'controller running (ND_RUN): not touching it'
new = (old & ~ALLOWED) | want
m[0:4] = struct.pack('<I', new)
print('NDCR %08x -> %08x (now %08x)' % (old, new, struct.unpack('<I', m[0:4])[0]))
