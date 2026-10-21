"""Emulate stock FM microcode commands with the real karas.db parameter blocks and print
the resulting motion sequence (stepper-engine moves, PWM writes, sensor reads, UART text).
usage: fmseq.py fm.bin RE_snapshot.zip karas.db CMD [CMD ...]
   env SENSE: comma list addr=value overrides for sensor registers (default all 0),
   env SENSE_AFTER: number of reads after which XIRD/XIRD1 return 0xffffffff (default never)"""
import os, re, sqlite3, struct, sys, zipfile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UcError
from unicorn.arm_const import UC_ARM_REG_CPSR, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

fm_bin, zf, db = sys.argv[1:4]
cmds = [int(x, 0) for x in sys.argv[4:]]
STEPS_MM = {0: 80.0, 1: 80.0, 2: 3200.0, 3: 458.83, 4: 1.0}
AXIS = {0: 'X', 1: 'Y', 2: 'Z', 3: 'E', 4: 'C'}

# --- parameter blocks: globals image from engine_loadDBValue, row NO=4 ---
z = zipfile.ZipFile(zf)
t = z.read([x for x in z.namelist() if x.endswith('/engine_loadDBValue.c')][0]).decode(errors='replace')
c = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
glob = {}
for m in re.finditer(r'(xRam00361[0-9a-f]{3}) = db_get_var_\w+\(0x[0-9a-f]+ /\*"(CONF_ENGINE_\w+)"\*/,'
                     r'0x[0-9a-f]+ /\*"([^"]+)"', t):
    a = int(m.group(1)[4:], 16)
    if a in glob:
        continue
    v = c.execute('select "%s" from "%s" where NO=4' % (m.group(3), m.group(2))).fetchone()[0]
    glob[a] = (int(float(v)) if v is not None else 0, m.group(3))
def block(base, size):
    b = bytearray(size)
    for off in range(0, size, 4):
        v = glob.get(base + off, (0, None))[0]
        struct.pack_into('<i', b, off, v)
    return bytes(b)
# Block bases derived from how the FM code uses the fields (see docs/stock_routines.md)
BLOCKS = {0x9464: (int(os.environ.get('EJECT_BASE', '0x3618f0'), 0), 0xa4, 'EJECT'),
          0x93f0: (int(os.environ.get('INSERT_BASE', '0x36187c'), 0), 0x74, 'INSERT')}

uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
uc.mem_map(0, 0x10000); uc.mem_write(0, open(fm_bin, 'rb').read())
uc.mem_map(0x04000000, 0x40000)

# Preloaded DTCM tables exactly as upc_driver_init() builds them
def preload(elf_path):
    from elftools.elf.elffile import ELFFile
    e = ELFFile(open(elf_path, 'rb'))
    syms = {s.name: s['st_value'] for s in e.get_section_by_name('.dynsym').iter_symbols()}
    segs = [(s['p_vaddr'], s.data()) for s in e.iter_segments() if s['p_type'] == 'PT_LOAD']
    def rdm(a, n):
        for va, d in segs:
            if va <= a < va + len(d):
                return d[a - va:a - va + n].ljust(n, b'\0')
        return bytes(n)
    tb = bytearray(0x99e0)
    for name, off, size in [('adc_temp_mC_lookup_table', 0, 0x1e48), ('adc_bed_mC_lookup_table', 0x1e48, 0x1a0c),
                            ('pwm_power_mW_lookup_table', 0x3854, 0x1f48), ('XYAccelPWM_M', 0x579c, 0xa1c),
                            ('EAccelPWM_M', 0x61b8, 0x1558), ('ZAccelPWM_M', 0x7710, 0x1a18),
                            ('defaultAccelTbl_InMainCode', 0x9128, 0xa8), ('machine_Constraints', 0x93a8, 0x48)]:
        tb[off:off + size] = rdm(syms[name], size)
    cs = sum(tb[:0x91d0]) & 0xffffffff
    struct.pack_into('<II', tb, 0x91d0, cs, (~cs) & 0xffffffff)
    return bytes(tb)
ELF = os.environ.get('MAIN_ELF', r'D:\DP200\backup\Sindoh_raw_dump\marvell_lspsdk_3dp_gemstone-debug_stripped.elf')
uc.mem_write(0x04000000, preload(ELF))
for off, (base, size, _) in BLOCKS.items():
    uc.mem_write(0x04000000 + off, block(base, size))

mem = {}; log = []; uart = []; nreads = {}
sense = {}
for kv in filter(None, os.environ.get('SENSE', '').split(',')):
    k, v = kv.split('='); sense[int(k, 0)] = int(v, 0)
SENSE_AFTER = int(os.environ.get('SENSE_AFTER', '-1'))

