"""Cold extruder feed/retract on the real printer (FM MCU only; no heat, no X/Y/Z motion).
Clutch (pwm6) on, E (engine 3) moves MM at SPEED mm/s, clutch off, driver off, MCU reset.
DIR 0 = feed, 1 = retract (hardware_notes). Positive MM feeds, negative retracts.
usage: ktest_feed.py KLIPPER_TREE PRINTER_IP MM [speed=10]"""
import sys, time
kl, ip, MM = sys.argv[1], sys.argv[2], float(sys.argv[3])
SPEED = float(sys.argv[4]) if len(sys.argv) > 4 else 10.0
if abs(MM) > 500 or not 0 < SPEED <= 40:
    sys.exit('refusing: |MM| <= 500 and 0 < speed <= 40')
src = open(__file__.replace('ktest_feed.py', 'khost.py'), encoding='utf-8-sig').read().split('fm = Mcu(')[0]
g = {'__name__': 'feed'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
F = 396000000
E_SPM = 458.83

fm = g['Mcu']('FM', 9100)
fm.identify()
c = fm.transact('get_config', 'config')
if c['is_config'] or c['is_shutdown']:
    fm.send('reset'); time.sleep(1.0); fm.recv(0.3)
    fm.seq = 0; fm.mcu_next = None
    fm.identify()

fm.send('allocate_oids count=5')
fm.send('config_stepper oid=0 step_pin=smot_step3 dir_pin=smot_dir3 invert_step=0 step_pulse_ticks=%d' % (2 * F // 1000000))
fm.send('config_digital_out oid=1 pin=smot_en3 value=1 default_value=1 max_duration=0')
fm.send('config_pwm_out oid=2 pin=pwm31 cycle_ticks=%d value=0 default_value=0 max_duration=0' % (F // 10000))
fm.send('config_digital_out oid=3 pin=pwm6 value=0 default_value=0 max_duration=0')       # clutch
fm.send('config_endstop oid=4 pin=xena46 pull_up=0')                                      # cartridge lever
fm.send('finalize_config crc=0')
r = fm.transact('get_config', 'config')
if not r['is_config'] or r['is_shutdown']:
    sys.exit('FM config failed %r' % r)

def finish(msg):
    fm.send('update_digital_out oid=3 value=0')
    fm.send('update_digital_out oid=1 value=1')
    time.sleep(0.3)
    fm.send('reset')
    print('END: %s; clutch off, driver off, MCU reset' % msg)

try:
    t_on = (fm.clock()[0] + F // 2) & 0xffffffff
    fm.send('queue_pwm_out oid=2 clock=%d value=%d' % (t_on, int(0.75 * 255)))
    fm.send('queue_digital_out oid=1 clock=%d on_ticks=0' % t_on)
    fm.send('update_digital_out oid=3 value=1')
    time.sleep(0.8)
    n = int(round(abs(MM) * E_SPM)); iv = int(F / (SPEED * E_SPM))
    d = 0 if MM > 0 else 1
    print('%s %.0f mm at %.0f mm/s (%d steps, %.1f s)' % ('feeding' if d == 0 else 'retracting', abs(MM), SPEED, n, n * iv / F))
    sys.stdout.flush()
    t = (fm.clock()[0] + F // 2) & 0xffffffff
    fm.send('reset_step_clock oid=0 clock=%d' % t)
    fm.send('set_next_step_dir oid=0 dir=%d' % d)
    left = n
    while left:
        cnt = min(left, 60000)
        fm.send('queue_step oid=0 interval=%d count=%d add=0' % (iv, cnt)); left -= cnt
    time.sleep(0.5 + n * iv / F + 0.5)
    r = fm.transact('get_config', 'config')
    pos = fm.transact('stepper_get_position oid=0', 'stepper_position')['pos']
    lever = fm.transact('endstop_query_state oid=4', 'endstop_state')['pin_value']
    finish('moved, stepper pos %d (|pos| should be %d), is_shutdown=%d, xena46=%d'
           % (pos, n, r['is_shutdown'], lever))
except BaseException as e:
    finish('ABORT: %r' % e)
    raise
