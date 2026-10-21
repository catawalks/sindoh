"""One-way move of a single axis on the real printer, then all drivers off and MCU reset.
usage: ktest_move.py KLIPPER_TREE PRINTER_IP AXIS DIR MM [MM_PER_S]
AXIS X/Y/Z/E, DIR = raw engine direction bit (Z: 0 = bed up, 1 = bed down)."""
import sys, time
kl, ip, axis, d, mm = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), float(sys.argv[5])
speed = float(sys.argv[6]) if len(sys.argv) > 6 else 5.0
src = open(__file__.replace('ktest_move.py', 'khost.py'), encoding='utf-8-sig').read()
src = src.split('fm = Mcu(')[0]
g = {'__name__': 'ktest'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
F = 396000000
AX = {'X': (0, 27, 0.425, 80), 'Y': (1, 29, 0.575, 80), 'Z': (2, 30, 0.65, 3200), 'E': (3, 31, 0.75, 458.83)}
eng, pwm, ref, spm = AX[axis]
steps = int(round(mm * spm))
if steps > 65535:
    sys.exit('too many steps for one queue_step (max 65535)')

fm = g['Mcu']('FM', 9100)
fm.identify()
cfg = fm.transact('get_config', 'config')
if cfg['is_config'] or cfg['is_shutdown']:
    fm.send('reset'); time.sleep(1.0); fm.recv(0.3)
    fm.seq = 0; fm.mcu_next = None
    fm.identify()
fm.send('allocate_oids count=3')
fm.send('config_stepper oid=0 step_pin=smot_step%d dir_pin=smot_dir%d invert_step=0 step_pulse_ticks=%d' % (eng, eng, 2 * F // 1000000))
fm.send('config_digital_out oid=1 pin=smot_en%d value=1 default_value=1 max_duration=0' % eng)
fm.send('config_pwm_out oid=2 pin=pwm%d cycle_ticks=%d value=0 default_value=0 max_duration=0' % (pwm, F // 10000))
fm.send('finalize_config crc=0')
r = fm.transact('get_config', 'config')
if not r['is_config'] or r['is_shutdown']:
    sys.exit('config failed %r' % r)
t = mm / speed
now = fm.clock()[0]
t_on = (now + F // 2) & 0xffffffff
fm.send('queue_pwm_out oid=2 clock=%d value=%d' % (t_on, int(ref * 255)))
fm.send('queue_digital_out oid=1 clock=%d on_ticks=0' % t_on)
fm.send('reset_step_clock oid=0 clock=%d' % ((t_on + F // 2) & 0xffffffff))
fm.send('set_next_step_dir oid=0 dir=%d' % d)
fm.send('queue_step oid=0 interval=%d count=%d add=0' % (int(F * t / steps), steps))
print('%s: %d steps dir %d (%.1f mm at %.1f mm/s, %.1f s)' % (axis, steps, d, mm, speed, t))
time.sleep(1.0 + t + 0.5)
pos = fm.transact('stepper_get_position oid=0', 'stepper_position')['pos']
sd = fm.transact('get_config', 'config')['is_shutdown']
fm.send('update_digital_out oid=1 value=1')
time.sleep(0.2)
fm.send('reset')
print('done: position %d, shutdown=%d; driver disabled, MCU reset' % (pos, sd))
