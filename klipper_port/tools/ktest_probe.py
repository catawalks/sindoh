"""Levelling-probe test: home Z/X/Y, deploy the push-push probe pin (stock left-wall toggle),
probe the bed N times at (PX, PY) by raising the bed, then stow, lower the bed, drivers off, reset.
Safety: every probing move has BOTH the probe pin (dsens8 = 1) and the Z top switch (xena44 = 1)
on one trsync, so the bed can never rise above the Z-homed height.
Own test coordinates (the pre-calibration config, not today's printer.cfg): X home 216 (max), Y home 5.5 (min, bed back), Z home 3.1
(top switch, bed up; +Z = bed down). Z values below are therefore only as good as position_endstop.
usage: ktest_probe.py KLIPPER_TREE PRINTER_IP [PX=110] [PY=100] [N=3] [clear_mm=15]"""
import sys, time
kl, ip = sys.argv[1], sys.argv[2]
PX = float(sys.argv[3]) if len(sys.argv) > 3 else 110.0
PY = float(sys.argv[4]) if len(sys.argv) > 4 else 100.0
N = int(sys.argv[5]) if len(sys.argv) > 5 else 3
CLEAR = float(sys.argv[6]) if len(sys.argv) > 6 else 15.0
if not (0 <= PX <= 200 and 10 <= PY <= 195 and 1 <= N <= 10 and 8 <= CLEAR <= 30):
    sys.exit('refusing: PX 0..200, PY 10..195, N 1..10, clear 8..30')
src = open(__file__.replace('ktest_probe.py', 'khost.py'), encoding='utf-8-sig').read().split('fm = Mcu(')[0]
g = {'__name__': 'probe'}
sys.argv = [sys.argv[0], kl, ip]
exec(compile(src, 'khost.py', 'exec'), g)
F = 396000000
# axis: engine, REF block, REF duty, steps/mm, DIR for +coordinate, home DIR, home pin oid, home position
AX = {'X': dict(eng=0, ref=27, duty=0.425, spm=80.0, pos_dir=1, home_dir=1, home_pos=216.0),
      'Y': dict(eng=1, ref=29, duty=0.60, spm=80.0, pos_dir=1, home_dir=0, home_pos=5.5),
      'Z': dict(eng=2, ref=30, duty=0.65, spm=3200.0, pos_dir=1, home_dir=0, home_pos=3.1)}
STEP_OID = {'X': 0, 'Y': 1, 'Z': 2}
EN_OID = {'X': 3, 'Y': 4, 'Z': 5}
REF_OID = {'X': 6, 'Y': 7, 'Z': 8}
ES = {'X': 9, 'Y': 10, 'Z': 11, 'P': 12}       # xena42, xena43, xena44, dsens8
TRS = 13

fm = g['Mcu']('FM', 9100)
fm.identify()
c = fm.transact('get_config', 'config')
if c['is_config'] or c['is_shutdown']:
    fm.send('reset'); time.sleep(1.0); fm.recv(0.3)
    fm.seq = 0; fm.mcu_next = None
    fm.identify()
