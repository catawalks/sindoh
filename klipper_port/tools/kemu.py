"""Boot a UPC Klipper image in Unicorn (ARM946) and talk to it with klippy's msgproto.
usage: kemu.py KLIPPER_TREE klipper.bin fm|io"""
import sys, struct
kl, binpath, core = sys.argv[1:4]
sys.path.insert(0, kl + '/klippy')
import msgproto
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UcError
from unicorn import arm_const as A

FM = core == 'fm'
IPC = 0x04000000 + (0x10000 if FM else 0x14000)
RX, TX, RING = IPC + 0x100, IPC + 0x1100, 0x1000
TIMER = 0x08001144
uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
try:
    uc.ctl_set_cpu_model(A.UC_CPU_ARM_946)
except Exception as e:
    print('cpu model not set:', e)
uc.mem_map(0, 0x10000); uc.mem_write(0, open(binpath, 'rb').read())
uc.mem_map(0x04000000, 0x40000)

state = {'ticks': 0, 't1': int(__import__('os').environ.get('T1INIT', '0'), 0)}
mem = {}; writes = []; starts_at = []
ADC_FIFO = {0: 600, 1: 300}   # raw counts returned for mux sel 0 / 1

def rd(base):
    def f(u, off, size, ud):
        a = base + off
        if a == TIMER:
            d = int(__import__('os').environ.get('TICK','40'))
            state['ticks'] = (state['ticks'] + d) & 0xffffffff   # true elapsed time
            state['treads'] = state.get('treads', 0) + 1
            state['t1'] = max(0, state.get('t1', 0) - d)          # one-shot down-counter
            if not FM and state['t1'] < 0x40000000:               # play the FM core's reload
                sh = 0x04018000
                acc = struct.unpack('<I', uc.mem_read(sh + 16, 4))[0]
                uc.mem_write(sh + 16, struct.pack('<I', (acc + 0xffffffff - state['t1']) & 0xffffffff))
                seq = struct.unpack('<I', uc.mem_read(sh + 12, 4))[0]
                uc.mem_write(sh + 12, struct.pack('<I', (seq + 2) & 0xffffffff))  # as FM does
                state['t1'] = 0xffffffff
            return state['t1']
        if 0xf930a180 <= a < 0xf930a1a8:
            return ADC_FIFO[mem.get(0xf930a200, 0) & 1]
        return mem.get(a, 0)
    return f

def wr(base):
    def f(u, off, size, val, ud):
        a = base + off
        if a == TIMER: state['t1'] = val
        mem[a] = val
        writes.append((a, val))
        if a == 0xf8150060:                       # engine 0 START: when (emulated ticks)
            starts_at.append(state['ticks'])
    return f

for b, s in [(0x08000000, 0x10000), (0xf8000000, 0x200000), (0xf9300000, 0x10000)]:
    uc.mmio_map(b, s, rd(b), None, wr(b), None)

# HOOK=0x1715: count calls of one function (address from the build's
# klipper.elf; Thumb bit dropped), e.g. gpio_out_toggle_noirq = step events
calls = [0]
if __import__('os').environ.get('HOOK'):
    _h = int(__import__('os').environ['HOOK'], 0) & ~1
    def _count(u, addr, size, ud):
        calls[0] += 1
    uc.hook_add(UC_HOOK_CODE, _count, begin=_h, end=_h)

def r32(a): return struct.unpack('<I', uc.mem_read(a, 4))[0]
def w32(a, v): uc.mem_write(a, struct.pack('<I', v & 0xffffffff))

def run(n=300000):
    pc = uc.reg_read(A.UC_ARM_REG_PC)
    if uc.reg_read(A.UC_ARM_REG_CPSR) & 0x20:
        pc |= 1
    try:
        uc.emu_start(pc, 0xffffffff, count=n)
    except UcError as e:
        print('EMU ERROR', e, hex(uc.reg_read(A.UC_ARM_REG_PC)))
        sys.exit(1)
    if r32(IPC + 8) == 0xdead:
        print('FIRMWARE FAULT vector', r32(IPC + 16), 'addr', hex(r32(IPC + 20)))
        sys.exit(1)

# Boot
uc.reg_write(A.UC_ARM_REG_PC, 0)
run(200000)
print('magic %#x state %u heartbeat %u' % (r32(IPC), r32(IPC + 8), r32(IPC + 12)))

parser = msgproto.MessageParser()
seq = [0]
rxbuf = bytearray()

