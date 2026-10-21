"""Send Klipper's 'reset' to both UPC MCUs (restart_method: command) and verify they come back clean.
usage: kreset.py KLIPPER_TREE PRINTER_IP"""
import sys, time
kl, ip = sys.argv[1], sys.argv[2]
src = open(__file__.replace('kreset.py', 'khost.py'), encoding='utf-8-sig').read()
src = src.split('fm = Mcu(')[0]
g = {'__name__': 'kreset'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
for name, port in (('FM', 9100), ('IO', 9101)):
    m = g['Mcu'](name, port)
    m.identify()
    before = m.transact('get_config', 'config')
    up0 = m.transact('get_uptime', 'uptime')
    m.send('reset')
    time.sleep(1.0)
    m.recv(0.3)
    # Firmware restarted: its sequence counter starts over
    m.seq = 0; m.mcu_next = None
    m.identify()
    after = m.transact('get_config', 'config')
    up1 = m.transact('get_uptime', 'uptime')
    print('%s: before is_shutdown=%d is_config=%d uptime %d:%d -> after is_shutdown=%d is_config=%d uptime %d:%d'
          % (name, before['is_shutdown'], before['is_config'], up0['high'], up0['clock'],
             after['is_shutdown'], after['is_config'], up1['high'], up1['clock']))