fm.send('allocate_oids count=14')
for a in 'XYZ':
    e = AX[a]['eng']
    fm.send('config_stepper oid=%d step_pin=smot_step%d dir_pin=smot_dir%d invert_step=0 step_pulse_ticks=%d'
            % (STEP_OID[a], e, e, 2 * F // 1000000))
for a in 'XYZ':
    fm.send('config_digital_out oid=%d pin=smot_en%d value=1 default_value=1 max_duration=0' % (EN_OID[a], AX[a]['eng']))
for a in 'XYZ':
    fm.send('config_pwm_out oid=%d pin=pwm%d cycle_ticks=%d value=0 default_value=0 max_duration=0'
            % (REF_OID[a], AX[a]['ref'], F // 10000))
for k, p in (('X', 'xena42'), ('Y', 'xena43'), ('Z', 'xena44'), ('P', 'dsens8')):
    fm.send('config_endstop oid=%d pin=%s pull_up=0' % (ES[k], p))
fm.send('config_trsync oid=%d' % TRS)
fm.send('finalize_config crc=0')
r = fm.transact('get_config', 'config')
if not r['is_config'] or r['is_shutdown']:
    sys.exit('config failed %r' % r)

pos = {'X': None, 'Y': None, 'Z': None}
log = []
# Keep every shutdown message the MCU sends, whichever call happens to read it
shutdowns = []
_recv = fm.recv
def _recv_hook(wait=0.1):
    msgs = _recv(wait)
    for m in msgs:
        if m['#name'] in ('shutdown', 'is_shutdown'):
            shutdowns.append(m)
    return msgs
fm.recv = _recv_hook
# Probe input filter: SAMPLE_COUNT consecutive samples SAMPLE_TICKS apart must all read 1
SAMPLE_TICKS = int(sys.argv[7]) * F // 1000000 if len(sys.argv) > 7 else F // 20000    # 50 us
SAMPLE_COUNT = int(sys.argv[8]) if len(sys.argv) > 8 else 10
def say(s):
    print(s); sys.stdout.flush(); log.append(s)
def q(k):
    return fm.transact('endstop_query_state oid=%d' % ES[k], 'endstop_state')['pin_value']
def steppos(a):
    return fm.transact('stepper_get_position oid=%d' % STEP_OID[a], 'stepper_position')['pos']
def shutdown_check():
    if fm.transact('get_config', 'config')['is_shutdown']:
        fm.recv(0.3)
        raise RuntimeError('MCU shutdown: %r' % [(m['#name'], m.get('static_string_id'), m.get('clock'))
                                                 for m in shutdowns])

def finish(msg):
    for a in 'XYZ':
        fm.send('update_digital_out oid=%d value=1' % EN_OID[a])
    time.sleep(0.3)
    fm.send('reset')
    say('END: %s; drivers off, MCU reset' % msg)
    sys.exit(0)

def move(a, target, speed):
    """Uniform-speed move of one axis to an absolute coordinate."""
    ax = AX[a]
    d_mm = target - pos[a]
    n = int(round(abs(d_mm) * ax['spm']))
    if n == 0:
        return
    d = ax['pos_dir'] if d_mm > 0 else 1 - ax['pos_dir']
    iv = int(F / (speed * ax['spm']))
    oid = STEP_OID[a]
    t = (fm.clock()[0] + F // 2) & 0xffffffff
    fm.send('reset_step_clock oid=%d clock=%d' % (oid, t))
    fm.send('set_next_step_dir oid=%d dir=%d' % (oid, d))
    left = n
    while left:
        cnt = min(left, 60000)
        fm.send('queue_step oid=%d interval=%d count=%d add=0' % (oid, iv, cnt)); left -= cnt
    time.sleep(0.5 + n * iv / F + 0.3)
    pos[a] = pos[a] + (n / ax['spm']) * (1 if d_mm > 0 else -1)
    shutdown_check()

def stop_endstops(keys):
    for k in keys:
        fm.send('endstop_home oid=%d clock=0 sample_ticks=0 sample_count=0 rest_ticks=0 pin_value=0 trsync_oid=0 trigger_reason=0' % ES[k])

def guarded(a, d, max_mm, speed, stops, pfilter=None):
    """Move axis a in raw DIR d until one of stops [(endstop_key, reason)] reads 1.
    Returns (reason or None, travelled_mm)."""
    ax = AX[a]; oid = STEP_OID[a]
    n = int(max_mm * ax['spm']); iv = int(F / (speed * ax['spm']))
    fm.recv(0.2)        # drop late reports of the previous trsync
    p0 = steppos(a)
    t0 = (fm.clock()[0] + F // 2) & 0xffffffff
    fm.send('trsync_start oid=%d report_clock=%d report_ticks=%d expire_reason=4' % (TRS, t0, F // 10))
    fm.send('stepper_stop_on_trigger oid=%d trsync_oid=%d' % (oid, TRS))
    fm.send('trsync_set_timeout oid=%d clock=%d' % (TRS, (t0 + 2 * F) & 0xffffffff))
    for k, reason in stops:
        st, sc = (pfilter or (SAMPLE_TICKS, SAMPLE_COUNT)) if k == 'P' else (F // 66666, 4)
        fm.send('endstop_home oid=%d clock=%d sample_ticks=%d sample_count=%d rest_ticks=%d pin_value=1 trsync_oid=%d trigger_reason=%d'
                % (ES[k], t0, st, sc, F // 10000, TRS, reason))
    fm.send('reset_step_clock oid=%d clock=%d' % (oid, t0))
    fm.send('set_next_step_dir oid=%d dir=%d' % (oid, d))
    left = n
    while left:
        cnt = min(left, 60000)
        fm.send('queue_step oid=%d interval=%d count=%d add=0' % (oid, iv, cnt)); left -= cnt
    res = None; end = time.time() + 1.0 + n * iv / F + 4.0; renew = time.time() + 0.5
    while time.time() < end and res is None:
        for m in fm.recv(0.05):
            # only reports of THIS trsync session (clock at/after t0; a stale report from the
            # previous homing once made the script believe the stepper had stopped)
            if (m['#name'] == 'trsync_state' and m['oid'] == TRS and not m['can_trigger']
                    and ((m['clock'] - t0) & 0xffffffff) < 0x80000000):
                res = m['trigger_reason']
            if m['#name'] in ('shutdown', 'is_shutdown'):
                raise RuntimeError('MCU shutdown during guarded move: %r' % m)
        if res is None and time.time() > renew:
            fm.send('trsync_set_timeout oid=%d clock=%d' % (TRS, (fm.clock()[0] + 2 * F) & 0xffffffff))
            renew = time.time() + 0.5
    stop_endstops([k for k, _ in stops])
    time.sleep(0.2)
    p1 = steppos(a); time.sleep(0.3); p2 = steppos(a)
    if p1 != p2:
        raise RuntimeError('%s still moving after trsync result %r (%d -> %d)' % (a, res, p1, p2))
    mm = abs(p2 - p0) / ax['spm']
    return (res if res in [r_ for _, r_ in stops] else None), mm

def home(a, speed):
    ax = AX[a]
    if q(a) == 1:      # already on the switch: back off first
        pos[a] = ax['home_pos']
        away = 5.0 if ax['home_dir'] != ax['pos_dir'] else -5.0     # opposite to the homing direction
        move(a, ax['home_pos'] + away, 5.0 if a != 'Z' else 3.0)
    res, mm = guarded(a, ax['home_dir'], 260.0 if a != 'Z' else 205.0, speed, [(a, 1)])
    if res != 1:
        finish('%s homing did not trigger after %.1f mm' % (a, mm))
    pos[a] = ax['home_pos']
    say('%s homed (travel %.2f mm) -> %.1f' % (a, mm, pos[a]))

def toggle_probe():
    """Stock engine_changelvsensor: X -> -10, push to -20 at 10 mm/s, back to -5.6."""
    move('X', -10.0, 20.0)
    move('X', -20.0, 10.0)
    move('X', -5.6, 20.0)

def set_probe(want, what):
    for i in range(3):
        if q('P') == want:
            return
        toggle_probe()
        say('  toggle %d for %s: dsens8 = %d' % (i + 1, what, q('P')))
    if q('P') != want:
        finish('probe did not %s after 3 toggles' % what)

try:
    # drivers + REF on
    t_on = (fm.clock()[0] + F // 2) & 0xffffffff
    for a in 'XYZ':
        fm.send('queue_pwm_out oid=%d clock=%d value=%d' % (REF_OID[a], t_on, int(AX[a]['duty'] * 255)))
        fm.send('queue_digital_out oid=%d clock=%d on_ticks=0' % (EN_OID[a], t_on))
    time.sleep(0.8)
    say('start: X/Y/Z switches %d/%d/%d, dsens8 %d' % (q('X'), q('Y'), q('Z'), q('P')))
    # Z first while the probe is stowed (a deployed pin could touch the bed during Z homing)
    if q('P') != 1:
        # never raise the bed to the switch under a deployed pin: stow it first
        say('probe reads deployed - homing X and stowing it before Z homing')
        home('X', 10.0)
        set_probe(1, 'stow')
    pos['Z'] = 0.0
    home('Z', 3.0)
    move('Z', pos['Z'] + CLEAR, 5.0)
    home('X', 10.0)
    home('Y', 5.0)
    set_probe(0, 'deploy')
    say('probe deployed (dsens8 = 0) at X %.1f' % pos['X'])
    move('Y', PY, 20.0)
    move('X', PX, 20.0)
    say('at X %.1f Y %.1f, Z %.3f (bed %.1f mm below the Z-switch height)' % (pos['X'], pos['Y'], pos['Z'], pos['Z'] - 3.1))
    # Noise check: pin deployed, bed moving AWAY (down) so nothing can touch the pin.
    # A trigger here is electrical noise or pin bounce, not contact.
    say('dsens8 x5 before noise check: %s' % [q('P') for _ in range(5)])
    for label, pf in (('Klipper default 4 x 15us', (F // 66666, 4)),
                      ('strict %d x %dus' % (SAMPLE_COUNT, SAMPLE_TICKS * 1000000 // F), None)):
        for d, what in ((1, 'down'), (0, 'up')):
            if d == 0:
                res, mm = guarded('Z', 0, 5.0, 2.0, [('P', 1), ('Z', 2)], pf)
                pos['Z'] -= mm
            else:
                res, mm = guarded('Z', 1, 5.0, 2.0, [('P', 1)], pf)
                pos['Z'] += mm
            say('  noise check %-26s Z %s 5 mm at 2 mm/s: %s after %.3f mm'
                % (label, what, {1: 'FALSE TRIGGER', 2: 'Z switch?!', None: 'no trigger'}[res], mm))
            if res == 1:
                say('    dsens8 now: %s' % [q('P') for _ in range(5)])
    say('dsens8 x5 before probing: %s' % [q('P') for _ in range(5)])
    results = []
    for i in range(N):
        if q('P') != 0:
            say('  probe %d: pin not deployed (dsens8 = 1) - re-deploying' % (i + 1))
            xs, ys = pos['X'], pos['Y']
            set_probe(0, 'deploy')
            move('X', xs, 20.0)
        z0 = pos['Z']
        res, mm = guarded('Z', 0, z0 - 3.1 + 0.5, 2.0, [('P', 1), ('Z', 2)])
        pos['Z'] = z0 - mm
        if res == 1:
            results.append(pos['Z'])
            say('  probe %d: TRIGGERED at Z %.4f (travel %.4f mm)' % (i + 1, pos['Z'], mm))
        elif res == 2:
            say('  probe %d: Z SWITCH reached first at Z %.4f - pin does not reach below the switch height' % (i + 1, pos['Z']))
        else:
            say('  probe %d: no trigger (travel %.3f mm)' % (i + 1, mm))
        move('Z', pos['Z'] + 5.0, 5.0)
        say('  after lowering 5 mm: dsens8 = %d (%s)' % (q('P'), 'still deployed' if q('P') == 0 else 'LATCHED IN by the bed push'))
        if res != 1:
            break
    if len(results) >= 2:
        say('probe Z: %s  range %.4f mm  mean %.4f' % (' '.join('%.4f' % z for z in results),
                                                      max(results) - min(results), sum(results) / len(results)))
    # stow and leave the bed lowered
    move('Z', pos['Z'] + 5.0, 5.0)
    set_probe(1, 'stow')
    say('probe stowed (dsens8 = 1)')
    finish('done')
except SystemExit:
    raise
except BaseException as e:
    finish('ABORT: %r' % e)
