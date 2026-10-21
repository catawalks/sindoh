"""Scan an ARM ELF's executable sections for instructions touching d16-d31 / q8-q15 (absent on VFPv3-D16)."""
import sys, re
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
e = ELFFile(open(sys.argv[1], 'rb'))
bad = re.compile(r'\b(d(1[6-9]|2\d|3[01])|q([89]|1[0-5]))\b')
hits = 0; neon = 0
for sec in e.iter_sections():
    if not (sec['sh_flags'] & 4):
        continue
    data = sec.data(); base = sec['sh_addr']
    for mode in (CS_MODE_ARM, CS_MODE_THUMB):
        md = Cs(CS_ARCH_ARM, mode); md.skipdata = True
        for i in md.disasm(data, base):
            if bad.search(i.op_str):
                hits += 1
                if hits <= 10: print(f'{"ARM" if mode == CS_MODE_ARM else "THM"} {i.address:#x}: {i.mnemonic} {i.op_str}')
            if i.mnemonic.startswith('v') and ('.i' in i.mnemonic or 'q' in i.op_str):
                neon += 1
print('d16-d31/q8+ uses:', hits, ' neon-looking:', neon)
