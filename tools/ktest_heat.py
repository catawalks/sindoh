"""Capped heater test on the IO core with layered safety.
usage: ktest_heat.py KLIPPER_TREE PRINTER_IP PRINTER_CFG [nozzle|bed] [target_C] [max_duty]
Safety: MCU max_duration (2 s) on the heater pin, MCU ADC range check (shutdown above
LIMIT_C or on open/short thermistor), PC runaway check, total time limit, final reset."""
import re, sys, time
kl, ip, cfgpath = sys.argv[1], sys.argv[2], sys.argv[3]
which = sys.argv[4] if len(sys.argv) > 4 else 'nozzle'
TARGET = float(sys.argv[5]) if len(sys.argv) > 5 else (60.0 if which == 'nozzle' else 45.0)
MAX_DUTY = float(sys.argv[6]) if len(sys.argv) > 6 else 0.30
LIMIT_C = TARGET + 20.0          # MCU range-check cutoff
HOLD_S, TOTAL_S = 20.0, 150.0
RUNAWAY_S, RUNAWAY_MIN_RISE = 25.0, 2.0
src = open(__file__.replace('ktest_heat.py', 'khost.py'), encoding='utf-8-sig').read()
src = src.split('fm = Mcu(')[0]
g = {'__name__': 'ktest'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
F = 396000000

# Thermistor table from printer.cfg (temperatureN / voltageN, voltage = raw/1023)
sect = 'dp200_nozzle' if which == 'nozzle' else 'dp200_bed'
txt = open(cfgpath, encoding='utf-8').read()
blk = txt.split('[adc_temperature %s]' % sect)[1].split('\n[')[0]
T = [float(x) for x in re.findall(r'temperature\d+:\s*([-\d.]+)', blk)]
V = [float(x) for x in re.findall(r'voltage\d+:\s*([-\d.]+)', blk)]
pts = sorted(zip(V, T))                      # ascending voltage = descending temp

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
    raise SystemExit('temperature %.1f outside table' % t)

heater_pin, adc_pin = ('pwm5', 'adc0') if which == 'nozzle' else ('pwm24', 'adc1')
min_sum = int(raw_for(LIMIT_C) * 8)          # hotter than LIMIT_C -> lower raw
max_sum = 1015 * 8                           # raw ~1015+ = open thermistor (0 C is ~1008)

io = g['Mcu']('IO', 9101)
io.identify()
cfg = io.transact('get_config', 'config')
if cfg['is_config'] or cfg['is_shutdown']:
    io.send('reset'); time.sleep(1.0); io.recv(0.3)
    io.seq = 0; io.mcu_next = None
    io.identify()
io.send('allocate_oids count=3')
io.send('config_analog_in oid=0 pin=%s' % adc_pin)
io.send('config_digital_out oid=1 pin=%s value=0 default_value=0 max_duration=%d' % (heater_pin, 2 * F))
io.send('config_digital_out oid=2 pin=pwm1 value=0 default_value=0 max_duration=0')   # hotend fan
io.send('finalize_config crc=0')
r = io.transact('get_config', 'config')
if not r['is_config'] or r['is_shutdown']:
    sys.exit('config failed %r' % r)
CYCLE = F // 10
io.send('set_digital_out_pwm_cycle oid=1 cycle_ticks=%d' % CYCLE)
now = io.clock()[0]
io.send('query_analog_in oid=0 clock=%d sample_ticks=%d sample_count=8 rest_ticks=%d bytes_per_report=2'
        ' min_value=%d max_value=%d range_check_count=4'
        % ((now + F // 5) & 0xffffffff, F // 1000, int(F * 0.3), min_sum, max_sum))
if which == 'nozzle':
    io.send('update_digital_out oid=2 value=1')
print('%s heater test: target %.0f C, max duty %.0f%%, MCU cutoff %.0f C (raw sum < %d)'
      % (which, TARGET, MAX_DUTY * 100, LIMIT_C, min_sum))

# Estimate the MCU clock locally (as klippy does) instead of querying it over
# WiFi every loop; schedule heater updates LEAD seconds ahead.
LEAD = 0.6
sync = {}
def resync():
    c, t, _ = io.clock()
    sync.update(c=c, t=t)
def est_clock():
    return (sync['c'] + int((time.time() - sync['t']) * F)) & 0xffffffff
resync()
t0 = time.time(); last_temp = None; start_temp = None; next_sync = t0 + 10
reached = None; abort = None; trace = []
while True:
    el = time.time() - t0
    for m in io.recv(0.05):
        if m['#name'] in ('shutdown', 'is_shutdown'):
            abort = 'MCU shutdown: %s' % m.get('static_string_id')
        if m['#name'] == 'analog_in_state':
            last_temp = temp(int.from_bytes(bytes(m['values'][:2]), 'little') / 8.0)
            if start_temp is None:
                start_temp = last_temp
    if abort:
        break
    if last_temp is None:
        if el > 3:
            abort = 'no temperature reports'
            break
        continue
    if last_temp > LIMIT_C - 5:
        abort = 'temperature %.1f C near limit' % last_temp
        break
    if el > RUNAWAY_S and reached is None and last_temp - start_temp < RUNAWAY_MIN_RISE:
        abort = 'runaway check: only %.1f C rise after %.0f s' % (last_temp - start_temp, el)
        break
    if reached is None and last_temp >= TARGET:
        reached = el
    if reached is not None and el - reached > HOLD_S:
        break
    if el > TOTAL_S:
        abort = 'time limit'
        break
    duty = max(0.0, min(MAX_DUTY, (TARGET - last_temp) * 0.05))   # P control
    # refresh the heater command every loop (MCU turns it off after 2 s without one)
    if time.time() > next_sync:
        resync(); next_sync = time.time() + 10
    io.send('queue_digital_out oid=1 clock=%d on_ticks=%d'
            % ((est_clock() + int(LEAD * F)) & 0xffffffff, int(duty * CYCLE)))
    if not trace or el - trace[-1][0] >= 5:
        trace.append((el, last_temp, duty))
        print('[%5.1fs] %6.1f C  duty %3.0f%%' % (el, last_temp, duty * 100)); sys.stdout.flush()
    time.sleep(0.25)

io.send('update_digital_out oid=1 value=0')
time.sleep(0.2)
io.send('update_digital_out oid=2 value=0')
io.send('reset')
print('END: %s; last %.1f C (start %.1f C); heater off, MCU reset'
      % (abort or ('held %.0f s at target' % HOLD_S), last_temp or float('nan'), start_temp or float('nan')))
