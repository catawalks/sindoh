"""Motorised levelling-probe toggle, stock sequence (engine_changelvsensor):
home X (right, xena42), X -> -10 mm, push to -20 mm at 10 mm/s, back to -5.6 mm.
Reads dsens8 before and after. Then driver off and MCU reset.
usage: ktest_lvtoggle.py KLIPPER_TREE PRINTER_IP"""
import sys, time
kl, ip = sys.argv[1], sys.argv[2]
src = open(__file__.replace('ktest_lvtoggle.py', 'khost.py'), encoding='utf-8-sig').read().split('fm = Mcu(')[0]
g = {'__name__': 'lv'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
F = 396000000
SPM = 80.0
HOME_X = 216.0

fm = g['Mcu']('FM', 9100)
fm.identify()
cfg = fm.transact('get_config', 'config')
if cfg['is_config'] or cfg['is_shutdown']:
    fm.send('reset'); time.sleep(1.0); fm.recv(0.3)
    fm.seq = 0; fm.mcu_next = None
    fm.identify()
fm.send('allocate_oids count=6')
fm.send('config_stepper oid=0 step_pin=smot_step0 dir_pin=smot_dir0 invert_step=0 step_pulse_ticks=%d' % (2 * F // 1000000))
fm.send('config_digital_out oid=1 pin=smot_en0 value=1 default_value=1 max_duration=0')
fm.send('config_pwm_out oid=2 pin=pwm27 cycle_ticks=%d value=0 default_value=0 max_duration=0' % (F // 10000))
fm.send('config_endstop oid=3 pin=xena42 pull_up=0')
fm.send('config_trsync oid=4')
fm.send('config_endstop oid=5 pin=dsens8 pull_up=0')
fm.send('finalize_config crc=0')
r = fm.transact('get_config', 'config')
if not r['is_config'] or r['is_shutdown']:
    sys.exit('config failed %r' % r)

def q(oid):
    return fm.transact('endstop_query_state oid=%d' % oid, 'endstop_state')['pin_value']
def interval(speed):
    return int(F / (speed * SPM))

lv0 = q(5)
print('dsens8 before: %d (0 = extended/deployed, 1 = latched in/stowed)' % lv0)

# enable driver + REF current
now = fm.clock()[0]
t_on = (now + F // 2) & 0xffffffff
fm.send('queue_pwm_out oid=2 clock=%d value=%d' % (t_on, int(0.425 * 255)))
fm.send('queue_digital_out oid=1 clock=%d on_ticks=0' % t_on)
time.sleep(0.7)

# 1. home X to the right switch (unless already on it)
if q(3) != 1:
    t0 = (fm.clock()[0] + F // 2) & 0xffffffff
    steps = int(260 * SPM)
    fm.send('trsync_start oid=4 report_clock=%d report_ticks=%d expire_reason=4' % (t0, F // 10))
    fm.send('stepper_stop_on_trigger oid=0 trsync_oid=4')
    fm.send('trsync_set_timeout oid=4 clock=%d' % ((t0 + 2 * F) & 0xffffffff))
    fm.send('endstop_home oid=3 clock=%d sample_ticks=%d sample_count=4 rest_ticks=%d pin_value=1 trsync_oid=4 trigger_reason=1'
            % (t0, F // 66666, F // 10000))
    fm.send('reset_step_clock oid=0 clock=%d' % t0)
    fm.send('set_next_step_dir oid=0 dir=1')
    fm.send('queue_step oid=0 interval=%d count=%d add=0' % (interval(10), steps))
    res = None; end = time.time() + 30; renew = time.time() + 0.5
    while time.time() < end and res is None:
        for m in fm.recv(0.1):
            if m['#name'] == 'trsync_state' and not m['can_trigger']:
                res = m['trigger_reason']
        if res is None and time.time() > renew:
            fm.send('trsync_set_timeout oid=4 clock=%d' % ((fm.clock()[0] + 2 * F) & 0xffffffff))
            renew = time.time() + 0.5
    if res != 1:
        fm.send('update_digital_out oid=1 value=1'); fm.send('reset')
        sys.exit('X homing did not trigger (reason %r) - aborting' % res)
    fm.send('endstop_home oid=3 clock=0 sample_ticks=0 sample_count=0 rest_ticks=0 pin_value=0 trsync_oid=0 trigger_reason=0')
    print('X homed (switch = %.1f mm)' % HOME_X)
else:
    print('X already on its switch (= %.1f mm)' % HOME_X)

# 2. stock toggle sequence (positions in mm)
seq = [(0, HOME_X - (-10.0), 20.0, 'to X -10'),
       (0, 10.0, 10.0, 'push to X -20'),
       (1, 14.4, 20.0, 'back to X -5.6')]
t = (fm.clock()[0] + F // 2) & 0xffffffff
fm.send('reset_step_clock oid=0 clock=%d' % t)
total = 0.0
for d, mm, spd, what in seq:
    n = int(round(mm * SPM))
    iv = interval(spd)
    fm.send('set_next_step_dir oid=0 dir=%d' % d)
    # first step carries a 0.3 s pause between segments
    fm.send('queue_step oid=0 interval=%d count=1 add=0' % (iv + int(0.3 * F)))
    left = n - 1
    while left:
        c = min(left, 60000)
        fm.send('queue_step oid=0 interval=%d count=%d add=0' % (iv, c))
        left -= c
    total += mm / spd + 0.3
    print('queued: %s (%.1f mm at %.0f mm/s)' % (what, mm, spd))
time.sleep(0.5 + total + 1.0)
pos = fm.transact('stepper_get_position oid=0', 'stepper_position')['pos']
lv1 = q(5)
sd = fm.transact('get_config', 'config')['is_shutdown']
fm.send('update_digital_out oid=1 value=1')
time.sleep(0.2)
fm.send('reset')
print('dsens8 after: %d  -> %s; shutdown=%d; driver off, MCU reset'
      % (lv1, 'TOGGLED' if lv1 != lv0 else 'NOT toggled', sd))
