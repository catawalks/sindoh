"""Read input pins through Klipper endstop queries on the FM MCU.
usage: ksense.py KLIPPER_TREE PRINTER_IP [pin ...]   (default: switches + sensors)"""
import sys, time
kl, ip = sys.argv[1], sys.argv[2]
pins = sys.argv[3:] or ['xena42', 'xena43', 'xena44', 'xena46', 'dsens8', 'dsens0', 'dsens1', 'dsens7']
src = open(__file__.replace('ksense.py', 'khost.py'), encoding='utf-8-sig').read().split('fm = Mcu(')[0]
g = {'__name__': 'ksense'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
fm = g['Mcu']('FM', 9100)
fm.identify()
cfg = fm.transact('get_config', 'config')
if cfg['is_config'] or cfg['is_shutdown']:
    fm.send('reset'); time.sleep(1.0); fm.recv(0.3)
    fm.seq = 0; fm.mcu_next = None
    fm.identify()
fm.send('allocate_oids count=%d' % len(pins))
for oid, p in enumerate(pins):
    fm.send('config_endstop oid=%d pin=%s pull_up=0' % (oid, p))
fm.send('finalize_config crc=0')
for oid, p in enumerate(pins):
    r = fm.transact('endstop_query_state oid=%d' % oid, 'endstop_state')
    print('%-8s = %d' % (p, r['pin_value']))
fm.send('reset')
