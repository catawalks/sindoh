"""Connect to the UPC Klipper MCUs via the TCP bridge, identify, report config and shutdown reason.
usage: kstatus.py KLIPPER_TREE PRINTER_IP"""
import sys, time
kl, ip = sys.argv[1], sys.argv[2]
sys.argv = [sys.argv[0], kl, ip]
src = open(__file__.replace('kstatus.py', 'khost.py'), encoding='utf-8-sig').read()
src = src.split('fm = Mcu(')[0]
g = {'__name__': 'kstatus'}
exec(compile(src, 'khost.py', 'exec'), g)
for name, port in (('FM', 9100), ('IO', 9101)):
    m = g['Mcu'](name, port)
    m.identify()
    m.send('get_config')
    end = time.time() + 2
    while time.time() < end:
        for msg in m.recv(0.1):
            if msg['#name'] in ('config', 'shutdown', 'is_shutdown'):
                print(name, msg['#name'], {k: v for k, v in msg.items() if not k.startswith('#')})
    m.send('allocate_oids count=1')   # refused in shutdown -> is_shutdown with reason
    for msg in m.recv(0.5):
        if msg['#name'] in ('shutdown', 'is_shutdown'):
            print(name, 'REASON:', msg.get('static_string_id'), msg)
    m.send('get_uptime')
    for msg in m.recv(0.5):
        if msg['#name'] == 'uptime':
            print(name, 'uptime', msg)
