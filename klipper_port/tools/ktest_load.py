"""Heated filament load/purge on the real printer (no X/Y/Z motion; nozzle stays where it is).
Heats the nozzle (pwm5, adc0) to TARGET, then clutch (pwm6) on and feeds MM at SPEED mm/s in
5 mm chunks (heater loop keeps running), waits, optional retract, everything off, MCUs reset.
usage: ktest_load.py KLIPPER_TREE PRINTER_IP PRINTER_CFG MM [speed=3] [target_C=210] [max_duty=0.6] [retract_mm=0]"""
import re, sys, time
kl, ip, cfgpath, MM = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
SPEED = float(sys.argv[5]) if len(sys.argv) > 5 else 3.0
TARGET = float(sys.argv[6]) if len(sys.argv) > 6 else 210.0
MAX_DUTY = float(sys.argv[7]) if len(sys.argv) > 7 else 0.60
RETRACT = float(sys.argv[8]) if len(sys.argv) > 8 else 0.0
if not (0 < MM <= 150 and 0 < SPEED <= 10 and TARGET <= 250 and 0 <= RETRACT <= 20):
    sys.exit('refusing: 0 < MM <= 150, speed <= 10, target <= 250, retract <= 20')
THRESH = TARGET - 5.0
LIMIT_C = TARGET + 20.0
TOTAL_S = 360.0
src = open(__file__.replace('ktest_load.py', 'khost.py'), encoding='utf-8-sig').read().split('fm = Mcu(')[0]
g = {'__name__': 'load'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
F = 396000000
E_SPM = 458.83

txt = open(cfgpath, encoding='utf-8').read()
blk = txt.split('[adc_temperature dp200_nozzle]')[1].split('\n[')[0]
T = [float(x) for x in re.findall(r'temperature\d+:\s*([-\d.]+)', blk)]
V = [float(x) for x in re.findall(r'voltage\d+:\s*([-\d.]+)', blk)]
pts = sorted(zip(V, T))
def temp(raw):
    v = raw / 1023.0
    for (v0, t0), (v1, t1) in zip(pts, pts[1:]):
        if v0 <= v <= v1:
            return t0 + (v - v0) / (v1 - v0) * (t1 - t0)
    return float('nan')
def raw_for(t):
    for (v0, t0), (v1, t1) in zip(pts, pts[1:]):
        if min(t0, t1) <= t <= max(t0, t1):
            return (v0 + (t - t0) / (t1 - t0) * (v1 - v0)) * 1023
    raise SystemExit('temperature outside table')

def fresh(m):
    m.identify()
    c = m.transact('get_config', 'config')
    if c['is_config'] or c['is_shutdown']:
        m.send('reset'); time.sleep(1.0); m.recv(0.3)
        m.seq = 0; m.mcu_next = None
        m.identify()

fm = g['Mcu']('FM', 9100); io = g['Mcu']('IO', 9101)
fresh(fm); fresh(io)

# ---- FM: E stepper, enable, REF, clutch, lever
fm.send('allocate_oids count=5')
fm.send('config_stepper oid=0 step_pin=smot_step3 dir_pin=smot_dir3 invert_step=0 step_pulse_ticks=%d' % (2 * F // 1000000))
fm.send('config_digital_out oid=1 pin=smot_en3 value=1 default_value=1 max_duration=0')
fm.send('config_pwm_out oid=2 pin=pwm31 cycle_ticks=%d value=0 default_value=0 max_duration=0' % (F // 10000))
fm.send('config_digital_out oid=3 pin=pwm6 value=0 default_value=0 max_duration=0')       # clutch
fm.send('config_endstop oid=4 pin=xena46 pull_up=0')                                      # lever
fm.send('finalize_config crc=0')
# ---- IO: nozzle ADC, heater (2 s watchdog), hotend fan
io.send('allocate_oids count=3')
io.send('config_analog_in oid=0 pin=adc0')
io.send('config_digital_out oid=1 pin=pwm5 value=0 default_value=0 max_duration=%d' % (2 * F))
io.send('config_digital_out oid=2 pin=pwm1 value=0 default_value=0 max_duration=0')
io.send('finalize_config crc=0')
for m in (fm, io):
    r = m.transact('get_config', 'config')
    if not r['is_config'] or r['is_shutdown']:
        sys.exit('%s config failed %r' % (m.name, r))
CYCLE = F // 10
io.send('set_digital_out_pwm_cycle oid=1 cycle_ticks=%d' % CYCLE)
now = io.clock()[0]
io.send('query_analog_in oid=0 clock=%d sample_ticks=%d sample_count=8 rest_ticks=%d bytes_per_report=2'
        ' min_value=%d max_value=%d range_check_count=4'
        % ((now + F) & 0xffffffff, F // 1000, int(F * 0.3), int(raw_for(LIMIT_C) * 8), 1015 * 8))
io.send('update_digital_out oid=2 value=1')       # hotend fan on

st = {'temp': None, 'start': None, 't0': time.time(), 'abort': None, 'sync': None}
def io_resync():
    c, t, _ = io.clock(); st['sync'] = (c, t)
def io_est():
    c, t = st['sync']; return (c + int((time.time() - t) * F)) & 0xffffffff
io_resync(); st['next_sync'] = time.time() + 10
def heat_step():
    for m in io.recv(0.02):
        if m['#name'] in ('shutdown', 'is_shutdown'):
            st['abort'] = 'IO MCU shutdown: %s' % m.get('static_string_id')
        if m['#name'] == 'analog_in_state':
            st['temp'] = temp(int.from_bytes(bytes(m['values'][:2]), 'little') / 8.0)
            if st['start'] is None:
                st['start'] = (st['temp'], time.time())
    if st['temp'] is not None:
        if st['temp'] > LIMIT_C - 5:
            st['abort'] = 'temperature %.1f near limit' % st['temp']
        s0, ts = st['start']
        if st['temp'] < THRESH and time.time() - ts > 40 and st['temp'] - s0 < 10:
            st['abort'] = 'runaway check: %.1f C rise in %.0f s' % (st['temp'] - s0, time.time() - ts)
    if time.time() - st['t0'] > TOTAL_S:
        st['abort'] = 'time limit'
    duty = 0.0 if st['temp'] is None or st['abort'] else max(0.0, min(MAX_DUTY, (TARGET - st['temp']) * 0.05))
    if time.time() > st['next_sync']:
        io_resync(); st['next_sync'] = time.time() + 10
    io.send('queue_digital_out oid=1 clock=%d on_ticks=%d' % ((io_est() + int(1.0 * F)) & 0xffffffff, int(duty * CYCLE)))
def wait(sec):
    end = time.time() + sec
    while time.time() < end and not st['abort']:
        heat_step(); time.sleep(0.2)
def finish(msg):
    io.send('update_digital_out oid=1 value=0')
    fm.send('update_digital_out oid=3 value=0')
    fm.send('update_digital_out oid=1 value=1')
    time.sleep(0.3)
    io.send('update_digital_out oid=2 value=0')
    fm.send('reset'); io.send('reset')
    print('END: %s; last temp %.1f C; heater/clutch/driver/fan off, MCUs reset' % (msg, st['temp'] or float('nan')))
    sys.exit(0)

def e_move(d, mm, speed):
    n = int(round(mm * E_SPM)); iv = int(F / (speed * E_SPM))
    t = (fm.clock()[0] + F // 2) & 0xffffffff
    fm.send('reset_step_clock oid=0 clock=%d' % t)
    fm.send('set_next_step_dir oid=0 dir=%d' % d)
    fm.send('queue_step oid=0 interval=%d count=%d add=0' % (iv, n))
    wait(0.5 + n * iv / F + 0.1)

try:
    t_on = (fm.clock()[0] + F // 2) & 0xffffffff
    fm.send('queue_pwm_out oid=2 clock=%d value=%d' % (t_on, int(0.75 * 255)))
    fm.send('queue_digital_out oid=1 clock=%d on_ticks=0' % t_on)
    print('heating to %.0f C (feed at >= %.0f C), max duty %.0f%%' % (TARGET, THRESH, MAX_DUTY * 100))
    last = 0
    while not st['abort'] and (st['temp'] is None or st['temp'] < THRESH):
        heat_step(); time.sleep(0.2)
        if time.time() - last > 10 and st['temp'] is not None:
            print('  [%5.1fs] %6.1f C' % (time.time() - st['t0'], st['temp'])); sys.stdout.flush(); last = time.time()
    if st['abort']:
        finish('ABORT: ' + st['abort'])
    wait(5.0)       # soak
    print('at %.1f C - feeding %.0f mm at %.1f mm/s' % (st['temp'], MM, SPEED)); sys.stdout.flush()
    fm.send('update_digital_out oid=3 value=1')
    wait(0.3)
    fed = 0.0
    while fed < MM and not st['abort']:
        c = min(5.0, MM - fed)
        e_move(0, c, SPEED); fed += c
        print('  fed %5.1f mm  [%5.1fs] %6.1f C' % (fed, time.time() - st['t0'], st['temp'])); sys.stdout.flush()
    if st['abort']:
        finish('ABORT after %.0f mm: %s' % (fed, st['abort']))
    wait(1.0)
    if RETRACT:
        e_move(1, RETRACT, 40.0)
        print('  retracted %.0f mm' % RETRACT)
    fm.send('update_digital_out oid=3 value=0')
    wait(1.0)
    lever = fm.transact('endstop_query_state oid=4', 'endstop_state')['pin_value']
    finish('LOAD done: fed %.0f mm, retract %.0f mm, xena46=%d' % (fed, RETRACT, lever))
except SystemExit:
    raise
except BaseException as e:
    finish('ABORT: %r' % e)
