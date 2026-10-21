"""Emulate the probe firmware and decode its report like 'upctool probe'.
usage: pemu.py probe.bin fm|io"""
import sys, struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UcError
from unicorn import arm_const as A
binp, core = sys.argv[1:3]
FM = core == 'fm'
IPC = 0x04000000 + (0x10000 if FM else 0x14000)
REP = IPC + 0x2100
uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
uc.ctl_set_cpu_model(A.UC_CPU_ARM_946)
uc.mem_map(0, 0x20000); uc.mem_write(0, open(binp, 'rb').read())
uc.mem_map(0x04000000, 0x100000)
st = {'perf': 0, 'n': 0}; mem = {}; uart = []
def rd(base):
    def f(u, off, size, ud):
        a = base + off; st['n'] += 1
        if a == 0x08000204: st['perf'] += 37; return st['perf'] & 0xffffffff
        if a == 0xf8060014: return 0x60
        if a == 0x0800165c: return (1 << 10) if (st['n'] // 5000) % 2 else 0
        if 0xf930a180 <= a < 0xf930a1a8: return 700 if (mem.get(0xf930a200, 0) & 1) == 0 else 350
        return mem.get(a, 0)
    return f
def wr(base):
    def f(u, off, size, val, ud):
        a = base + off
        if a == 0xf8060000: uart.append(chr(val & 0xff)); return
        mem[a] = val
    return f
for b, s in [(0x08000000, 0x10000), (0xf8000000, 0x200000), (0xf9300000, 0x10000)]:
    uc.mmio_map(b, s, rd(b), None, wr(b), None)
try:
    uc.emu_start(0, 0xffffffff, count=3000000)
except UcError as e:
    print('EMU ERROR', e, hex(uc.reg_read(A.UC_ARM_REG_PC)))
r = lambda a: struct.unpack('<I', uc.mem_read(a, 4))[0]
print('uart:', repr(''.join(uart)))
print('ipc magic %#x fw %s state %u' % (r(IPC), uc.mem_read(IPC + 32, 4).decode(), r(IPC + 8)))
f = struct.unpack('<17I', uc.mem_read(REP, 68))
names = 'magic loops core cpsr cp15_id cp15_ctrl cp15_tcm thumb_ok dtcm_exec_ok aborts xird xird1 xird_or xird1_or xird_and xird1_and adc_enabled'.split()
d = dict(zip(names, f)); print({k: hex(v) for k, v in d.items()})
off = REP + 68
fifo = struct.unpack('<20I', uc.mem_read(off, 80)); off += 80
code = struct.unpack('<2I', uc.mem_read(off, 8)); off += 8
print('adc fifo sel0', fifo[:10], 'sel1', fifo[10:], 'codes', code)
ta = struct.unpack('<8I', uc.mem_read(off, 32)); off += 32
tr = struct.unpack('<8I', uc.mem_read(off, 32)); off += 32
print('tcm tests', [(hex(a), x) for a, x in zip(ta, tr)])
for i in range(16):
    c = struct.unpack('<6I', uc.mem_read(off + 24 * i, 24))
    if c[3]: print('counter %#010x first %#x last %#x chg %u up %u down %u' % c)
