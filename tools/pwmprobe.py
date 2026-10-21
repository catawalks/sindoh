"""Run IO microcode init + timer ticks under Unicorn; log every dec_pwm / dec_adc register write.
usage: pwmprobe.py io.bin [cmd_word target]"""
import sys, struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UcError
from unicorn.arm_const import UC_ARM_REG_CPSR, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

code = open(sys.argv[1], 'rb').read()
uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
uc.mem_map(0, 0x10000); uc.mem_write(0, code)
uc.mem_map(0x04000000, 0x40000)
# preloaded-table checksum must match or init halts; an all-zero table sums to 0 -> store 0 and ~0
uc.mem_write(0x040091d0, struct.pack('<II', 0, 0xffffffff))
log = []; mem = {}; state = {'irq': 0}

def rd(base):
    def f(u, off, size, ud):
        a = base + off
        if a == 0xf8060014: return 0x60
        if a == 0x080018c0: return state['irq']
        if 0xf930a180 <= a < 0xf930a1a8: return 0x400
        return mem.get(a, 0)
    return f

def wr(base):
    def f(u, off, size, val, ud):
        a = base + off
        if a == 0xf8060000: return
        mem[a] = val
        if 0xf9304000 <= a < 0xf9308000 or a in (0x08001140, 0x08001880, 0x0800188c):
            log.append((u.reg_read(UC_ARM_REG_PC), a, val))
    return f

for b, s in [(0x08000000, 0x10000), (0xf9300000, 0x10000), (0xf8000000, 0x200000)]:
    uc.mmio_map(b, s, rd(b), None, wr(b), None)

try: uc.emu_start(0, 0xffffffff, count=600000)
except UcError as e: print('init stop', e)
idle = uc.reg_read(UC_ARM_REG_PC)
print(f'idle pc={idle:#x}')
for pc, a, v in log: print(f'INIT pc={pc:05x} {a:#010x} <- {v:#x}')

def irq(bits, n=1):
    for _ in range(n):
        log.clear(); state['irq'] = bits
        uc.reg_write(UC_ARM_REG_CPSR, (uc.reg_read(UC_ARM_REG_CPSR) & ~0x1f) | 0x92)
        uc.reg_write(UC_ARM_REG_SP, 0x04034000); uc.reg_write(UC_ARM_REG_LR, idle + 4)
        try: uc.emu_start(0x18, idle, count=400000)
        except UcError as e: print('irq stop', e)

if len(sys.argv) > 3:
    uc.mem_write(0x04009340, struct.pack('<I', int(sys.argv[2], 0)))
    uc.mem_write(0x04009344, struct.pack('<I', int(sys.argv[3], 0)))
    uc.mem_write(0x04009348, struct.pack('<I', int(sys.argv[3], 0)))
    irq(0x20)
    for pc, a, v in log: print(f'CMD  pc={pc:05x} {a:#010x} <- {v:#x}')
    irq(0x1, 30)
    for pc, a, v in log: print(f'TICK pc={pc:05x} {a:#010x} <- {v:#x}')
