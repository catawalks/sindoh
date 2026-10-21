"""Extract IKCONFIG from a uImage/zImage inside a NAND image. usage: ikconfig.py image out.config"""
import sys, zlib, gzip
data = open(sys.argv[1], 'rb').read()
# Find gzip streams; decompress each, look for IKCFG_ST marker (possibly nested in the kernel).
def scan(buf, depth=0):
    i = 0
    while True:
        i = buf.find(b'\x1f\x8b\x08', i)
        if i < 0 or depth > 2:
            return None
        try:
            d = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(buf[i:i + 0x2000000])
        except Exception:
            i += 1
            continue
        if b'IKCFG_ST' in d:
            j = d.find(b'IKCFG_ST') + 8
            return gzip.decompress(d[j:d.find(b'IKCFG_ED', j)])
        if len(d) > 1000000:
            r = scan(d, depth + 1)
            if r:
                return r
        i += 1
cfg = scan(data[:0x1000000])
open(sys.argv[2], 'wb').write(cfg)
print(len(cfg))