def send(cmdtext):
    cmd = parser.create_command(cmdtext)
    blk = [msgproto.MESSAGE_MIN + len(cmd), (seq[0] & 0x0f) | msgproto.MESSAGE_DEST] + cmd
    blk += msgproto.crc16_ccitt(blk) + [msgproto.MESSAGE_SYNC]
    seq[0] = (seq[0] + 1) & 0x0f
    head = r32(IPC + 0x40)
    for i, b in enumerate(blk):
        uc.mem_write(RX + ((head + i) & (RING - 1)), bytes([b]))
    w32(IPC + 0x40, head + len(blk))

def recv():
    head, tail = r32(IPC + 0x50), r32(IPC + 0x54)
    while tail != head:
        rxbuf.append(uc.mem_read(TX + (tail & (RING - 1)), 1)[0]); tail += 1
    w32(IPC + 0x54, tail)
    msgs = []
    while rxbuf:
        n = parser.check_packet(bytes(rxbuf))
        if n == 0:
            break
        if n < 0:
            del rxbuf[:-n]; continue
        for p in parser_msgs(bytes(rxbuf[:n])):
            msgs.append(p)
        del rxbuf[:n]
    return msgs

def parser_msgs(block):
    out = []
    pos = msgproto.MESSAGE_HEADER_SIZE
    end = len(block) - msgproto.MESSAGE_TRAILER_SIZE
    while pos < end:
        msgid, param_pos = parser.msgid_parser.parse(block, pos)
        mid = parser.messages_by_id.get(msgid, parser.unknown)
        params, pos = mid.parse(block, pos)
        params['#name'] = mid.name
        out.append(params)
    return out

