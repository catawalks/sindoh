"""Small X/Y/Z out-and-back moves on the real printer via the TCP bridge.
Each axis: 2 mm away from its home end at 4 mm/s, 0.5 s pause, back; endstop
read before / after the outward leg / at the end. Then driver off and reset.
usage: ktest_xyz.py KLIPPER_TREE PRINTER_IP [mm] [mm_per_s] [axes]"""
import sys, time
kl, ip = sys.argv[1], sys.argv[2]
MM = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
SPEED = float(sys.argv[4]) if len(sys.argv) > 4 else 4.0
AXES = sys.argv[5] if len(sys.argv) > 5 else 'XYZ'
src = open(__file__.replace('ktest_xyz.py', 'khost.py'), encoding='utf-8-sig').read()
src = src.split('fm = Mcu(')[0]
g = {'__name__': 'ktest'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
F = 396000000

# axis: engine, REF pwm block, REF value (0-255), steps/mm, DIR value for "away from home", endstop
AX = {
    'X': (0, 27, int(0.425 * 255), 80, 0, 'xena42'),     # homes to MAX -> move negative first
    'Y': (1, 29, int(0.575 * 255), 80, 1, 'xena43'),     # homes to MIN -> move positive first
    'Z': (2, 30, int(0.65 * 255), 3200, 1, 'xena44'),    # homes to MIN -> move positive first
}

fm = g['Mcu']('FM', 9100)
fm.identify()

def fresh():
    cfg = fm.transact('get_config', 'config')
    if cfg['is_config'] or cfg['is_shutdown']:
        fm.send('reset'); time.sleep(1.0); fm.recv(0.3)
        fm.seq = 0; fm.mcu_next = None
        fm.identify()

def endstop():
    return fm.transact('endstop_query_state oid=3', 'endstop_state')['pin_value']

import re
# AXES like "XYZ" or "YZ-": a trailing '-' reverses that axis' first direction
for name, rev in re.findall(r'([XYZ])(-?)', AXES):
    eng, pwm, ref, spm, away, es = AX[name]
    if rev:
        away = 1 - away
    fresh()
    fm.send('allocate_oids count=4')
    fm.send('config_stepper oid=0 step_pin=smot_step%d dir_pin=smot_dir%d invert_step=0 step_pulse_ticks=%d'
            % (eng, eng, 2 * F // 1000000))
    fm.send('config_digital_out oid=1 pin=smot_en%d value=1 default_value=1 max_duration=0' % eng)
    fm.send('config_pwm_out oid=2 pin=pwm%d cycle_ticks=%d value=0 default_value=0 max_duration=0' % (pwm, F // 10000))
    fm.send('config_endstop oid=3 pin=%s pull_up=0' % es)
    fm.send('finalize_config crc=0')
    r = fm.transact('get_config', 'config')
    if not r['is_config'] or r['is_shutdown']:
        sys.exit('%s: config failed %r' % (name, r))
    steps = int(round(MM * spm))
    leg = MM / SPEED
    interval = int(F * leg / steps)
    e0 = endstop()
    now = fm.clock()[0]
    t_on = (now + F // 2) & 0xffffffff
    fm.send('queue_pwm_out oid=2 clock=%d value=%d' % (t_on, ref))
    fm.send('queue_digital_out oid=1 clock=%d on_ticks=0' % t_on)
    t_step = (t_on + F // 2) & 0xffffffff
    fm.send('reset_step_clock oid=0 clock=%d' % t_step)
    fm.send('set_next_step_dir oid=0 dir=%d' % away)
    fm.send('queue_step oid=0 interval=%d count=%d add=0' % (interval, steps))
    fm.send('set_next_step_dir oid=0 dir=%d' % (1 - away))
    fm.send('queue_step oid=0 interval=%d count=1 add=0' % (interval + F // 2))
    fm.send('queue_step oid=0 interval=%d count=%d add=0' % (interval, steps - 1))
    # endstop after the outward leg (during the pause)
    time.sleep(0.5 + 0.5 + leg + 0.15)
    e1 = endstop()
    time.sleep(0.5 + leg + 0.4)
    e2 = endstop()
    pos = fm.transact('stepper_get_position oid=0', 'stepper_position')['pos']
    sd = fm.transact('get_config', 'config')['is_shutdown']
    fm.send('update_digital_out oid=1 value=1')
    fm.send('queue_pwm_out oid=2 clock=%d value=0' % ((fm.clock()[0] + F // 5) & 0xffffffff))
    time.sleep(0.4)
    print('%s: %d steps each way (%.1f mm, %.2f s/leg), dir %d first; endstop %s before=%d out=%d end=%d; '
          'position %d, shutdown=%d' % (name, steps, MM, leg, away, es, e0, e1, e2, pos, sd))
    time.sleep(1.0)
fm.send('reset')
print('drivers disabled, MCU reset')
