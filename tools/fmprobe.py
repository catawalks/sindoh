"""Run FM microcode init, then optionally one command; log stepper-engine, XENA and dec_* writes.
usage: fmprobe.py fm.bin [cmd [off=val ...]]"""
import sys, struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UcError
from unicorn.arm_const import UC_ARM_REG_CPSR, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

code = open(sys.argv[1], 'rb').read()
uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
uc.mem_map(0, 0x10000); uc.mem_write(0, code)
uc.mem_map(0x04000000, 0x40000)
uc.mem_write(0x040091d0, struct.pack('<II', 0, 0xffffffff))
log = []; mem = {}; nreads = {}

def rd(base):
    def f(u, off, size, ud):
        a = base + off
        nreads[a] = nreads.get(a, 0) + 1
        if a == 0xf8060014: return 0x60
        if 0xf8150000 <= a < 0xf8155000 and (a & 0xfff) in (0x64, 0x88): return 0x100
        if a == 0x08001840: return 0x200
        if a in (0x0800165c, 0x08001658): return 0xffffffff if nreads[a] > 40 else 0
        return mem.get(a, 0)
    return f

def wr(base):
    def f(u, off, size, val, ud):
        a = base + off
        if a == 0xf8060000: return
        mem[a] = val
        if a not in range(0x08001840, 0x08001870):
            log.append((u.reg_read(UC_ARM_REG_PC), a, val))
    return f

for b, s in [(0x08000000, 0x10000), (0xf9300000, 0x10000), (0xf8000000, 0x200000)]:
    uc.mmio_map(b, s, rd(b), None, wr(b), None)
try: uc.emu_start(0, 0xffffffff, count=600000)
except UcError as e: print('init stop', e)
idle = uc.reg_read(UC_ARM_REG_PC)
print(f'idle pc={idle:#x}')
for pc, a, v in log: print(f'INIT pc={pc:05x} {a:#010x} <- {v:#x}')
if len(sys.argv) > 2:
    log.clear(); nreads.clear()
    blk = 0x040095c0
    uc.mem_write(blk, bytes(700)); uc.mem_write(blk, struct.pack('<I', int(sys.argv[2], 0)))
    for kv in sys.argv[3:]:
        k, v = kv.split('='); uc.mem_write(blk + int(k, 16), struct.pack('<i', int(v, 0)))
    uc.reg_write(UC_ARM_REG_CPSR, (uc.reg_read(UC_ARM_REG_CPSR) & ~0x1f) | 0x92)
    uc.reg_write(UC_ARM_REG_SP, 0x0403c000 - 0x100); uc.reg_write(UC_ARM_REG_LR, idle + 4)
    try: uc.emu_start(0x18, idle, count=3000000)
    except UcError as e: print('cmd stop', e)
    for pc, a, v in log[:200]: print(f'CMD  pc={pc:05x} {a:#010x} <- {v:#x}')
