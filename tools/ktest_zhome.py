"""Klipper-style Z homing test (MCU stops the stepper via trsync when xena44 triggers).
Bed rises (DIR 0) at SPEED mm/s for at most MAX_MM. Then driver off, MCU reset.
usage: ktest_zhome.py KLIPPER_TREE PRINTER_IP [max_mm] [mm_per_s] [pin_value]"""
import sys, time
kl, ip = sys.argv[1], sys.argv[2]
MAX_MM = float(sys.argv[3]) if len(sys.argv) > 3 else 140.0
SPEED = float(sys.argv[4]) if len(sys.argv) > 4 else 5.0
PIN_VALUE = int(sys.argv[5]) if len(sys.argv) > 5 else 1
src = open(__file__.replace('ktest_zhome.py', 'khost.py'), encoding='utf-8-sig').read()
src = src.split('fm = Mcu(')[0]
g = {'__name__': 'ktest'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
F = 396000000
SPM = 3200

fm = g['Mcu']('FM', 9100)
fm.identify()
cfg = fm.transact('get_config', 'config')
if cfg['is_config'] or cfg['is_shutdown']:
    fm.send('reset'); time.sleep(1.0); fm.recv(0.3)
    fm.seq = 0; fm.mcu_next = None
    fm.identify()
fm.send('allocate_oids count=5')
fm.send('config_stepper oid=0 step_pin=smot_step2 dir_pin=smot_dir2 invert_step=0 step_pulse_ticks=%d' % (2 * F // 1000000))
fm.send('config_digital_out oid=1 pin=smot_en2 value=1 default_value=1 max_duration=0')
fm.send('config_pwm_out oid=2 pin=pwm30 cycle_ticks=%d value=0 default_value=0 max_duration=0' % (F // 10000))
fm.send('config_endstop oid=3 pin=xena44 pull_up=0')
fm.send('config_trsync oid=4')
fm.send('finalize_config crc=0')
r = fm.transact('get_config', 'config')
if not r['is_config'] or r['is_shutdown']:
    sys.exit('config failed %r' % r)

pv = fm.transact('endstop_query_state oid=3', 'endstop_state')['pin_value']
print('Z endstop xena44 before homing: %d (trigger value %d)' % (pv, PIN_VALUE))
if pv == PIN_VALUE:
    fm.send('reset')
    sys.exit('endstop already reads the trigger value - not moving')

steps = int(MAX_MM * SPM)
interval = int(F / (SPEED * SPM))
move_t = steps * interval / F
now = fm.clock()[0]
t_on = (now + F // 2) & 0xffffffff
t0 = (t_on + F // 2) & 0xffffffff
fm.send('queue_pwm_out oid=2 clock=%d value=%d' % (t_on, int(0.65 * 255)))
fm.send('queue_digital_out oid=1 clock=%d on_ticks=0' % t_on)
fm.send('trsync_start oid=4 report_clock=%d report_ticks=%d expire_reason=4' % (t0, F // 10))
fm.send('stepper_stop_on_trigger oid=0 trsync_oid=4')
# At 396 MHz a 32-bit clock can only be scheduled < 2^31 ticks (5.4 s) ahead,
# so the safety timeout is kept short and renewed while homing (as klippy does).
fm.send('trsync_set_timeout oid=4 clock=%d' % ((t0 + 2 * F) & 0xffffffff))
fm.send('endstop_home oid=3 clock=%d sample_ticks=%d sample_count=4 rest_ticks=%d pin_value=%d trsync_oid=4 trigger_reason=1'
        % (t0, F // 66666, F // 10000, PIN_VALUE))
fm.send('reset_step_clock oid=0 clock=%d' % t0)
fm.send('set_next_step_dir oid=0 dir=0')
left = steps
while left:
    n = min(left, 60000)
    fm.send('queue_step oid=0 interval=%d count=%d add=0' % (interval, n))
    left -= n
print('homing: up to %.0f mm at %.1f mm/s (max %.1f s)' % (MAX_MM, SPEED, move_t))

result = None
end = time.time() + 1.0 + move_t + 4.0
next_renew = time.time() + 0.5
while time.time() < end and result is None:
    for m in fm.recv(0.1):
        if m['#name'] == 'trsync_state' and not m['can_trigger']:
            result = m
            break
        if m['#name'] in ('shutdown', 'is_shutdown'):
            result = {'trigger_reason': 'MCU shutdown: %s' % m.get('static_string_id')}
            break
    if result is None and time.time() > next_renew:
        # Renew the trsync timeout 2 s ahead (stops the move if this PC goes away)
        c = fm.clock()[0]
        fm.send('trsync_set_timeout oid=4 clock=%d' % ((c + 2 * F) & 0xffffffff))
        next_renew = time.time() + 0.5
pos = fm.transact('stepper_get_position oid=0', 'stepper_position')['pos']
pv = fm.transact('endstop_query_state oid=3', 'endstop_state')['pin_value']
fm.send('update_digital_out oid=1 value=1')
time.sleep(0.2)
fm.send('reset')
if result is None:
    print('no trsync result; position %d steps (%.1f mm)' % (pos, pos / SPM))
else:
    why = {1: 'ENDSTOP TRIGGERED', 4: 'timeout (no trigger)'}.get(result['trigger_reason'], result['trigger_reason'])
    print('result: %s; travelled %.2f mm (%d steps); endstop now %d; driver off, MCU reset'
          % (why, -pos / SPM, pos, pv))
