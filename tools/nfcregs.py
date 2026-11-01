# Read-only dump of the NAND controller registers (0xf9082000, 0x00-0x7c).
# NEVER reads +0x40 (NDDB, the data FIFO): a read there takes a word out of
# the FIFO, and every later page read was then shifted by 4 bytes
# (2026-11-01: this tool caused the "ramz"/0xff-shifted reads, the UBI
# "layout volume not found" and every second-run mismatch that day).
import mmap, os, struct
NDDB = 0x40
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0xf9082000)
for o in range(0, 0x80, 4):
    if o == NDDB:
        print('NFC +%02x = (NDDB, not read)' % o)
        continue
    print('NFC +%02x = %08x' % (o, struct.unpack('<I', m[o:o + 4])[0]))
