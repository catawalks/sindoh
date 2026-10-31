#!/usr/bin/python3
"""NAND write path, stage 3 (owner-approved 2026-10-31): one free UBI PEB
of the stock root (mtd6), on the mainline test kernel (m1-debian-nandw,
patch 0010). Runs on the printer as root; stops at the first unexpected
result and closes the write window on any exit.

  1. save the block (per page: ECC data, raw data, raw OOB) to SAVE
  2. guard: window closed, erase BLOCK -> refused, block unchanged
  3. guard: window = BLOCK only, erase BLOCK-1 -> refused, unchanged
  4. erase BLOCK, check it reads erased
  5. program test pages, read them back (ECC and raw: data, "programz",
     ECC bytes), erase again
  6. program the saved non-erased pages back (the UBI EC header): the
     block must read back identical to the saved copy, raw OOB included,
     i.e. our BCH bytes equal the stock driver's
  7. close the window

    python3 nand_write_test.py [BLOCK]     (default 4084)
    python3 nand_write_test.py --verify [BLOCK]   (read-only: block vs saved copy)
"""
import ctypes
import fcntl
import os
import random
import struct
import sys

MTD = '/dev/mtd6'
FIRST = 0xd9a0000 // 0x20000
PAGE, OOB, PPB = 2048, 64, 64
OOB_READ = 62    # spare 32 + ECC 30: the controller never fills bytes 62-63
WINDOW = '/sys/module/marvell_nand/parameters/write_window'
MEMERASE = 0x40084d02             # _IOW('M', 2, struct erase_info_user)
MEMREADOOB = 0xc00c4d04           # _IOWR('M', 4, struct mtd_oob_buf)
MEMGETBADBLOCK = 0x40084d0b
MTDFILEMODE = 0x4d13
RAW = 3


class Fail(Exception):
    pass


def window(val):
    with open(WINDOW, 'w') as f:
        f.write(val)
    got = open(WINDOW).read().strip()
    if got != val:
        raise Fail('window is %r, wanted %r' % (got, val))


def pos(block, page=0):
    return ((block - FIRST) * PPB + page) * PAGE


def read_page(fd, block, page, raw=False):
    if raw:
        fcntl.ioctl(fd, MTDFILEMODE, RAW)
    try:
        return os.pread(fd, PAGE, pos(block, page))
    finally:
        if raw:
            fcntl.ioctl(fd, MTDFILEMODE, 0)


def read_oob(fd, block, page):
    buf = ctypes.create_string_buffer(OOB)
    fcntl.ioctl(fd, MEMREADOOB, struct.pack('III', pos(block, page), OOB,
                                            ctypes.addressof(buf)))
    return buf.raw


def snapshot(fd, block):
    return [(read_page(fd, block, p), read_page(fd, block, p, True),
             read_oob(fd, block, p)) for p in range(PPB)]


def erase(fd, block):
    fcntl.ioctl(fd, MEMERASE, struct.pack('II', pos(block), PPB * PAGE))


def program(fd, block, page, data):
    n = os.pwrite(fd, data, pos(block, page))
    if n != PAGE:
        raise Fail('short write %d' % n)


def expect_refused(fd, block, what):
    before = snapshot(fd, block)
    try:
        erase(fd, block)
    except OSError as e:
        print('  %s: erase refused (%s)' % (what, e.strerror))
    else:
        raise Fail('%s: erase was NOT refused' % what)
    # the refused command never reached the controller, which still waits
    # for it: the next command clears that (and may fail itself)
    for _ in range(2):
        try:
            read_page(fd, block, 0)
            break
        except OSError as e:
            print('  read after the refusal: %s (controller reset)' % e.strerror)
    if snapshot(fd, block) != before:
        raise Fail('%s: block %d changed' % (what, block))
    print('  %s: block %d unchanged' % (what, block))


def is_erased(snap):
    return all(d == b'\xff' * PAGE and r == b'\xff' * PAGE and
               o[:OOB_READ] == b'\xff' * OOB_READ for d, r, o in snap)


