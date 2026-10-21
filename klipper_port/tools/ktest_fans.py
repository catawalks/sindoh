"""Fan output test on the IO core: pwm1..pwm4 switched fully on one at a time.
usage: ktest_fans.py KLIPPER_TREE PRINTER_IP [on_seconds] [blocks]"""
import sys, time
kl, ip = sys.argv[1], sys.argv[2]
ON = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0
BLOCKS = [int(b) for b in (sys.argv[4] if len(sys.argv) > 4 else '1,2,3,4').split(',')]
src = open(__file__.replace('ktest_fans.py', 'khost.py'), encoding='utf-8-sig').read()
src = src.split('fm = Mcu(')[0]
g = {'__name__': 'ktest'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)

io = g['Mcu']('IO', 9101)
io.identify()
cfg = io.transact('get_config', 'config')
if cfg['is_config'] or cfg['is_shutdown']:
    io.send('reset'); time.sleep(1.0); io.recv(0.3)
    io.seq = 0; io.mcu_next = None
    io.identify()
io.send('allocate_oids count=%d' % len(BLOCKS))
for oid, b in enumerate(BLOCKS):
    io.send('config_digital_out oid=%d pin=pwm%d value=0 default_value=0 max_duration=0' % (oid, b))
io.send('finalize_config crc=0')
r = io.transact('get_config', 'config')
if not r['is_config'] or r['is_shutdown']:
    sys.exit('config failed %r' % r)
t0 = time.time()
for n, (oid, b) in enumerate(zip(range(len(BLOCKS)), BLOCKS), 1):
    print('[%4.1fs] step %d: pwm%d ON' % (time.time() - t0, n, b)); sys.stdout.flush()
    io.send('update_digital_out oid=%d value=1' % oid)
    time.sleep(ON)
    io.send('update_digital_out oid=%d value=0' % oid)
    print('[%4.1fs]          pwm%d off' % (time.time() - t0, b)); sys.stdout.flush()
    time.sleep(2.0)
sd = io.transact('get_config', 'config')['is_shutdown']
io.send('reset')
print('done, shutdown=%d, MCU reset (all outputs off)' % sd)
