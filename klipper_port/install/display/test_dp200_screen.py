"""Offline test for dp200_screen.py: synthetic touch events through a pipe,
Moonraker POSTs stubbed (nothing is sent to the printer), framebuffer writes
go to a temp file. Needs a running Moonraker for the read-only status query.
    /usr/bin/python3 test_dp200_screen.py"""
import os, sys, tempfile, time
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dp200_screen as S

sent = []
S.post = lambda path, body=None: sent.append((path, (body or {}).get('script')))

def raw_for(u, v):
    ry = (u - S.CAL_U[1]) / S.CAL_U[0]
    rx = (v - S.CAL_V[1]) / S.CAL_V[0]
    return int(rx), int(ry)

class FakeTouch(S.Touch):
    def __init__(self):
        self.r, self.w = os.pipe()
        os.set_blocking(self.r, False)
        self.fd = self.r
        self.x = self.y = None
        self.samples, self.down, self.last = [], False, 0.0

    def frame(self, u, v):
        rx, ry = raw_for(u, v)
        ev = S.EVENT
        os.write(self.w, ev.pack(0, 0, S.EV_ABS, S.ABS_MT_X, rx) + ev.pack(0, 0, S.EV_ABS, S.ABS_MT_Y, ry)
                 + ev.pack(0, 0, S.EV_SYN, S.SYN_REPORT, 0))

    def lift(self):
        os.write(self.w, S.EVENT.pack(0, 0, S.EV_SYN, S.SYN_REPORT, 0))

ui = S.UI()
ui.settings = {}                      # default timeout, whatever the printer has saved
ui.st = S.query()
# results must not depend on whether the printer happens to be homed
ui.st['toolhead'] = dict(ui.st['toolhead'], homed_axes='xyz')
touch = FakeTouch()
fails = 0

def step():
    for ev in touch.poll():
        if ui.dimmed() and ev[0] == 'down':
            ui.last_touch, ui.press = time.time(), None
            continue
        ui.on_touch(ev)
    ui.check_hold()
    ui.render()

def tap(label):
    box = find(label)
    u, v = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    for _ in range(4):
        touch.frame(u, v)
    step()
    touch.lift()
    step()
    time.sleep(0.4)          # let a background "gcode" thread finish
    step()

labels = {}
_orig_button = S.UI.button
def button(self, d, box, label, action, *a, **k):
    labels[label] = box
    return _orig_button(self, d, box, label, action, *a, **k)
S.UI.button = button

def find(label):
    labels.clear()
    ui.render()
    if label == 'STOP':
        return next(b for b, a in ui.buttons if a == ('estop',))
    return labels[label]

def check(name, cond):
    global fails
    print('%-40s %s' % (name, 'ok' if cond else 'FAIL'))
    fails += not cond