def main():
    block = int(sys.argv[1]) if len(sys.argv) > 1 else 4084
    save = '/var/backups/nand_block%d.bin' % block
    if open(WINDOW).read().strip() != 'none':
        raise Fail('window not closed at start')
    fd = os.open(MTD, os.O_RDWR | os.O_SYNC)
    bad = ctypes.c_longlong(pos(block))
    if fcntl.ioctl(fd, MEMGETBADBLOCK, bad):
        raise Fail('block %d is marked bad' % block)

    # 1. save (or, after an interrupted run, the copy saved by the first one)
    if os.path.exists(save):
        raw = open(save, 'rb').read()
        n = 2 * PAGE + OOB
        orig = [(raw[i:i + PAGE], raw[i + PAGE:i + 2 * PAGE], raw[i + 2 * PAGE:i + n])
                for i in range(0, PPB * n, n)]
        print('1. using the copy saved before: %s' % save)
    else:
        orig = snapshot(fd, block)
        with open(save, 'wb') as f:
            for d, r, o in orig:
                f.write(d + r + o)
    used = [p for p, (d, r, o) in enumerate(orig)
            if r != b'\xff' * PAGE or o[:OOB_READ] != b'\xff' * OOB_READ]
    print('1. saved %s; programmed pages %s; page 0 starts %r' % (save, used, orig[0][0][:4]))
    if orig[0][0][:4] != b'UBI#' or used != [0]:
        raise Fail('not a free UBI PEB (EC header only)')
    o = orig[0][2]
    print('   page 0 OOB: spare %s marker %r ecc %s' % (o[:24].hex(), o[24:32], o[32:62].hex()))

    # 2./3. the guard
    print('2. window closed')
    expect_refused(fd, block, 'closed window')
    print('3. window %d,%d' % (block, block))
    window('%d,%d' % (block, block))
    expect_refused(fd, block - 1, 'outside the window')

    # 4. erase
    erase(fd, block)
    if not is_erased(snapshot(fd, block)):
        raise Fail('block not erased')
    print('4. erased, reads 0xff (ECC, raw, OOB)')

    # 5. test pages
    rnd = random.Random(4084)
    pages = {p: bytes(rnd.getrandbits(8) for _ in range(PAGE)) for p in (0, 1, 31, 63)}
    for p, data in pages.items():
        program(fd, block, p, data)
    for p, data in pages.items():
        d, r = read_page(fd, block, p), read_page(fd, block, p, True)
        o = read_oob(fd, block, p)
        if d != data:
            raise Fail('page %d: ECC read differs' % p)
        flips = sum(bin(a ^ b).count('1') for a, b in zip(r, data))
        if o[:24] != b'\xff' * 24 or o[24:32] != b'programz' or o[32:62] == b'\xff' * 30:
            raise Fail('page %d: OOB %s' % (p, o.hex()))
        print('5. page %2d: ECC read equal, raw bitflips %d, OOB marker %r, ECC %s...' % (
            p, flips, o[24:32], o[32:40].hex()))
    erase(fd, block)
    if not is_erased(snapshot(fd, block)):
        raise Fail('block not erased (2nd)')

    # 6. restore
    for p in used:
        program(fd, block, p, orig[p][0])
    compare(snapshot(fd, block), orig, 'after restore')
    print('6. restored: all 64 pages identical to the saved copy (ECC data, raw data, raw OOB 0-61)')
    os.close(fd)


def compare(now, orig, what):
    """Pages equal: ECC data, raw data and the OOB bytes the controller fills."""
    for p in range(PPB):
        d, r, o = now[p]
        if d != orig[p][0] or r != orig[p][1] or o[:OOB_READ] != orig[p][2][:OOB_READ]:
            raise Fail('page %d differs %s: ECC %s raw %s OOB %s vs %s' % (
                p, what, d == orig[p][0], r == orig[p][1], o[:OOB_READ].hex(),
                orig[p][2][:OOB_READ].hex()))


def verify(block):
    """Read-only: the block against the copy saved by the first run."""
    save = '/var/backups/nand_block%d.bin' % block
    raw = open(save, 'rb').read()
    n = 2 * PAGE + OOB
    orig = [(raw[i:i + PAGE], raw[i + PAGE:i + 2 * PAGE], raw[i + 2 * PAGE:i + n])
            for i in range(0, PPB * n, n)]
    fd = os.open(MTD, os.O_RDONLY)
    compare(snapshot(fd, block), orig, 'from the saved copy')
    os.close(fd)
    print('verify: block %d equals %s (ECC data, raw data, raw OOB 0-61)' % (block, save))


if sys.argv[1:2] == ['--verify']:
    try:
        verify(int(sys.argv[2]) if len(sys.argv) > 2 else 4084)
        sys.exit(0)
    except Fail as e:
        print('FAIL:', e)
        sys.exit(1)

try:
    main()
    ok = True
except Fail as e:
    print('FAIL:', e)
    ok = False
finally:
    try:
        window('none')
        print('7. window closed:', open(WINDOW).read().strip())
    except Exception as e:      # noqa: BLE001
        print('could not close the window:', e)
sys.exit(0 if ok else 1)
