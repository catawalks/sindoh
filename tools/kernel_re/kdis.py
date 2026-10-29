"""Disassemble vendor-kernel functions by name, using the System.map from
kallsyms.py. Literal-pool loads are annotated with the value and the
symbol or string it points to; MOVW/MOVT pairs are folded.

    python -I tools/kernel_re/kdis.py Image System.map func [func...]
    python -I tools/kernel_re/kdis.py Image System.map 0xc001e25c:0x100

Needs capstone. With python -I, point KRE_PYLIB at a pip --target dir."""
import bisect
import os
import struct
import sys

if os.environ.get('KRE_PYLIB'):
    sys.path.insert(0, os.environ['KRE_PYLIB'])
from capstone import CS_ARCH_ARM, CS_MODE_ARM, Cs  # noqa: E402
from capstone.arm import ARM_OP_MEM, ARM_REG_PC  # noqa: E402

BASE = 0xc0008000


def load_map(path):
    syms = []
    for line in open(path):
        a, t, n = line.split()[:3]
        syms.append((int(a, 16), n))
    syms.sort()
    return syms


def symname(syms, addrs, v):
    i = bisect.bisect_right(addrs, v) - 1
    if i < 0 or v - syms[i][0] > 0x4000:
        return None
    a, n = syms[i]
    return n if v == a else f'{n}+0x{v - a:x}'


def cstring(img, v):
    o = v - BASE
    if not 0 <= o < len(img):
        return None
    e = img.find(b'\0', o, o + 120)
    s = img[o:e] if e > o else b''
    if len(s) >= 3 and all(32 <= c < 127 or c in (9, 10) for c in s):
        return s.decode()
    return None


def describe(img, syms, addrs, v):
    s = cstring(img, v)
    if s is not None:
        return repr(s)
    n = symname(syms, addrs, v) if 0xbf000000 <= v < 0xc1000000 else None
    return n or ''


def dis(img, syms, addrs, start, size):
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    md.detail = True
    o = start - BASE
    movw = {}
    for i in md.disasm(img[o:o + size], start):
        note = ''
        if i.mnemonic.startswith('ldr') and len(i.operands) == 2:
            m = i.operands[1]
            if m.type == ARM_OP_MEM and m.mem.base == ARM_REG_PC and m.mem.index == 0:
                lit = i.address + 8 + m.mem.disp
                lo = lit - BASE
                if 0 <= lo < len(img) - 4:
                    v = struct.unpack_from('<I', img, lo)[0]
                    note = f'=0x{v:08x} {describe(img, syms, addrs, v)}'
        elif i.mnemonic.startswith('movw'):
            movw[i.op_str.split(',')[0]] = i.operands[1].imm & 0xffff
        elif i.mnemonic.startswith('movt'):
            r = i.op_str.split(',')[0]
            if r in movw:
                v = (i.operands[1].imm << 16) | movw[r]
                note = f'=0x{v:08x} {describe(img, syms, addrs, v)}'
        elif i.mnemonic in ('bl', 'b', 'blx') or i.mnemonic.startswith('b'):
            if i.operands and i.operands[0].type == 2:  # IMM
                n = symname(syms, addrs, i.operands[0].imm)
                note = n or ''
        print(f'{i.address:08x}: {i.mnemonic:8s} {i.op_str:32s} {note}')


def main():
    img = open(sys.argv[1], 'rb').read()
    syms = load_map(sys.argv[2])
    addrs = [a for a, _ in syms]
    names = {n: a for a, n in syms}
    for want in sys.argv[3:]:
        if ':' in want:
            a, n = (int(x, 0) for x in want.split(':'))
        else:
            a = names[want]
            j = bisect.bisect_right(addrs, a)
            n = (addrs[j] if j < len(addrs) else a + 0x100) - a
        print(f'\n== {symname(syms, addrs, a)} @ 0x{a:08x} ({n} bytes)')
        dis(img, syms, addrs, a, n)


if __name__ == '__main__':
    main()