check('home screen', ui.screen == 'home')
tap('SYSTEM');            check('SYSTEM -> system screen', ui.screen == 'system')
tap('FIRMWARE');          check('FIRMWARE asks to confirm', ui.confirm is not None)
tap('NO');                check('NO cancels, nothing sent', ui.confirm is None and not sent)
tap('INFO');              check('SYSTEM -> INFO page', ui.screen == 'info')
rows = dict(ui.info or [])
check('INFO lists versions and storage', all(k in rows for k in ('Build', 'Klipper', 'Kernel', 'Storage')))
check('INFO reads the kernel', rows.get('Kernel', '-') != '-')
tap('BACK');              check('INFO BACK -> system', ui.screen == 'system')
# UPDATE: versions from Moonraker; refresh and upgrade go through post()
tap('UPDATE'); time.sleep(1.5); step()
check('SYSTEM -> UPDATE page', ui.screen == 'update')
check('UPDATE reads the Mainsail version', ui.upd.get('mainsail', '-') not in ('-', None))
n = len(sent); tap('CHECK NOW'); time.sleep(1.5); step()
check('CHECK NOW asks Moonraker to refresh', ('/machine/update/refresh?name=mainsail', None) in sent[n:])
ui.upd['mainsail_new'] = 'v9.9.9'
tap('UPDATE');            check('a newer Mainsail asks to confirm', ui.confirm is not None and 'v9.9.9' in ui.confirm[0])
n = len(sent); tap('YES'); time.sleep(1.5); step()
check('YES asks Moonraker to upgrade Mainsail', ('/machine/update/upgrade?name=mainsail', None) in sent[n:])
tap('BACK');              check('UPDATE BACK -> system', ui.screen == 'system')
tap('BACK');              check('BACK -> home', ui.screen == 'home')
tap('LAMP');              check('LAMP sends LAMP_TOGGLE', sent[-1:] == [('/printer/gcode/script', 'LAMP_TOGGLE')])
tap('MOVE'); tap('HOME');  check('MOVE -> HOME -> homing screen', ui.screen == 'homing')
tap('HOME ALL')
check('HOME ALL asks to confirm', ui.confirm is not None and sent[-1][1] == 'LAMP_TOGGLE')
check('HOME ALL asks if the bed is empty', 'EMPTY' in ui.confirm[0])
tap('YES');               check('YES sends BED_CLEAR + G28', sent[-1] == ('/printer/gcode/script', 'BED_CLEAR\nG28'))
for axis in 'XY':
    n = len(sent); tap('HOME ' + axis)
    check('HOME %s asks to confirm' % axis, ui.confirm is not None and len(sent) == n)
    tap('YES');           check('YES sends G28 ' + axis, sent[-1] == ('/printer/gcode/script', 'G28 ' + axis))
n = len(sent); tap('HOME Z'); tap('NO')
check('NO on HOME Z sends nothing', len(sent) == n and ui.screen == 'homing')
tap('HOME Z');            check('HOME Z asks if the bed is empty', 'EMPTY' in ui.confirm[0])
tap('YES');               check('YES sends BED_CLEAR + G28 Z', sent[-1] == ('/printer/gcode/script', 'BED_CLEAR\nG28 Z'))
# a refused G-code shows Klipper's message, not the HTTP reason phrase
import io, urllib.error
body = io.BytesIO(b'{"error": {"code": 400, "message": "Must home axis first: 0.000 0.000 0.000"}}')
err = urllib.error.HTTPError(S.API, 400, 'unknown', {}, body)
check('refusal shows the Klipper message', S.fail_text(err) == 'Must home axis first: 0.000 0.000 0.000')
tap('BACK');              check('BACK -> move screen', ui.screen == 'move')
tap('BACK')
# input shaping: sensor config switched by renaming files (in a temp dir here)
adir = tempfile.mkdtemp()
S.ADXL_ON = os.path.join(adir, 'dp200_adxl.cfg'); S.ADXL_OFF = S.ADXL_ON + '.off'
open(S.ADXL_OFF, 'w').close()
tap('MOVE'); tap('CALIBRATE'); tap('INPUT SHAPING')
check('MOVE -> CALIBRATE -> INPUT SHAPING', ui.screen == 'shaper')
n = len(sent); tap('SENSOR ON')
check('SENSOR ON asks to confirm', ui.confirm is not None and len(sent) == n)
tap('YES')
check('YES enables config + restarts', os.path.exists(S.ADXL_ON) and not os.path.exists(S.ADXL_OFF)
      and sent[-1] == ('/printer/restart', None))
