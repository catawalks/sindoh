"""Heated filament unload on the real printer, stock sequence (engine_filaUnload + FM cmd 0x13).
FM MCU: X/Z park, E retract, clutch (pwm6), filament sensor xena46 (0 = present).
IO MCU: nozzle heater (pwm5) + thermistor (adc0), hotend fan (pwm1).
usage: ktest_unload.py KLIPPER_TREE PRINTER_IP PRINTER_CFG [target_C] [max_duty]"""
import re, sys, time
kl, ip, cfgpath = sys.argv[1], sys.argv[2], sys.argv[3]
TARGET = float(sys.argv[4]) if len(sys.argv) > 4 else 230.0
MAX_DUTY = float(sys.argv[5]) if len(sys.argv) > 5 else 0.60
THRESH = TARGET - 20.0                 # stock wait threshold (210 for PLA 230)
LIMIT_C = TARGET + 20.0                # MCU range-check cutoff
TOTAL_S = 360.0
src = open(__file__.replace('ktest_unload.py', 'khost.py'), encoding='utf-8-sig').read().split('fm = Mcu(')[0]
g = {'__name__': 'unload'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
F = 396000000
E_SPM, X_SPM, Z_SPM = 458.83, 80.0, 3200.0

# thermistor table from printer.cfg
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

# ---- FM config: X, Z, E steppers, enables, REF currents, X endstop, clutch, filament sensor
fm.send('allocate_oids count=14')
for oid, (eng, en_oid) in enumerate(((0, 3), (2, 4), (3, 5))):
    fm.send('config_stepper oid=%d step_pin=smot_step%d dir_pin=smot_dir%d invert_step=0 step_pulse_ticks=%d'
            % (oid, eng, eng, 2 * F // 1000000))
    fm.send('config_digital_out oid=%d pin=smot_en%d value=1 default_value=1 max_duration=0' % (en_oid, eng))
for oid, (blkno, duty) in enumerate(((27, 0.425), (30, 0.65), (31, 0.75)), 6):
    fm.send('config_pwm_out oid=%d pin=pwm%d cycle_ticks=%d value=0 default_value=0 max_duration=0' % (oid, blkno, F // 10000))
fm.send('config_endstop oid=9 pin=xena42 pull_up=0')
fm.send('config_trsync oid=10')
fm.send('config_digital_out oid=11 pin=pwm6 value=0 default_value=0 max_duration=0')      # clutch
fm.send('config_endstop oid=12 pin=xena46 pull_up=0')                                     # filament sensor
fm.send('config_endstop oid=13 pin=dsens8 pull_up=0')
fm.send('finalize_config crc=0')
# ---- IO config: nozzle ADC, heater (2 s watchdog), hotend fan
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
        % ((now + F // 5) & 0xffffffff, F // 1000, int(F * 0.3), int(raw_for(LIMIT_C) * 8), 1015 * 8))
io.send('update_digital_out oid=2 value=1')       # hotend fan on

def q(oid):
    return fm.transact('endstop_query_state oid=%d' % oid, 'endstop_state')['pin_value']

# ---- shared state + heater loop step (called from every wait)
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
    io.send('queue_digital_out oid=1 clock=%d on_ticks=%d' % ((io_est() + int(0.6 * F)) & 0xffffffff, int(duty * CYCLE)))
def wait(sec):
    end = time.time() + sec
    while time.time() < end and not st['abort']:
        heat_step(); time.sleep(0.2)
def finish(msg):
    io.send('update_digital_out oid=1 value=0')
    fm.send('update_digital_out oid=11 value=0')
    for oid in (3, 4, 5):
        fm.send('update_digital_out oid=%d value=1' % oid)
    time.sleep(0.3)
    io.send('update_digital_out oid=2 value=0')
    fm.send('reset'); io.send('reset')
    print('END: %s; last temp %.1f C; heater/clutch/fan off, MCUs reset' % (msg, st['temp'] or float('nan')))
    sys.exit(0)

# ---- FM motion helper (one stepper at a time, uniform speed)
fm_t = {'next': None}
def fm_move(oid, d, mm, speed, spm):
    n = int(round(abs(mm) * spm)); iv = int(F / (speed * spm))
    t = (fm.clock()[0] + F // 2) & 0xffffffff
    fm.send('reset_step_clock oid=%d clock=%d' % (oid, t))
    fm.send('set_next_step_dir oid=%d dir=%d' % (oid, d))
    left = n
    while left:
        c = min(left, 60000)
        fm.send('queue_step oid=%d interval=%d count=%d add=0' % (oid, iv, c)); left -= c
    wait(0.5 + n * iv / F + 0.3)

# enable drivers + REF
t_on = (fm.clock()[0] + F // 2) & 0xffffffff
for oid, duty in ((6, 0.425), (7, 0.65), (8, 0.75)):
    fm.send('queue_pwm_out oid=%d clock=%d value=%d' % (oid, t_on, int(duty * 255)))
for oid in (3, 4, 5):
    fm.send('queue_digital_out oid=%d clock=%d on_ticks=0' % (oid, t_on))
wait(0.8)
print('filament sensor xena46 = %d (0 = present), probe dsens8 = %d' % (q(12), q(13)))

# 1. park: home X right, X -> 229 (13 mm right of the switch), Z down 10 mm (23.1)
if q(9) != 1:
    t0 = (fm.clock()[0] + F // 2) & 0xffffffff
    fm.send('trsync_start oid=10 report_clock=%d report_ticks=%d expire_reason=4' % (t0, F // 10))
    fm.send('stepper_stop_on_trigger oid=0 trsync_oid=10')
    fm.send('trsync_set_timeout oid=10 clock=%d' % ((t0 + 2 * F) & 0xffffffff))
    fm.send('endstop_home oid=9 clock=%d sample_ticks=%d sample_count=4 rest_ticks=%d pin_value=1 trsync_oid=10 trigger_reason=1'
            % (t0, F // 66666, F // 10000))
    fm.send('reset_step_clock oid=0 clock=%d' % t0)
    fm.send('set_next_step_dir oid=0 dir=1')
    fm.send('queue_step oid=0 interval=%d count=%d add=0' % (int(F / (20 * X_SPM)), int(260 * X_SPM)))
    res = None; end = time.time() + 20; renew = time.time() + 0.5
    while time.time() < end and res is None and not st['abort']:
        for m in fm.recv(0.05):
            if m['#name'] == 'trsync_state' and not m['can_trigger']:
                res = m['trigger_reason']
        heat_step()
        if res is None and time.time() > renew:
            fm.send('trsync_set_timeout oid=10 clock=%d' % ((fm.clock()[0] + 2 * F) & 0xffffffff))
            renew = time.time() + 0.5
    fm.send('endstop_home oid=9 clock=0 sample_ticks=0 sample_count=0 rest_ticks=0 pin_value=0 trsync_oid=0 trigger_reason=0')
    if res != 1:
        finish('X homing failed (%r)' % res)
print('X homed at 216.0 mm')
fm_move(0, 1, 229.0 - 216.0, 20, X_SPM)
fm_move(1, 1, 10.0, 5, Z_SPM)
print('parked at X 229.0, bed lowered 10 mm')

# 2. heat
print('heating to %.0f C (start unloading at >= %.0f C), max duty %.0f%%' % (TARGET, THRESH, MAX_DUTY * 100))
last = 0
while not st['abort'] and (st['temp'] is None or st['temp'] < THRESH):
    heat_step(); time.sleep(0.2)
    if time.time() - last > 10 and st['temp'] is not None:
        print('  [%5.1fs] %6.1f C' % (time.time() - st['t0'], st['temp'])); sys.stdout.flush(); last = time.time()
if st['abort']:
    finish('ABORT: ' + st['abort'])
print('at %.1f C - unloading' % st['temp'])

# 3. retract: clutch on, 50 mm @10 mm/s, then 20 mm chunks @25 mm/s until sensor empty for 50 mm (max 420)
fm.send('update_digital_out oid=11 value=1')
wait(0.3)
fm_move(2, 1, 50.0, 10, E_SPM)
moved, after, cleared_at = 50.0, 0.0, None
while not st['abort']:
    empty = q(12) == 1
    if empty and cleared_at is None:
        cleared_at = moved
        print('  filament left the sensor after %.0f mm' % moved)
    if empty:
        after += 20.0
    if after > 50.0:
        break
    if moved >= 420.0:
        finish('UNLOAD FAILED: filament still at the sensor after %.0f mm' % moved)
    fm_move(2, 1, 20.0, 25, E_SPM)
    moved += 20.0
if st['abort']:
    finish('ABORT: ' + st['abort'])
finish('UNLOAD COMPLETE: retracted %.0f mm, sensor cleared at %s mm (sensor_to_nozzle estimate)'
       % (moved, '%.0f' % cleared_at if cleared_at is not None else '?'))
