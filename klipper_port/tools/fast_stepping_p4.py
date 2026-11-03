"""Faster stepping, phase 4: one firmware variant on the printer.
usage: p4.py LOG   (the variant is already loaded; owner present, bed empty)
Homing repeatability at 208 mm/s, drift after zig-zags (30/100 mm/s and
long 208 mm/s travels), 5 probes at the centre, UPC_STEP_STATS."""
import json, sys, time, urllib.request
sys.argv = [sys.argv[0], sys.argv[1]]
src = open(sys.argv[0].replace('p4.py', 'drift_test.py'), encoding='utf-8').read()
exec(compile(src.split("\nlog('--- drift test start')")[0], 'drift_test.py', 'exec'))

def q(obj):
    with urllib.request.urlopen(API + '/printer/objects/query?' + obj, timeout=10) as r:
        return json.load(r)['result']['status']

def timed(script, t=180):
    t0 = time.time(); gc(script, timeout=t); return time.time() - t0

def probe():
    gc('G90\nG1 Z15 F600\nG1 X95 Y130 F6000\nM400\nPROBE\nG1 Z15 F600\nM400', timeout=120)
    return q('probe')['probe']['last_z_result']

def travel(axis, a, b, n):
    """n long travels at 208 mm/s (mostly constant speed: engine moves)."""
    left = n
    while left:
        k = min(left, 5)
        moves = '\n'.join('G1 %s%.1f F12480\nG1 %s%.1f F12480' % (axis, b, axis, a) for _ in range(k))
        gc('G90\nSET_VELOCITY_LIMIT VELOCITY=210 ACCEL=1500\nG1 %s%.1f F6000\n%s\nM400' % (axis, a, moves), 120)
        left -= k

log('--- phase 4 start, mcu %s' % q('mcu')['mcu']['mcu_version'])
log('G28 (all): %.1f s' % timed('BED_CLEAR\nG28'))
gc('G90\nG1 Z10 F600\nM400')
for ax, far in (('X', 20), ('Y', 200)):
    base = trigger(ax); times = []
    for i in range(10):
        gc('G90\nG1 %s%d F6000\nM400' % (ax, far))
        times.append(timed('G28 %s' % ax))
    after = trigger(ax)
    log('%s homing x10 at 208: trigger %.3f -> %.3f shift %+.3f; G28 %.1f-%.1f s'
        % (ax, base, after, after - base, min(times), max(times)))
gc('G90\nG1 X105 Y100 F6000\nM400')
for axis, mid, lo, hi in (('X', 105, 20, 200), ('Y', 100, 20, 180)):
    run(axis, mid, 'print speed 30 mm/s a1500', 50, 1800, 1500)
    run(axis, mid, 'travel 100 mm/s a1500', 50, 6000, 1500)
    t0 = trigger(axis)
    travel(axis, lo, hi, 20)
    t1 = trigger(axis)
    log('%s %-26s before %.3f after %.3f  shift %+.3f mm (20 travels)'
        % (axis, '208 mm/s %d-%d' % (lo, hi), t0, t1, t1 - t0))
gc('SET_VELOCITY_LIMIT VELOCITY=210 ACCEL=1500')
z = [probe() for _ in range(5)]
log('probe x5 at X95 Y130: %s  spread %.4f' % (' '.join('%.4f' % v for v in z), max(z) - min(z)))
gc('UPC_STEP_STATS')
with urllib.request.urlopen(API + '/server/gcode_store?count=8', timeout=10) as r:
    for m in json.load(r)['result']['gcode_store']:
        if 'engine' in m['message']:
            log('stats: ' + m['message'].replace('\n', ' | '))
gc('G90\nG1 Z20 F600\nG1 X105 Y100 F6000\nM400')
log('--- phase 4 done')