tap('TEST X'); tap('YES')
check('TEST X sends SHAPER_CALIBRATE AXIS=X', sent[-1][1].endswith('SHAPER_CALIBRATE AXIS=X'))
tap('TEST Y'); tap('YES')
check('TEST Y sends SHAPER_CALIBRATE AXIS=Y', sent[-1][1].endswith('SHAPER_CALIBRATE AXIS=Y'))
m = S.SHAPER_RE.findall('Recommended shaper_type_x = mzv, shaper_freq_x = 53.8 Hz')
check('result line parsed', m == [('x', 'mzv', '53.8')])
tap('SENSOR OFF'); tap('YES')
check('SENSOR OFF disables config', os.path.exists(S.ADXL_OFF) and not os.path.exists(S.ADXL_ON))
os.unlink(S.ADXL_OFF); os.rmdir(adir)
tap('BACK'); tap('BACK'); tap('BACK')
# CALIBRATE: paper tests, PID tune, saving - all through the stand-ins
# (post() records; manual_probe is faked; nothing moves or heats)
_get = S.get
S.get = lambda p: ({'status': {'manual_probe': {'is_active': True, 'z_position': 0.825}}}
                   if 'manual_probe' in p else _get(p))
st0 = ui.st
ui.st = dict(st0)
tap('MOVE'); tap('CALIBRATE'); tap('Z HEIGHT')
check('Z HEIGHT asks if the bed is empty', ui.confirm is not None and 'EMPTY' in ui.confirm[0])
n = len(sent); tap('YES'); time.sleep(0.5); step()
check('Z HEIGHT homes and starts the paper test',
      ('/printer/gcode/script', 'BED_CLEAR\nG28\nZ_ENDSTOP_CALIBRATE') in sent[n:] and ui.screen == 'papertest')
ui.st['manual_probe'] = {'is_active': True, 'z_position': 2.275}
tap('-0.1');              check('-0.1 sends TESTZ Z=-0.1', sent[-1] == ('/printer/gcode/script', 'TESTZ Z=-0.1'))
tap('ACCEPT'); time.sleep(0.5); step()
check('ACCEPT sends ACCEPT', sent[-1] == ('/printer/gcode/script', 'ACCEPT') and ui.cal.get('done'))
ui.st['manual_probe'] = {'is_active': False}
tap('SAVE'); tap('YES'); time.sleep(0.5); step()
check('SAVE sends SAVE_CONFIG', sent[-1] == ('/printer/gcode/script', 'SAVE_CONFIG') and ui.screen == 'calibrate')
tap('PROBE OFFSET'); tap('YES'); time.sleep(0.5); step()
check('PROBE OFFSET starts LV_PROBE_CALIBRATE', sent[-1] == ('/printer/gcode/script', 'BED_CLEAR\nLV_PROBE_CALIBRATE'))
ui.st['manual_probe'] = {'is_active': True, 'z_position': 0.825}
tap('ACCEPT'); time.sleep(0.5); step()
check('probe ACCEPT passes the height on',
      sent[-1] == ('/printer/gcode/script', 'ACCEPT\nLV_PROBE_CALIBRATE_SAVE Z=0.825'))
tap('DISCARD');           check('DISCARD -> calibrate', ui.screen == 'calibrate' and not ui.cal)
tap('Z HEIGHT'); tap('YES'); time.sleep(0.5); step()
n = len(sent); tap('BACK'); time.sleep(0.5); step()
check('BACK during a paper test sends ABORT', ('/printer/gcode/script', 'ABORT') in sent[n:]
      and ui.screen == 'calibrate')
ui.st['manual_probe'] = {'is_active': False}
tap('PID TUNE'); tap('NOZZLE')
check('PID NOZZLE asks to confirm', ui.confirm is not None and '210' in ui.confirm[0])
tap('YES'); time.sleep(0.5); step()
check('YES sends PID_CALIBRATE extruder 210',
      ('/printer/gcode/script', 'PID_CALIBRATE HEATER=extruder TARGET=210') in sent)
tap('SAVE'); tap('YES'); time.sleep(0.5); step()
check('PID SAVE sends SAVE_CONFIG', sent[-1] == ('/printer/gcode/script', 'SAVE_CONFIG'))
ui.st['gcode_move'] = dict(st0['gcode_move'], homing_origin=[0.0, 0.0, 0.05, 0.0])
ui.screen = 'calibrate'
tap('SAVE Z OFFSET'); tap('YES'); time.sleep(0.5); step()
check('SAVE Z OFFSET applies it and saves',
      sent[-1] == ('/printer/gcode/script', 'Z_OFFSET_APPLY_ENDSTOP\nSAVE_CONFIG'))
