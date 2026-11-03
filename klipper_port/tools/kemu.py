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
        if 0xf8150000 <= a < 0xf8155000:
            e = eng.get((a - 0xf8150000) >> 12)
            r = a & 0xfff
            if e is not None and r in (0x64, 0x78, 0x88):
                now = state['ticks']
                if r == 0x64:                         # COM_STAT: bit 8 busy
                    return 0x106 if now < e['end'] else 7
                if r == 0x88:                         # I_PEND: bit 8 done
                    return 0x108 if now >= e['end'] else 8
                done = min(e['edges'], (now - e['start']) // e['tpe'])
                return (e['c0'] - done) & 0xffffff    # COM_STP: edge down-counter
        return mem.get(a, 0)
    return f

# Stepper engine model (hardware run 2026-11-03, docs/faster_stepping_plan.md):
# START runs CMD's edge count at PWM_M x PWM_P engine ticks per edge (engine
# clock = half the FM timer); +0x64 bit 8 busy, +0x88 bit 8 done, +0x78 a
# 24-bit down-counter of edges; ABORT (+0x04 = 0x100) stops it. Rising
# edges (the steps) are at start + (2k+1) edge times. starts_at = step times
# of engine 0; state['overrun'] counts STARTs while still busy.
eng = {}

def eng_write(n, r, val):
    now = state['ticks']
    e = eng.get(n)
    if r == 0x60 and val == 1:
        if e is not None and now < e['end']:
            state['overrun'] = state.get('overrun', 0) + 1
        b = 0xf8150000 + 0x1000 * n
        edges = mem.get(b + 0x5c, 0) >> 16
        tpe = max(1, mem.get(b + 0x58, 0) * max(1, mem.get(b + 0x50, 1)) * 2)
        c0 = 0
        if e is not None:
            c0 = (e['c0'] - min(e['edges'], (now - e['start']) // e['tpe'])) & 0xffffff
        eng[n] = {'start': now, 'end': now + edges * tpe, 'edges': edges, 'tpe': tpe, 'c0': c0}
        if n == 0:
            starts_at.extend(now + tpe * (2 * k + 1) for k in range(edges // 2))
    elif r == 0x04 and val & 0x100 and e is not None:
        if now < e['end']:
            e['edges'] = (now - e['start']) // e['tpe']
            e['end'] = now
            if n == 0:
                starts_at[:] = [t for t in starts_at if t <= now]
        else:
            e['c0'], e['edges'] = 0, 0                # config ABORT: counter back to 0

def steps_done():
    """Engine 0 steps whose rising edge has happened by now."""
    return sum(1 for t in starts_at if t <= state['ticks'])

def wr(base):
    def f(u, off, size, val, ud):
        a = base + off
        if a == TIMER: state['t1'] = val
        mem[a] = val
        writes.append((a, val))
        if 0xf8150000 <= a < 0xf8155000:
            eng_write((a - 0xf8150000) >> 12, a & 0xfff, val)
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
    def expected(t, blocks):
        """Klipper's step times for queue_step blocks after a step at t."""
        out = []
        for interval, count, add in blocks:
            t += interval
            out.append(t)
            iv = interval + add
            for _ in range(count - 1):
                t += iv
                out.append(t)
                iv += add
        return out

    def run_blocks(name, blocks, dir_=None, loops=200):
        starts_at.clear(); calls[0] = 0; state['overrun'] = 0
        t0 = clock() + 300000
        send('reset_step_clock oid=0 clock=%d' % t0)
        if dir_ is not None:
            send('set_next_step_dir oid=0 dir=%d' % dir_)
        for b in blocks:
            send('queue_step oid=0 interval=%d count=%d add=%d' % b)
        want = expected(t0, blocks)
        for _ in range(loops):
            run(100000); recv()
            if len(starts_at) >= len(want) and steps_done() >= len(want):
                break
        got = sorted(starts_at)
        dev = [g - w for g, w in zip(got, want)]
        print('%s: %d steps (expected %d), step time - schedule %d..%d ticks, '
              'engine STARTs %d, overruns %d, hooked calls %d'
              % (name, len(got), len(want), min(dev), max(dev),
                 sum(1 for a, v in writes if a == 0xf8150060 and v == 1),
                 state.get('overrun', 0), calls[0]))
        writes.clear()
        return len(got)

    writes.clear()
    run_blocks('constant', [(4000, 25, 0)], dir_=1)
    r = transact('stepper_get_position oid=0', 'stepper_position'); print('position', r['pos'], '(expected 25)')
    run_blocks('accel after dir change', [(6000, 40, -20)], dir_=0)
    r = transact('stepper_get_position oid=0', 'stepper_position'); print('position', r['pos'], '(expected -15)')
    run_blocks('mixed blocks', [(5000, 50, 0), (5000, 30, -30), (4130, 60, 0), (4130, 20, 25)])
    r = transact('stepper_get_position oid=0', 'stepper_position'); print('position', r['pos'], '(expected -175)')
    run_blocks('back-to-back constant', [(5000, 40, 0), (4400, 40, 0), (4003, 400, 0)], loops=400)
    r = transact('stepper_get_position oid=0', 'stepper_position'); print('position', r['pos'], '(expected -655)')
    # position read in the middle of a long constant block
    starts_at.clear()
    send('reset_step_clock oid=0 clock=%d' % (clock() + 300000))
    send('queue_step oid=0 interval=8000 count=200 add=0')
    for _ in range(14):
        run(100000); recv()
    r = transact('stepper_get_position oid=0', 'stepper_position')
    n = steps_done()
    print('mid-move: %d steps done at the reply, position %d (-655 - steps = %d)' % (n, r['pos'], -655 - n))
    for _ in range(120):
        run(100000); recv()
        if steps_done() >= 200:
            break
    base = transact('stepper_get_position oid=0', 'stepper_position')['pos']
    # Homing-style stop (trsync) in the middle of a move: afterwards the
    # position must equal the steps actually made, and none may follow
    starts_at.clear()
    send('trsync_start oid=3 report_clock=0 report_ticks=0 expire_reason=4')
    send('stepper_stop_on_trigger oid=0 trsync_oid=3')
    send('reset_step_clock oid=0 clock=%d' % (clock() + 300000))
    send('queue_step oid=0 interval=8000 count=300 add=0')
    for _ in range(16):
        run(100000); recv()
    send('trsync_trigger oid=3 reason=1')
    for _ in range(20):
        run(100000); recv()
    n = steps_done()
    for _ in range(40):
        run(100000); recv()
    pos = transact('stepper_get_position oid=0', 'stepper_position')['pos']
    print('trsync stop: %d of 300 steps, %d after the stop, position %d (expected %d)'
          % (n, steps_done() - n, pos, base - n))
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
