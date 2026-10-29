"""Extract the decompressed vendor kernel (vmlinux "Image", linked at
0xc0008000) from a mtd0 dump or a uImage/zImage file.

    python -I tools/kernel_re/extract_image.py nand_images/mtd0.bin out/Image

mtd0 layout (docs/sd_boot_plan.md): boot table, signed U-Boot, then the
uImage at 0x40000. The zImage carries a gzip stream (CONFIG_KERNEL_GZIP);
the first gzip stream that inflates to > 1 MB is the kernel. Also writes
out/Image.initramfs.cpio if the embedded initramfs is found."""
import struct
import sys
import zlib

UIMAGE_MAGIC = 0x27051956


def find_uimage(d):
    for off in (0, 0x40000):
        if len(d) >= off + 64 and struct.unpack_from('>I', d, off)[0] == UIMAGE_MAGIC:
            size = struct.unpack_from('>I', d, off + 12)[0]
            name = d[off + 32:off + 64].split(b'\0')[0].decode(errors='replace')
            return off + 64, size, name
    return 0, len(d), None


def gunzip_at(buf, i):
    z = zlib.decompressobj(16 + zlib.MAX_WBITS)
    return z.decompress(buf[i:]), z.eof


def main():
    d = open(sys.argv[1], 'rb').read()
    start, size, name = find_uimage(d)
    z = d[start:start + size]
    print(f'uImage payload at 0x{start:x}, 0x{size:x} bytes, name {name!r}')
    i = 0
    while True:
        i = z.find(b'\x1f\x8b\x08', i)
        if i < 0:
            sys.exit('no kernel gzip stream found')
        try:
            img, done = gunzip_at(z, i)
        except zlib.error:
            i += 1
            continue
        if len(img) > 1 << 20:
            break
        i += 1
    print(f'gzip at zImage+0x{i:x} -> Image {len(img)} bytes (complete={done})')
    open(sys.argv[2], 'wb').write(img)
    # Embedded initramfs (CONFIG_INITRAMFS_COMPRESSION_GZIP): a gzip'd newc cpio.
    j = 0
    while True:
        j = img.find(b'\x1f\x8b\x08', j)
        if j < 0:
            break
        try:
            c, _ = gunzip_at(img, j)
        except zlib.error:
            j += 1
            continue
        if c.startswith(b'070701'):
            open(sys.argv[2] + '.initramfs.cpio', 'wb').write(c)
            print(f'initramfs cpio at Image+0x{j:x} ({len(c)} bytes)')
            break
        j += 1


if __name__ == '__main__':
    main()