# HOME in the header (its label is the house icon: '' in the label map)
ui.screen = 'pid'
tap('');                  check('HOME from a deep page -> home', ui.screen == 'home')
find('LAMP');             check('no HOME button on the home page', '' not in labels)
ui.screen = 'calibrate'
tap('Z HEIGHT'); tap('YES'); time.sleep(0.5); step()
ui.st['manual_probe'] = {'is_active': True, 'z_position': 2.0}
n = len(sent); tap(''); time.sleep(0.5); step()
check('HOME during a paper test aborts it', ('/printer/gcode/script', 'ABORT') in sent[n:]
      and ui.screen == 'home')
S.get = _get
ui.st = st0
ui.screen = 'home'
check('BACK x3 -> home', ui.screen == 'home')
tap('FILAMENT'); tap('UNLOCK');       check('UNLOCK asks to confirm', ui.confirm is not None)
tap('YES');                           check('YES sends CARTRIDGE_RELEASE', sent[-1] == ('/printer/gcode/script', 'CARTRIDGE_RELEASE'))
# filament dryer
tap('DRYER');                         check('FILAMENT -> DRYER', ui.screen == 'dryer')
tap('PETG'); tap('6h'); n = len(sent); tap('START')
check('START asks to confirm', ui.confirm is not None and len(sent) == n)
tap('YES')
check('YES sends FILAMENT_DRY PETG 65 C 6 h',
      sent[-1] == ('/printer/gcode/script', 'FILAMENT_DRY TEMP=65 HOURS=6 MATERIAL=PETG'))
tap('ABS'); tap('START')
check('80 C warns and adds FORCE=1', ui.confirm is not None and 'WARNING' in ui.confirm[0]
      and ui.confirm[1][1].endswith('FORCE=1'))
n = len(sent); tap('NO');             check('NO sends nothing', len(sent) == n)
saved_st = ui.st
ui.st = dict(saved_st, **{'gcode_macro _DRY': {'active': 1, 'remaining': 100, 'total': 240, 'temp': 50,
                                                'flipped': 1, 'sheet_max': 70}})
tap('STOP DRYING'); tap('YES')
check('running dryer: STOP DRYING sends FILAMENT_DRY_STOP', sent[-1] == ('/printer/gcode/script', 'FILAMENT_DRY_STOP'))
ui.st = saved_st
tap('BACK')
# LOAD / UNLOAD: filament presets and a custom temperature (saved setting
# in a temp file here)
check('DRYER BACK -> filament', ui.screen == 'filament')
S.SETTINGS = os.path.join(tempfile.mkdtemp(), 'screen_settings.json')
tap('LOAD');                          check('LOAD -> filament choice', ui.screen == 'fil_mat')
n = len(sent); tap('PLA')
check('PLA asks to confirm', ui.confirm is not None and len(sent) == n)
tap('YES');                           check('YES sends LOAD_FILAMENT MATERIAL=PLA',
                                            sent[-1] == ('/printer/gcode/script', 'LOAD_FILAMENT MATERIAL=PLA'))
tap('PETG'); tap('YES');              check('PETG sends LOAD_FILAMENT TEMP=240',
                                            sent[-1] == ('/printer/gcode/script', 'LOAD_FILAMENT TEMP=240'))
tap('CUSTOM');                        check('CUSTOM -> temperature page', ui.screen == 'fil_custom')
t0 = ui.fil['temp']; tap('+10'); tap('-5')
check('+10 -5 changes the temperature', ui.fil['temp'] == t0 + 5)
for _ in range(12):
    tap('+10')
check('capped at the extruder limit', ui.fil['temp'] == S.FIL_MAX)
n = len(sent); tap('LOAD'); tap('NO')
check('custom LOAD asks first, NO sends nothing', len(sent) == n and ui.confirm is None)
tap('LOAD'); tap('YES');              check('custom LOAD sends TEMP=260',
                                            sent[-1] == ('/printer/gcode/script', 'LOAD_FILAMENT TEMP=%d' % S.FIL_MAX))
