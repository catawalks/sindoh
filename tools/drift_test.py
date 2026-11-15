"""X/Y lost-step drift test: find the endstop trigger point, zig-zag, find it again.

Trigger search: creep toward the switch in 0.1 mm steps (then 0.02 mm back-off
refinement) and read QUERY_ENDSTOPS after each step. A shift of the trigger
point after the zig-zags = steps lost (or gained) during them.
"""
import json, sys, time, urllib.parse, urllib.request

API = 'http://10.10.0.147:7125'
LOG = open(sys.argv[1], 'a', buffering=1)


def log(*a):
    s = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + '\n')


def gc(script, timeout=58):
    url = API + '/printer/gcode/script?script=' + urllib.parse.quote(script)
    req = urllib.request.Request(url, data=b'', method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def endstops():
    gc('QUERY_ENDSTOPS')
    with urllib.request.urlopen(API + '/printer/objects/query?query_endstops', timeout=10) as r:
        return json.load(r)['result']['status']['query_endstops']['last_query']


AX = {  # axis: (stepper, start, direction toward the switch, limit)
    'X': ('stepper_x', 213.0, +1, 219.5),
    'Y': ('stepper_y', 8.5, -1, -1.5),
}


def trigger(axis):
    name, start, sgn, limit = AX[axis]
    gc('G90\nG1 %s%.3f F1200\nM400' % (axis, start))
    if endstops()[name]:
        raise SystemExit('%s already triggered at the start point %.1f' % (axis, start))
    pos = start
    for step in (0.1, 0.02):
        while not endstops()[name]:
            pos += sgn * step
            if (pos - limit) * sgn > 0:
                raise SystemExit('%s: no trigger before %.1f' % (axis, limit))
            gc('G1 %s%.3f F300\nM400' % (axis, pos))
        if step == 0.1:
            # back off 0.3 mm and re-approach finer
            pos -= sgn * 0.3
            gc('G1 %s%.3f F300\nM400' % (axis, pos))
    gc('G1 %s%.3f F1200\nM400' % (axis, start))
    return pos


def zigzag(axis, a, b, n, f, accel):
    gc('SET_VELOCITY_LIMIT ACCEL=%d' % accel)
    left = n
    while left:
        k = min(left, 10)
        moves = '\n'.join('G1 %s%.1f F%d\nG1 %s%.1f F%d' % (axis, b, f, axis, a, f) for _ in range(k))
        gc('G90\nG1 %s%.1f F%d\n%s\nM400' % (axis, a, f, moves))
        left -= k
    gc('SET_VELOCITY_LIMIT ACCEL=1500')


def run(axis, mid, label, n, f, accel):
    t0 = trigger(axis)
    zigzag(axis, mid - 10, mid + 10, n, f, accel)
    t1 = trigger(axis)
    log('%s %-26s before %.3f after %.3f  shift %+.3f mm (%d zig-zags)' % (axis, label, t0, t1, t1 - t0, n))


log('--- drift test start')
gc('BED_CLEAR', 30)
gc('G28', 240)
gc('G90\nG1 Z10 F600\nG1 X105 Y100 F6000\nM400')
for axis, mid in (('X', 105), ('Y', 100)):
    t0 = trigger(axis)
    t1 = trigger(axis)
    log('%s repeatability (no moves)   %.3f %.3f  shift %+.3f mm' % (axis, t0, t1, t1 - t0))
    run(axis, mid, 'print speed 30 mm/s a1500', 100, 1800, 1500)
    run(axis, mid, 'travel 100 mm/s a1500', 100, 6000, 1500)
    run(axis, mid, 'slow 10 mm/s a300', 100, 600, 300)
gc('G1 X105 Y100 F6000\nM400')
log('--- drift test done')