def rd(base):
    def f(u, off, size, ud):
        a = base + off
        nreads[a] = nreads.get(a, 0) + 1
        if a == 0xf8060014:
            return 0x60
        if 0xf8150000 <= a < 0xf8155000 and (a & 0xfff) == 0x64:
            return 0                           # +0x64 bit8 = busy -> never busy
        if 0xf8150000 <= a < 0xf8155000 and (a & 0xfff) == 0x88:
            return 0x100                       # +0x88 bit8 = done
        if a == 0x08001840:
            return 0x200
        if a in sense:
            return sense[a]
        if a in (0x0800165c, 0x08001658) and SENSE_AFTER >= 0 and nreads[a] > SENSE_AFTER:
            return 0xffffffff
        if a == 0xf930100c:                    # filament encoder count: moves until ENC_STOP reads
            return min(nreads[a], int(os.environ.get('ENC_STOP', '1000000')))
        v = mem.get(a, 0)
        if (0xf9300000 <= a < 0xf9310000 or a in (0x0800165c, 0x08001658)) and a not in (0x08001840,):
            log.append(('R', u.reg_read(UC_ARM_REG_PC), a, v))
        return v
    return f

def wr(base):
    def f(u, off, size, val, ud):
        a = base + off
        if a == 0xf8060000:
            uart.append(chr(val & 0xff)); return
        mem[a] = val
        if not (0x08001840 <= a < 0x08001870):
            log.append(('W', u.reg_read(UC_ARM_REG_PC), a, val))
    return f

for b, s in [(0x08000000, 0x10000), (0xf9300000, 0x10000), (0xf8000000, 0x200000)]:
    uc.mmio_map(b, s, rd(b), None, wr(b), None)
try:
    uc.emu_start(0, 0xffffffff, count=600000)
except UcError as e:
    print('init stop', e)
idle = uc.reg_read(UC_ARM_REG_PC)
uart.clear()

def summarize():
    eng = {}
    out = []
    for kind, pc, a, v in log:
        if 0xf8150000 <= a < 0xf8155000:
            n, r = (a - 0xf8150000) >> 12, a & 0xfff
            e = eng.setdefault(n, {})
            if kind == 'W':
                e[r] = v
                if r == 0x60 and v == 1:
                    cmd = e.get(0x5c, 0); edges, mode = cmd >> 16, cmd & 0xffff
                    per = e.get(0x58, 0); dirb = (e.get(0x44, 0) >> 4) & 1
                    steps = edges // 2
                    rate = 200e6 / (2 * per) if per else 0
                    out.append('MOVE %s dir=%d steps=%d (%.2f mm) period=%d -> %.1f steps/s (%.2f mm/s) mode=%#x ramp=%d'
                               % (AXIS[n], dirb, steps, steps / STEPS_MM[n], per, rate, rate / STEPS_MM[n],
                                  mode, e.get(0x54, 0)))
                elif r == 0x04:
                    out.append('ABORT %s' % AXIS[n])
                elif r == 0x0c:
                    out.append('CFG %s driver %s' % (AXIS[n], 'OFF' if v & 1 else 'ON'))
        elif 0xf9304000 <= a < 0xf9308000 and kind == 'W':
            blk, r = (a - 0xf9304000) >> 8, a & 0xff
            if blk and r in (0, 8, 0xc):
                out.append('PWM block %d reg+%#x = %#x' % (blk, r, v))
        elif kind == 'R' and a in (0x0800165c, 0x08001658):
            pass
        elif kind == 'R':
            out.append('READ %#x = %#x (pc %#x)' % (a, v, pc))
    return out

for cmd in cmds:
    log.clear(); nreads.clear()
    blk = 0x040095c0
    uc.mem_write(blk, bytes(700)); uc.mem_write(blk, struct.pack('<I', cmd))
    uc.reg_write(UC_ARM_REG_CPSR, (uc.reg_read(UC_ARM_REG_CPSR) & ~0x1f) | 0x92)
    uc.reg_write(UC_ARM_REG_SP, 0x0403c000 - 0x100); uc.reg_write(UC_ARM_REG_LR, idle + 4)
    try:
        uc.emu_start(0x18, idle, count=20000000)
    except UcError as e:
        print('cmd stop', e, hex(uc.reg_read(UC_ARM_REG_PC)))
    sensor_reads = {a: n for a, n in nreads.items() if a in (0x0800165c, 0x08001658)}
    print('==== FM cmd %#x  uart=%r  sensor polls=%s' % (cmd, ''.join(uart), {hex(k): v for k, v in sensor_reads.items()}))
    uart.clear()
    prev = None; rep = 0
    for line in summarize():
        if line == prev:
            rep += 1; continue
        if rep:
            print('   (x%d more)' % rep); rep = 0
        print('  ', line); prev = line
    if rep:
        print('   (x%d more)' % rep)
