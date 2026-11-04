"""FM load during a fixed motion pattern (bed empty): mcu_awake / task_avg
sampled each second from klippy's MCU stats while the moves run.
usage: loadtest.py LOG"""
import json, sys, threading, time, urllib.parse, urllib.request
API = 'http://10.10.0.21:7125'   # direct: nginx cuts requests at 60 s
LOG = open(sys.argv[1], 'a', buffering=1)

def log(*a):
    s = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a)
    print(s, flush=True); LOG.write(s + '\n')

def gc(script, timeout=300):
    url = API + '/printer/gcode/script?script=' + urllib.parse.quote(script)
    with urllib.request.urlopen(urllib.request.Request(url, data=b'', method='POST'), timeout=timeout) as r:
        return json.load(r)

def stats():
    with urllib.request.urlopen(API + '/printer/objects/query?mcu&mcu%20io', timeout=5) as r:
        s = json.load(r)['result']['status']
    return s['mcu'], s['mcu io']

def pattern(reps):
    # diagonals (X and Y together) at travel speed, then short print-speed
    # zig-zags, then long single-axis travels at 208 mm/s
    out = ['G90', 'SET_VELOCITY_LIMIT VELOCITY=210 ACCEL=1500']
    for _ in range(reps):
        out += ['G1 X30 Y30 F9000', 'G1 X190 Y170 F9000', 'G1 X30 Y170 F9000', 'G1 X190 Y30 F9000']
        for k in range(10):
            out += ['G1 X%d Y%d F1800' % (100 + (k % 2) * 20, 80 + k * 2)]
        out += ['G1 X20 Y100 F12480', 'G1 X200 Y100 F12480', 'G1 X110 Y20 F12480', 'G1 X110 Y180 F12480']
    out += ['M400']
    return '\n'.join(out)

log('--- load test, mcu %s' % stats()[0]['mcu_version'])
gc('BED_CLEAR\nG28', 180)
gc('G90\nG1 Z10 F600\nG1 X110 Y100 F6000\nM400')
idle = [stats()[0]['last_stats'] for _ in range(3) if not time.sleep(1)]
samples = []
done = threading.Event()
def sampler():
    while not done.is_set():
        try:
            samples.append(stats()[0]['last_stats'])
        except Exception:
            pass
        time.sleep(1)
t = threading.Thread(target=sampler, daemon=True); t.start()
t0 = time.time()
gc(pattern(6), 600)
done.set(); t.join()
aw = [s.get('mcu_awake', 0) for s in samples]
ta = [s.get('mcu_task_avg', 0) for s in samples]
log('idle mcu_awake %.4f; moving %.0f s: mcu_awake mean %.4f max %.4f, task_avg mean %.6f max %.6f (%d samples)'
    % (sum(s.get('mcu_awake', 0) for s in idle) / len(idle), time.time() - t0,
       sum(aw) / len(aw), max(aw), sum(ta) / len(ta), max(ta), len(samples)))
gc('UPC_STEP_STATS')
gc('G90\nG1 X110 Y100 F6000\nM400')
