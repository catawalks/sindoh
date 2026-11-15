"""Start a print and watch it: printmon.py FILE LOG"""
import json, sys, time, urllib.parse, urllib.request
API = 'http://10.10.0.147:7125'
LOG = open(sys.argv[2], 'a', buffering=1)
def log(*a):
    s = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a); print(s, flush=True); LOG.write(s + '\n')
def post(path, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(API + path, data=b'', method='POST'), timeout=timeout) as r:
        return json.load(r)
def q(objs):
    with urllib.request.urlopen(API + '/printer/objects/query?' + objs, timeout=10) as r:
        return json.load(r)['result']['status']
log('--- print', sys.argv[1], 'mcu', q('mcu')['mcu']['mcu_version'])
post('/printer/gcode/script?script=' + urllib.parse.quote('BED_CLEAR'))
post('/printer/print/start?filename=' + urllib.parse.quote(sys.argv[1]))
last, t0, fails = None, time.time(), 0
while time.time() - t0 < 3000:
    time.sleep(15)
    try:
        s = q('print_stats&extruder=temperature,target&heater_bed=temperature,target&webhooks&toolhead=position')
        fails = 0
    except Exception as e:
        fails += 1; log('query failed', e)
        if fails > 8: break
        continue
    ps = s['print_stats']
    line = '%s e%.0f/%.0f b%.0f/%.0f z%.1f %ds fil%.0f %s' % (ps['state'], s['extruder']['temperature'], s['extruder']['target'],
        s['heater_bed']['temperature'], s['heater_bed']['target'], s['toolhead']['position'][2], ps['print_duration'], ps['filament_used'], ps.get('message', ''))
    if ps['state'] != last or int(time.time() - t0) % 120 < 15:
        log(line)
    last = ps['state']
    if s['webhooks']['state'] != 'ready':
        log('KLIPPER', s['webhooks']['state'], s['webhooks'].get('state_message', '')[:300]); break
    if ps['state'] in ('complete', 'error', 'cancelled'):
        break
log('--- end', last)
