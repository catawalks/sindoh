"""Read input pins through Klipper's buttons module (what filament sensors use) and print changes.
Read-only: nothing moves or heats.
usage: kbuttons.py KLIPPER_TREE PRINTER_IP [seconds=10] [pin ...]   (default xena46 dsens7)"""
import sys, time
kl, ip = sys.argv[1], sys.argv[2]
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
pins = sys.argv[4:] or ['xena46', 'dsens7']
src = open(__file__.replace('kbuttons.py', 'khost.py'), encoding='utf-8-sig').read().split('fm = Mcu(')[0]
g = {'__name__': 'kbuttons'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
F = 396000000
fm = g['Mcu']('FM', 9100)
fm.identify()
c = fm.transact('get_config', 'config')
if c['is_config'] or c['is_shutdown']:
    fm.send('reset'); time.sleep(1.0); fm.recv(0.3)
    fm.seq = 0; fm.mcu_next = None
    fm.identify()
fm.send('allocate_oids count=1')
fm.send('config_buttons oid=0 button_count=%d' % len(pins))
for i, p in enumerate(pins):
    fm.send('buttons_add oid=0 pos=%d pin=%s pull_up=0' % (i, p))
fm.send('finalize_config crc=0')
# klippy buttons.py: sample every 2 ms, report after 4 equal samples (QUERY_TIME 0.002, RETRANSMIT 50)
fm.send('buttons_query oid=0 clock=%d rest_ticks=%d retransmit_count=50 invert=0'
        % ((fm.clock()[0] + F // 2) & 0xffffffff, F // 500))
ack = 0; last = None; t0 = time.time(); n = 0
while time.time() - t0 < secs:
    for m in fm.recv(0.05):
        if m['#name'] == 'buttons_state':
            # same bookkeeping as klippy/extras/buttons.py handle_buttons_state
            diff = (m['ack_count'] - ack) & 0xff
            if diff & 0x80:
                diff -= 0x100
            states = bytes(m['state'])
            new_count = ack + diff + len(states) - ack
            if new_count <= 0:
                continue
            fm.send('buttons_ack oid=0 count=%d' % new_count)
            ack += new_count
            for s in states[-new_count:]:
                bits = ' '.join('%s=%d' % (p, (s >> i) & 1) for i, p in enumerate(pins))
                print('%6.2f s  %s' % (time.time() - t0, bits)); sys.stdout.flush()
                n += 1
r = fm.transact('get_config', 'config')
print('%d state reports, is_shutdown=%d' % (n, r['is_shutdown']))
fm.send('reset')
