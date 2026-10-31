#!/usr/bin/python3
"""Read-only NAND bad-block check for the DP200 (runs on the printer, mainline
kernel). For the given erase blocks of the whole chip: the factory bad-block
marker (OOB byte 0 of pages 0 and 1, read raw) and what the kernel's BBT says
(MEMGETBADBLOCK). Then the vendor BBT's main and mirror tables (last two
blocks), read with ECC and raw, decoded (2 bits per block, 11 = good).
Nothing is written.

    python3 nand_bbt_check.py [BLOCK ...]
"""
import ctypes
import fcntl
import os
import struct
import sys

MTD = '/dev/mtd6'                 # "filesystem": to the end of the chip
FIRST = 0xd9a0000 // 0x20000      # its first block
PAGE, OOB, PPB, NBLK = 2048, 64, 64, 4096
MEMGETBADBLOCK = 0x40084d0b       # _IOW('M', 11, loff_t)
MEMREADOOB = 0xc00c4d04           # _IOWR('M', 4, struct mtd_oob_buf)
MTDFILEMODE = 0x4d13              # _IO('M', 19)
MTD_FILE_MODE_RAW = 3


def oob(fd, page):
    buf = ctypes.create_string_buffer(OOB)
    req = struct.pack('III', (page - FIRST * PPB) * PAGE, OOB, ctypes.addressof(buf))
    fcntl.ioctl(fd, MEMREADOOB, req)
    return buf.raw


def isbad(fd, block):
    # a writable buffer: fcntl.ioctl then returns the ioctl's result, 1 = bad
    arg = ctypes.c_longlong((block - FIRST) * PPB * PAGE)
    return fcntl.ioctl(fd, MEMGETBADBLOCK, arg)


def table(data):
    return [b for b in range(NBLK) if (data[b // 4] >> ((b % 4) * 2)) & 3 != 3]


def main():
    blocks = [int(a) for a in sys.argv[1:]] or [3404, 3497]
    fd = os.open(MTD, os.O_RDONLY)
    for b in blocks:
        marks = [oob(fd, b * PPB + p)[:2].hex() for p in (0, 1)]
        print('block %d: marker pages 0/1 %s, kernel BBT %s' % (
            b, marks, 'BAD' if isbad(fd, b) else 'good'))
    for b, name in ((NBLK - 1, 'main'), (NBLK - 2, 'mirror')):
        o = oob(fd, b * PPB)
        os.lseek(fd, (b - FIRST) * PPB * PAGE, 0)
        ecc = os.read(fd, 1024)
        fcntl.ioctl(fd, MTDFILEMODE, MTD_FILE_MODE_RAW)
        os.lseek(fd, (b - FIRST) * PPB * PAGE, 0)
        raw = os.read(fd, 1024)
        fcntl.ioctl(fd, MTDFILEMODE, 0)
        print('%s (block %d): pattern %r version %d; ECC read lists %s, raw read lists %s' % (
            name, b, o[20:23], o[23], table(ecc), table(raw)))
    os.close(fd)


if __name__ == '__main__':
    main()
