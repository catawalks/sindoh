"""Grab the DP200 panel framebuffer (RGB565 LE, 800x480) and save it as PNG.
On the printer first:  (head -c 768000 /dev/fb0 | nc -l -p 9002 &)
Then:                  python -I tools/fb_grab.py 10.10.0.21 out.png
No Pillow needed."""
import socket, struct, sys, zlib

W, H = 800, 480

def main():
    host, out = sys.argv[1], sys.argv[2]
    s = socket.create_connection((host, 9002), timeout=10)
    b = bytearray()
    while len(b) < W * H * 2:
        d = s.recv(65536)
        if not d:
            break
        b += d
    if len(b) < W * H * 2:
        sys.exit('short read: %d bytes' % len(b))
    # The panel is mounted in portrait: save 480x800 as the user sees it
    # (portrait pixel (u, v) = fb pixel (x = 799 - v, y = u)).
    rows = bytearray()
    for v_ in range(W):
        rows.append(0)
        for u in range(H):
            i = u * W + (W - 1 - v_)
            v = b[2 * i] | (b[2 * i + 1] << 8)
            r, g, bl = (v >> 11) & 31, (v >> 5) & 63, v & 31
            rows += bytes(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (bl << 3) | (bl >> 2)))

    def chunk(t, data):
        c = struct.pack('>I', len(data)) + t + data
        return c + struct.pack('>I', zlib.crc32(t + data) & 0xffffffff)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', H, W, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b''))
    with open(out, 'wb') as f:
        f.write(png)
    print('saved', out)

main()
