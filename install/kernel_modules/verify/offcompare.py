"""Compare the struct field offsets used by the running vendor kernel's
USB/tty functions (bytes dumped from /dev/kmem) with the same functions
compiled from vanilla 3.2 with our config. Different compilers produce
different code, but memory accesses to struct fields must use the same
offsets if the layouts match. Usage: python -I offcompare.py DIR"""
import os, sys
sys.path.insert(0, os.path.join(os.environ['TEMP'], 'pdflib'))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from capstone.arm import ARM_OP_MEM, ARM_OP_IMM, ARM_REG_SP, ARM_REG_PC, ARM_REG_R11
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

D = sys.argv[1]
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
md.detail = True
SKIP = (ARM_REG_SP, ARM_REG_PC, ARM_REG_R11)    # stack, literal pool, frame pointer


def offsets(code):
    out = set()
    for ins in md.disasm(code, 0):
        ops = ins.operands
        for op in ops:
            if op.type == ARM_OP_MEM and op.mem.base not in SKIP and op.mem.index == 0 and op.mem.disp:
                out.add(abs(op.mem.disp))
        # add rd, rn, #imm with rn a struct pointer: address of a member
        if ins.mnemonic.startswith('add') and len(ops) == 3 and ops[2].type == ARM_OP_IMM \
                and ops[1].reg not in SKIP and 0 < ops[2].imm < 4096:
            out.add(ops[2].imm)
    return out


ours = {}
for fn in os.listdir(D):
    if not fn.startswith('ours_'):
        continue
    with open(os.path.join(D, fn), 'rb') as f:
        elf = ELFFile(f)
        secs = list(elf.iter_sections())
        for sec in secs:
            if not isinstance(sec, SymbolTableSection):
                continue
            for s in sec.iter_symbols():
                if s['st_info']['type'] != 'STT_FUNC' or not isinstance(s['st_shndx'], int):
                    continue
                data = secs[s['st_shndx']].data()
                ours[s.name] = data[s['st_value']:s['st_value'] + s['st_size']]

tot_v = tot_both = 0
for fn in sorted(os.listdir(D)):
    if not fn.endswith('.bin'):
        continue
    name = fn[:-4]
    if name not in ours:
        print('%-36s not in our objects' % name)
        continue
    v = offsets(open(os.path.join(D, fn), 'rb').read())
    o = offsets(ours[name])
    both = v & o
    tot_v += len(v)
    tot_both += len(both)
    print('%-36s vendor %2d offsets, ours %2d, shared %2d | only vendor %s | only ours %s'
          % (name, len(v), len(o), len(both), sorted(v - o), sorted(o - v)))
print('TOTAL: %d of %d vendor offsets also used by our build (%.0f %%)'
      % (tot_both, tot_v, 100.0 * tot_both / max(tot_v, 1)))