check('custom temperature saved', S.load_settings().get('fil_custom') == S.FIL_MAX)
tap('BACK'); tap('BACK');             check('BACK x2 -> filament', ui.screen == 'filament')
# not homed: a command that homes first asks about the bed and sends BED_CLEAR
ui.st['toolhead'] = dict(ui.st['toolhead'], homed_axes='')
tap('LOAD'); tap('PETG')
check('unhomed LOAD asks if the bed is empty', 'EMPTY' in ui.confirm[0])
tap('YES');                           check('YES sends BED_CLEAR + LOAD_FILAMENT',
                                            sent[-1] == ('/printer/gcode/script', 'BED_CLEAR\nLOAD_FILAMENT TEMP=240'))
tap('CUSTOM'); tap('LOAD')
check('unhomed custom LOAD asks too', 'EMPTY' in ui.confirm[0] and ui.confirm[1][1].startswith('BED_CLEAR\n'))
tap('NO'); tap('BACK'); tap('BACK')
ui.st['toolhead'] = dict(ui.st['toolhead'], homed_axes='xyz')
tap('UNLOAD'); tap('ABS'); tap('YES')
check('UNLOAD ABS sends UNLOAD_FILAMENT MATERIAL=ABS',
      sent[-1] == ('/printer/gcode/script', 'UNLOAD_FILAMENT MATERIAL=ABS'))
tap('BACK')
tap('BACK')
# STOP: a short tap must NOT stop, a 1 s hold must
tap('STOP');              check('short STOP tap ignored', all(p != '/printer/emergency_stop' for p, _ in sent))
box = find('STOP'); u, v = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
t0 = time.time()
while time.time() - t0 < 1.3:
    # like the real panel: frames every 50 ms (a gap > 0.3 s counts as lifted),
    # input handled each frame, a full redraw only now and then
    touch.frame(u, v)
    for ev in touch.poll():
        ui.on_touch(ev)
    ui.check_hold()
    time.sleep(0.05)
