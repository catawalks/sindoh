"""Small extruder step test on the real printer via the TCP bridge.
Enables the E driver (smot_en3), sets REF current (pwm31 hard PWM, stock 75 %),
steps 460 forward over ~1 s, pauses, 460 back, then disables and resets.
usage: ktest_motion.py KLIPPER_TREE PRINTER_IP [steps] [seconds]"""
import sys, time
kl, ip = sys.argv[1], sys.argv[2]
steps = int(sys.argv[3]) if len(sys.argv) > 3 else 460
secs = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
src = open(__file__.replace('ktest_motion.py', 'khost.py'), encoding='utf-8-sig').read()
src = src.split('fm = Mcu(')[0]
g = {'__name__': 'ktest'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
F = 396000000

fm = g['Mcu']('FM', 9100)
fm.identify()
cfg = fm.transact('get_config', 'config')
if cfg['is_config'] or cfg['is_shutdown']:
    fm.send('reset'); time.sleep(1.0); fm.recv(0.3)
    fm.seq = 0; fm.mcu_next = None
    fm.identify()
fm.send('allocate_oids count=3')
fm.send('config_stepper oid=0 step_pin=smot_step3 dir_pin=smot_dir3 invert_step=0 step_pulse_ticks=%d' % (2 * F // 1000000))
fm.send('config_digital_out oid=1 pin=smot_en3 value=1 default_value=1 max_duration=0')
fm.send('config_pwm_out oid=2 pin=pwm31 cycle_ticks=%d value=0 default_value=0 max_duration=0' % (F // 10000))
fm.send('finalize_config crc=0')
r = fm.transact('get_config', 'config')
print('configured: is_config=%d is_shutdown=%d' % (r['is_config'], r['is_shutdown']))

now = fm.clock()[0]
t_on = (now + F // 2) & 0xffffffff          # 0.5 s ahead (WiFi RTT is up to ~130 ms)
fm.send('queue_pwm_out oid=2 clock=%d value=191' % t_on)          # 0.75 * 255
fm.send('queue_digital_out oid=1 clock=%d on_ticks=0' % t_on)      # enable = bit0 cleared
interval = int(F * secs / steps)
t_step = (t_on + F // 2) & 0xffffffff
fm.send('reset_step_clock oid=0 clock=%d' % t_step)
fm.send('set_next_step_dir oid=0 dir=1')
fm.send('queue_step oid=0 interval=%d count=%d add=0' % (interval, steps))
# pause 0.5 s: one long first interval for the return move
fm.send('set_next_step_dir oid=0 dir=0')
fm.send('queue_step oid=0 interval=%d count=1 add=0' % (interval + F // 2))
fm.send('queue_step oid=0 interval=%d count=%d add=0' % (interval, steps - 1))
t_end = (t_step + int(F * (2 * secs + 1.0))) & 0xffffffff
fm.send('queue_pwm_out oid=2 clock=%d value=0' % t_end)
print('moving: %d steps each way, %.2f s each, interval %d ticks' % (steps, secs, interval))
time.sleep(0.5 + 0.5 + 2 * secs + 1.5)
r = fm.transact('stepper_get_position oid=0', 'stepper_position')
c = fm.transact('get_config', 'config')
print('stepper position after test: %d (expected 0), is_shutdown=%d' % (r['pos'], c['is_shutdown']))
fm.send('update_digital_out oid=1 value=1')         # disable driver
time.sleep(0.2)
fm.send('reset')                                     # also forces outputs off
print('driver disabled, MCU reset')
