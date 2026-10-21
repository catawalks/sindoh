"""Disassemble functions of an ARM ELF by symbol name, annotating literal-pool
loads with the string or symbol they point to.
    python tools/elfdis.py app.elf func [func...]
Needs: pip install pyelftools capstone"""
import sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from capstone.arm import ARM_OP_MEM, ARM_REG_PC
from elftools.elf.elffile import ELFFile

f = ELFFile(open(sys.argv[1], 'rb'))
data = open(sys.argv[1], 'rb').read()
segs = [(s['p_vaddr'], s['p_offset'], s['p_filesz']) for s in f.iter_segments() if s['p_type'] == 'PT_LOAD']
syms = {}
for s in f.get_section_by_name('.dynsym').iter_symbols():
    if s.name and s['st_value']:
        syms[s.name] = (s['st_value'] & ~1, s['st_size'])
by_addr = {v[0]: k for k, v in syms.items()}

def off(va):
    for v, o, n in segs:
        if v <= va < v + n:
            return o + va - v
    return None

def word(va):
    o = off(va)
    return int.from_bytes(data[o:o + 4], 'little') if o is not None else None

def cstr(va):
    o = off(va)
    if o is None:
        return None
    end = data.find(b'\0', o, o + 200)
    s = data[o:end]
    if len(s) >= 3 and all(32 <= c < 127 or c in (9, 10, 13) for c in s):
        return s.decode()
    return None

md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
md.detail = True
for name in sys.argv[2:]:
    if name.startswith('0x'):                    # unnamed (static) function: addr[:size]
        a, _, n = name.partition(':')
        va, size = int(a, 16), int(n or '0x300', 16)
    else:
        va, size = syms[name]
    print('==== %s @ %#x (%d bytes)' % (name, va, size))
    o = off(va)
    for i in md.disasm(data[o:o + size], va):
        note = ''
        if i.mnemonic.startswith('ldr') and len(i.operands) == 2:
            m = i.operands[1]
            if m.type == ARM_OP_MEM and m.mem.base == ARM_REG_PC:
                lit = word(i.address + 8 + m.mem.disp)
                if lit is not None:
                    s = cstr(lit)
                    note = '  ; =%#x %s' % (lit, repr(s) if s else by_addr.get(lit, ''))
        if i.mnemonic in ('bl', 'blx', 'b') and i.op_str.startswith('#'):
            t = int(i.op_str[1:], 0)
            note = '  ; ' + by_addr.get(t, '')
        print('%06x: %-7s %s%s' % (i.address, i.mnemonic, i.op_str, note))