touch.lift(); step()
check('STOP held 1 s -> emergency_stop', ('/printer/emergency_stop', None) in sent)
# dim + wake: first tap only wakes
ui.last_touch = time.time() - S.DIM_AFTER - 5
check('dims when idle', bool(ui.dimmed()))
n = len(sent)
box = find('LAMP') if not ui.dimmed() else labels.get('LAMP')
ui.last_touch = time.time() - S.DIM_AFTER - 5
for _ in range(4):
    touch.frame((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
step(); touch.lift(); step(); time.sleep(0.4); step()
check('wake tap sends nothing', len(sent) == n and not ui.dimmed())

# Bed level page: PROBE asks first (bed empty), YES confirms and meshes 4x4
ui.screen, ui.confirm = 'move', None
tap('BED LEVEL');          check('MOVE -> BED LEVEL page', ui.screen == 'bedlevel')
n = len(sent)
tap('PROBE');              check('PROBE asks to confirm', ui.confirm is not None and len(sent) == n)
tap('NO');                 check('NO probes nothing', ui.confirm is None and len(sent) == n)
tap('PROBE'); tap('YES')
time.sleep(1.0)
check('YES: BED_CLEAR + 4x4 mesh', len(sent) > n and sent[-1][1].startswith('BED_CLEAR\n')
      and 'PROBE_COUNT=4,4' in sent[-1][1])
ui.bl['mode'], ui.screen = 'start', 'home'

# Bed-empty dialog: shown while BED_CLEAR.asking, YES / NO answer it
ui.screen, ui.confirm = 'home', None
ui.st = dict(ui.st, **{'gcode_macro BED_CLEAR': {'ok': 0, 'asking': 1}})
ui.render()
check('bed-empty dialog pops up', ui.confirm is not None and 'EMPTY' in ui.confirm[0])
tap('YES');                check('YES sends BED_CLEAR', sent[-1][1] == 'BED_CLEAR' and ui.confirm is None)
ui.render();               check('no re-pop while status lags', ui.confirm is None)
ui.bed_answered = 0.0
tap('NO');                 check('NO sends BED_CLEAR CANCEL=1', sent[-1][1] == 'BED_CLEAR CANCEL=1')
ui.st = dict(ui.st, **{'gcode_macro BED_CLEAR': {'ok': 0, 'asking': 1}})
ui.bed_answered = 0.0; ui.confirm = None
ui.render();               check('bed dialog up again while asking', ui.confirm is not None)
ui.st = dict(ui.st, **{'gcode_macro BED_CLEAR': {'ok': 1, 'asking': 0}})
ui.render();               check('answered in Mainsail: the dialog closes', ui.confirm is None)
ui.st = dict(ui.st, **{'gcode_macro BED_CLEAR': {'ok': 0, 'asking': 0}})
ui.confirm = None

# cancel one object during a print (exclude_object)
saved = ui.st
ps = dict(ui.st['print_stats'], state='printing', filename='three.gcode')
ui.st = dict(ui.st, print_stats=ps, exclude_object={
    'objects': [{'name': 'CUBE_A'}, {'name': 'CUBE_B'}, {'name': 'CUBE_C'}],
    'excluded_objects': [], 'current_object': 'CUBE_B'})
ui.screen = 'home'; ui.render()
check('a print shows the print page', ui.screen == 'print')
tap('OBJECTS');            check('OBJECTS -> objects page', ui.screen == 'objects')
n = len(sent); tap('CUBE_A')
check('an object asks to confirm', ui.confirm is not None and 'CUBE_A' in ui.confirm[0] and len(sent) == n)
tap('YES');                check('YES sends EXCLUDE_OBJECT', sent[-1] == ('/printer/gcode/script', 'EXCLUDE_OBJECT NAME=CUBE_A'))
ui.st['exclude_object'] = dict(ui.st['exclude_object'], excluded_objects=['CUBE_A', 'CUBE_B'])
ui.render(); n = len(sent); tap('CUBE_A'); tap('CUBE_C')
check('skipped and last objects: no action', ui.confirm is None and len(sent) == n)
tap('BACK');               check('objects BACK -> print', ui.screen == 'print')
ui.st['exclude_object'] = {'objects': [{'name': 'ONLY'}], 'excluded_objects': []}
labels.clear(); ui.render(); check('one object: no OBJECTS button', 'OBJECTS' not in labels)
ui.screen = 'objects'; ui.st = saved; ui.render()
check('print over: objects page -> home', ui.screen == 'home')

# Panel: partial updates must equal a full redraw
tmp = tempfile.NamedTemporaryFile(delete=False)
tmp.write(b'\0' * S.FB_W * S.FB_H * 4); tmp.close()
p = S.Panel(tmp.name)
a = ui.render(); p.show(a)
ui.screen = 'move'; b = ui.render(); p.show(b)
full = S.rgb565(b.transpose(Image.Transpose.ROTATE_270))
data = open(tmp.name, 'rb').read()
check('partial fb update == full image (page 0)', data[:len(full)] == full)
check('partial fb update == full image (page 1)', data[len(full):] == full)
os.unlink(tmp.name)

# Mainline simplefb has one 800x480 page: nothing may be written past it
tmp = tempfile.NamedTemporaryFile(delete=False)
tmp.write(b'\0' * S.FB_W * S.FB_H * 2); tmp.close()
p = S.Panel(tmp.name)
check('one-page fb: one page', p.pages == (0,))
p.show(a); p.show(b)
data = open(tmp.name, 'rb').read()
check('one-page fb: size unchanged', len(data) == S.FB_W * S.FB_H * 2)
check('one-page fb: image correct', data == full)
os.unlink(tmp.name)
print('sent:', sent)
print('FAILURES: %d' % fails)
sys.exit(1 if fails else 0)