def transact(cmdtext, want, n=400000):
    send(cmdtext)
    got = []
    for _ in range(20):
        run(n // 20)
        got += recv()
        hits = [m for m in got if m.get('#name') == want]
        if hits:
            return hits[0]
    raise SystemExit('no %s response to %r; got %r' % (want, cmdtext, got))

# Identify: fetch the compressed data dictionary
data = b''
while True:
    r = transact('identify offset=%d count=40' % len(data), 'identify_response')
    if not r['data']:
        break
    data += bytes(r['data'])
parser.process_identify(data)
c = parser.get_constants()
print('identify OK: dict %d bytes, MCU=%s CLOCK_FREQ=%s' % (len(data), c.get('MCU'), c.get('CLOCK_FREQ')))
print('constants:', {k: v for k, v in c.items() if k in ('ADC_MAX', 'PWM_MAX', 'RECEIVE_WINDOW', 'STEPPER_STEP_BOTH_EDGE')})
pins = parser.get_enumerations().get('pin', {})
print('pin names: %d (e.g. %s)' % (len(pins), ', '.join(sorted(pins)[:4] + ['...'] + [p for p in ('smot_step0', 'pwm5', 'adc1', 'xena42') if p in pins])))

r = transact('get_uptime', 'uptime'); print('uptime', r['high'], r['clock'])
r = transact('get_config', 'config'); print('get_config', {k: r[k] for k in ('is_config', 'move_count')})

def clock(): return transact('get_clock', 'clock')['clock']

if FM:
    send('allocate_oids count=4')
    send('config_trsync oid=3')
    send('config_stepper oid=0 step_pin=smot_step0 dir_pin=smot_dir0 invert_step=0 step_pulse_ticks=400')
    send('config_endstop oid=1 pin=xena42 pull_up=1')
    send('config_digital_out oid=2 pin=smot_en0 value=1 default_value=1 max_duration=0')
    send('finalize_config crc=1234'); r = transact('get_config', 'config')
    print('after finalize: is_config', r['is_config'], 'move_count', r['move_count'])
    writes.clear()
    t0 = clock() + 200000
    send('reset_step_clock oid=0 clock=%d' % t0)
    send('set_next_step_dir oid=0 dir=1')
    send('queue_step oid=0 interval=4000 count=25 add=0')
    for _ in range(40):
        run(100000); recv()
    starts = [w for w in writes if w[0] == 0xf8150060]
    dirw = [hex(v) for a, v in writes if a == 0xf8150044]
    print('stepper 0: %d hardware pulses issued (expected 25); ctrl writes %s' % (len(starts), dirw[:3]))
    gaps = [b - a for a, b in zip(starts_at, starts_at[1:])]
    print('pulse gaps (emulated ticks): %s' % sorted(set(gaps)))
    r = transact('stepper_get_position oid=0', 'stepper_position'); print('stepper position', r['pos'])
    # Acceleration after a direction change, then a long move read mid-way
    # (UPC_STEP_SINGLE must give the same pulses, times and positions)
    starts_at.clear(); state['treads'] = 0; calls[0] = 0
    send('reset_step_clock oid=0 clock=%d' % (clock() + 200000))
    send('set_next_step_dir oid=0 dir=0')
    send('queue_step oid=0 interval=6000 count=40 add=-20')
    for _ in range(80):
        run(100000); recv()
    gaps = [b - a for a, b in zip(starts_at, starts_at[1:])]
    print('accel: %d pulses (expected 40), gaps %d..%d, hooked calls %d'
          % (len(starts_at), min(gaps), max(gaps), calls[0]))
    r = transact('stepper_get_position oid=0', 'stepper_position'); print('position after accel', r['pos'], '(expected -15)')
    starts_at.clear()
    send('reset_step_clock oid=0 clock=%d' % (clock() + 200000))
    send('queue_step oid=0 interval=8000 count=200 add=0')
    for _ in range(12):
        run(100000); recv()
    r = transact('stepper_get_position oid=0', 'stepper_position')
    print('mid-move: %d pulses by the reply, position %d (-15 - pulses = %d)'
          % (len(starts_at), r['pos'], -15 - len(starts_at)))
    # Homing-style stop (trsync) in the middle of a move: afterwards the
    # position must equal the pulses actually issued
    for _ in range(60):
        run(100000); recv()
    base = transact('stepper_get_position oid=0', 'stepper_position')['pos']
    starts_at.clear()
    send('trsync_start oid=3 report_clock=0 report_ticks=0 expire_reason=4')
    send('stepper_stop_on_trigger oid=0 trsync_oid=3')
    send('reset_step_clock oid=0 clock=%d' % (clock() + 200000))
    send('queue_step oid=0 interval=8000 count=300 add=0')
    for _ in range(14):
        run(100000); recv()
    send('trsync_trigger oid=3 reason=1')
    for _ in range(20):
        run(100000); recv()
    n = len(starts_at)
    for _ in range(20):
        run(100000); recv()
    pos = transact('stepper_get_position oid=0', 'stepper_position')['pos']
    print('trsync stop: %d of 300 pulses, none after (%d), position %d (expected %d)'
          % (n, len(starts_at), pos, base - n))
    mem[0x0800165c] = 1 << 10
    r = transact('endstop_query_state oid=1', 'endstop_state'); print('endstop xena42 high ->', r['pin_value'])
    mem[0x0800165c] = 0
    r = transact('endstop_query_state oid=1', 'endstop_state'); print('endstop xena42 low  ->', r['pin_value'])
else:
    send('allocate_oids count=3')
    send('config_analog_in oid=0 pin=adc0')
    send('config_analog_in oid=1 pin=adc1')
    send('config_digital_out oid=2 pin=pwm5 value=0 default_value=0 max_duration=0')
    send('finalize_config crc=1'); r = transact('get_config', 'config')
    now = clock() + 39600000   # 100 ms ahead (klippy schedules well ahead too)
    send('query_analog_in oid=0 clock=%d sample_ticks=200000 sample_count=8 rest_ticks=60000000 bytes_per_report=2 min_value=100 max_value=8000 range_check_count=4' % now)
    send('query_analog_in oid=1 clock=%d sample_ticks=200000 sample_count=8 rest_ticks=60000000 bytes_per_report=2 min_value=100 max_value=8000 range_check_count=4' % (now + 10))
    got = {}
    for _ in range(int(__import__('os').environ.get('ADCLOOPS','2000'))):
        run(100000)
        for m in recv():
            if m.get('#name') == 'analog_in_state':
                got[m['oid']] = int.from_bytes(bytes(m['values'][:2]), 'little')
        if len(got) == 2:
            break
    print('analog_in_state (sum of 8 samples): adc0 =', got.get(0), '(expect 8*600=4800)  adc1 =', got.get(1), '(expect 8*300=2400)')
    writes.clear()
    send('queue_digital_out oid=2 clock=%d on_ticks=1' % (clock() + 20000000))
    for _ in range(10):
        run(100000); [print('MCU says:', m) for m in recv() if m.get('#name') in ('shutdown','is_shutdown')]
    print('pwm5 ctrl writes:', [hex(v) for a, v in writes if a == 0xf9304500])
print('heartbeat', r32(IPC + 12), 'state', r32(IPC + 8))
