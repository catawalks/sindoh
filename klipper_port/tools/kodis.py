"""Disassemble named functions of an ARM kernel module with relocation targets annotated.
usage: kodis.py module.ko func [func...]"""
import sys
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
e = ELFFile(open(sys.argv[1], 'rb'))
st = e.get_section_by_name('.symtab')
syms = list(st.iter_symbols())
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
for want in sys.argv[2:]:
    s = next(x for x in syms if x.name == want)
    sec = e.get_section(s['st_shndx'])
    rel = {}
    for rs in e.iter_sections():
        if isinstance(rs, RelocationSection) and rs['sh_info'] == s['st_shndx']:
            for r in rs.iter_relocations():
                t = syms[r['r_info_sym']]
                rel[r['r_offset']] = t.name or e.get_section(t['st_shndx']).name
    data = sec.data()[s['st_value']:s['st_value'] + s['st_size']]
    print(f'==== {want} ({sec.name}+{s["st_value"]:#x}, {s["st_size"]} bytes)')
    for i in md.disasm(data, s['st_value']):
        w = int.from_bytes(data[i.address - s['st_value']:i.address - s['st_value'] + 4], 'little')
        print(f'{i.address:05x}: {w:08x}  {i.mnemonic:7s} {i.op_str:30s} {rel.get(i.address, "")}')
