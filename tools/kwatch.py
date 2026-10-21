"""Watch every input pin on the FM MCU and print changes (read-only: nothing moves or heats).
Reads xena0..63 (XIRD/XIRD1) and dsens0..31 (dec_sensor +0x210) through endstop queries.
usage: kwatch.py KLIPPER_TREE PRINTER_IP [seconds=60]"""
import sys, time
kl, ip = sys.argv[1], sys.argv[2]
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0
src = open(__file__.replace('kwatch.py', 'khost.py'), encoding='utf-8-sig').read().split('fm = Mcu(')[0]
g = {'__name__': 'kwatch'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
msgproto = g['msgproto']
fm = g['Mcu']('FM', 9100)
fm.identify()
cfg = fm.transact('get_config', 'config')
if cfg['is_config'] or cfg['is_shutdown']:
    fm.send('reset'); time.sleep(1.0); fm.recv(0.3)
    fm.seq = 0; fm.mcu_next = None
    fm.identify()
pins = ['xena%d' % i for i in range(64)] + ['dsens%d' % i for i in range(32)]
fm.send('allocate_oids count=%d' % len(pins))
for oid, p in enumerate(pins):
    fm.send('config_endstop oid=%d pin=%s pull_up=0' % (oid, p))
fm.send('finalize_config crc=0')

def send_multi(cmds):
    # Several commands per frame; pace frames to stay inside the 192-byte receive window
    blk = []
    for c in cmds:
        blk += fm.p.create_command(c)
    frame = [msgproto.MESSAGE_MIN + len(blk), (fm.seq & 0x0f) | msgproto.MESSAGE_DEST] + blk
    frame += msgproto.crc16_ccitt(frame) + [msgproto.MESSAGE_SYNC]
    fm.seq = (fm.seq + 1) & 0x0f
    fm.s.sendall(bytes(frame))

def sweep():
    vals = {}
    for i in range(0, len(pins), 12):
        send_multi(['endstop_query_state oid=%d' % o for o in range(i, min(i + 12, len(pins)))])
        for m in fm.recv(0.08):
            if m['#name'] == 'endstop_state':
                vals[m['oid']] = m['pin_value']
    end = time.time() + 1.0
    while len(vals) < len(pins) and time.time() < end:
        for m in fm.recv(0.05):
            if m['#name'] == 'endstop_state':
                vals[m['oid']] = m['pin_value']
    if len(vals) < len(pins) and fm.mcu_next is not None:
        fm.seq = fm.mcu_next
    return vals

base = sweep()
print('baseline (%d/%d pins):' % (len(base), len(pins)))
print('  high: ' + ' '.join(pins[o] for o in sorted(base) if base[o]))
last = dict(base)
t0 = time.time()
print('watching for %.0f s ...' % secs); sys.stdout.flush()
while time.time() - t0 < secs:
    v = sweep()
    for o in sorted(v):
        if o in last and v[o] != last[o]:
            print('%6.1f s  %-8s %d -> %d' % (time.time() - t0, pins[o], last[o], v[o]))
            sys.stdout.flush()
        last[o] = v[o]
print('final high: ' + ' '.join(pins[o] for o in sorted(last) if last[o]))
fm.send('reset')
