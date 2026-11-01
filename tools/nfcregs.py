# read-only dump of the NAND controller registers (0xf9082000, 0x00-0x7c)
import mmap, os, struct
fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=0xf9082000)
for o in range(0, 0x80, 4):
    print('NFC +%02x = %08x' % (o, struct.unpack('<I', m[o:o + 4])[0]))
