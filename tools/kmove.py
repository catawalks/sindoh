"""Shared FM motion helpers for the hardware test scripts (same logic as ktest_probe.py, which
is verified on the printer). Own test coordinates (the pre-calibration config, not today's printer.cfg): X home 216 (max),
Y home 5.5 (min, bed back), Z home 3.1 (top switch; +Z = bed down).
usage:  import kmove; m = kmove.Motion(KLIPPER_TREE, PRINTER_IP); m.enable(); ...; m.finish('msg')"""
import sys, time, os

F = 396000000
AX = {'X': dict(eng=0, ref=27, duty=0.425, spm=80.0, pos_dir=1, home_dir=1, home_pos=216.0),
      'Y': dict(eng=1, ref=29, duty=0.60, spm=80.0, pos_dir=1, home_dir=0, home_pos=5.5),
      'Z': dict(eng=2, ref=30, duty=0.65, spm=3200.0, pos_dir=1, home_dir=0, home_pos=3.1)}
STEP_OID = {'X': 0, 'Y': 1, 'Z': 2}
EN_OID = {'X': 3, 'Y': 4, 'Z': 5}
REF_OID = {'X': 6, 'Y': 7, 'Z': 8}
ES = {'X': 9, 'Y': 10, 'Z': 11, 'P': 12}       # xena42, xena43, xena44, dsens8
TRS = 13


class Motion:
    def __init__(self, kl, ip):
        here = os.path.dirname(os.path.abspath(__file__))
        src = open(os.path.join(here, 'khost.py'), encoding='utf-8-sig').read().split('fm = Mcu(')[0]
        g = {'__name__': 'kmove'}
        argv = sys.argv
        sys.argv = [argv[0], kl, ip]
        exec(compile(src, 'khost.py', 'exec'), g)
        sys.argv = argv
        fm = self.fm = g['Mcu']('FM', 9100)
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
        self.pos = {'X': None, 'Y': None, 'Z': None}
        self.shutdowns = []
        recv = fm.recv
        def hook(wait=0.1):
            msgs = recv(wait)
            self.shutdowns += [m for m in msgs if m['#name'] in ('shutdown', 'is_shutdown')]
            return msgs
        fm.recv = hook

    def say(self, s):
        print(s); sys.stdout.flush()

    def q(self, k):
        return self.fm.transact('endstop_query_state oid=%d' % ES[k], 'endstop_state')['pin_value']

    def steppos(self, a):
        return self.fm.transact('stepper_get_position oid=%d' % STEP_OID[a], 'stepper_position')['pos']

    def shutdown_check(self):
        if self.fm.transact('get_config', 'config')['is_shutdown']:
            self.fm.recv(0.3)
            raise RuntimeError('MCU shutdown: %r' % [(m['#name'], m.get('static_string_id')) for m in self.shutdowns])

    def enable(self, axes='XYZ'):
        fm = self.fm
        t_on = (fm.clock()[0] + F // 2) & 0xffffffff
        for a in axes:
            fm.send('queue_pwm_out oid=%d clock=%d value=%d' % (REF_OID[a], t_on, int(AX[a]['duty'] * 255)))
            fm.send('queue_digital_out oid=%d clock=%d on_ticks=0' % (EN_OID[a], t_on))
        time.sleep(0.8)

    def finish(self, msg):
        for a in 'XYZ':
            self.fm.send('update_digital_out oid=%d value=1' % EN_OID[a])
        time.sleep(0.3)
        self.fm.send('reset')
        self.say('END: %s; drivers off, MCU reset' % msg)

    def move(self, a, target, speed):
        ax = AX[a]; fm = self.fm
        d_mm = target - self.pos[a]
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
        self.pos[a] += (n / ax['spm']) * (1 if d_mm > 0 else -1)
        self.shutdown_check()

    def guarded(self, a, d, max_mm, speed, stops, pfilter=None):
        """Move axis a in raw DIR d until one of stops [(endstop_key, reason)] reads 1.
        Returns (reason or None, travelled_mm)."""
        ax = AX[a]; oid = STEP_OID[a]; fm = self.fm
        n = int(max_mm * ax['spm']); iv = int(F / (speed * ax['spm']))
        fm.recv(0.2)        # drop late reports of the previous trsync session
        p0 = self.steppos(a)
        t0 = (fm.clock()[0] + F // 2) & 0xffffffff
        fm.send('trsync_start oid=%d report_clock=%d report_ticks=%d expire_reason=4' % (TRS, t0, F // 10))
        fm.send('stepper_stop_on_trigger oid=%d trsync_oid=%d' % (oid, TRS))
        fm.send('trsync_set_timeout oid=%d clock=%d' % (TRS, (t0 + 2 * F) & 0xffffffff))
        for k, reason in stops:
            st, sc = (pfilter or (F // 66666, 4)) if k == 'P' else (F // 66666, 4)
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
                if (m['#name'] == 'trsync_state' and m['oid'] == TRS and not m['can_trigger']
                        and ((m['clock'] - t0) & 0xffffffff) < 0x80000000):
                    res = m['trigger_reason']
                if m['#name'] in ('shutdown', 'is_shutdown'):
                    raise RuntimeError('MCU shutdown during guarded move: %r' % m)
            if res is None and time.time() > renew:
                fm.send('trsync_set_timeout oid=%d clock=%d' % (TRS, (fm.clock()[0] + 2 * F) & 0xffffffff))
                renew = time.time() + 0.5
        for k, _ in stops:
            fm.send('endstop_home oid=%d clock=0 sample_ticks=0 sample_count=0 rest_ticks=0 pin_value=0 trsync_oid=0 trigger_reason=0' % ES[k])
        time.sleep(0.2)
        p1 = self.steppos(a); time.sleep(0.3); p2 = self.steppos(a)
        if p1 != p2:
            raise RuntimeError('%s still moving after trsync result %r (%d -> %d)' % (a, res, p1, p2))
        return (res if res in [r_ for _, r_ in stops] else None), abs(p2 - p0) / ax['spm']

    def home(self, a, speed):
        ax = AX[a]
        if self.q(a) == 1:      # already on the switch: back off first
            self.pos[a] = ax['home_pos']
            away = 5.0 if ax['home_dir'] != ax['pos_dir'] else -5.0
            self.move(a, ax['home_pos'] + away, 5.0 if a != 'Z' else 3.0)
        res, mm = self.guarded(a, ax['home_dir'], 260.0 if a != 'Z' else 205.0, speed, [(a, 1)])
        if res != 1:
            raise RuntimeError('%s homing did not trigger after %.1f mm' % (a, mm))
        self.pos[a] = ax['home_pos']
        self.say('%s homed (travel %.2f mm) -> %.1f' % (a, mm, self.pos[a]))

    def toggle_probe(self):
        """Stock engine_changelvsensor: X -> -10, push to -20 at 10 mm/s, back to -5.6."""
        self.move('X', -10.0, 20.0)
        self.move('X', -20.0, 10.0)
        self.move('X', -5.6, 20.0)

    def set_probe(self, want, what):
        for i in range(3):
            if self.q('P') == want:
                return
            self.toggle_probe()
            self.say('  toggle %d for %s: dsens8 = %d' % (i + 1, what, self.q('P')))
        if self.q('P') != want:
            raise RuntimeError('probe did not %s after 3 toggles' % what)
