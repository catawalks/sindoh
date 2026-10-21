import sys
from capstone import *
code = open(sys.argv[1], 'rb').read()
start = int(sys.argv[2], 0); end = int(sys.argv[3], 0)
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
for i in md.disasm(code[start:end], start):
    w = int.from_bytes(code[i.address:i.address+4], 'little')
    print(f'{i.address:05x}: {w:08x}  {i.mnemonic:8s} {i.op_str}')
