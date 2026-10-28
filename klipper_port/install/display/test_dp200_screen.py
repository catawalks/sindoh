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
tap('BACK');              check('BACK -> home', ui.screen == 'home')
tap('LAMP');              check('LAMP sends LAMP_TOGGLE', sent[-1:] == [('/printer/gcode/script', 'LAMP_TOGGLE')])
tap('MOVE'); tap('HOME');  check('MOVE -> HOME -> homing screen', ui.screen == 'homing')
tap('HOME ALL')
check('HOME ALL asks to confirm', ui.confirm is not None and sent[-1][1] == 'LAMP_TOGGLE')
tap('YES');               check('YES sends G28', sent[-1] == ('/printer/gcode/script', 'G28'))
for axis in 'XY':
    n = len(sent); tap('HOME ' + axis)
    check('HOME %s asks to confirm' % axis, ui.confirm is not None and len(sent) == n)
    tap('YES');           check('YES sends G28 ' + axis, sent[-1] == ('/printer/gcode/script', 'G28 ' + axis))
n = len(sent); tap('HOME Z'); tap('NO')
check('NO on HOME Z sends nothing', len(sent) == n and ui.screen == 'homing')
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
check('BACK x3 -> home', ui.screen == 'home')
tap('FILAMENT'); tap('UNLOCK');       check('UNLOCK asks to confirm', ui.confirm is not None)
tap('YES');                           check('YES sends CARTRIDGE_RELEASE', sent[-1] == ('/printer/gcode/script', 'CARTRIDGE_RELEASE'))
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
print('sent:', sent)
print('FAILURES: %d' % fails)
sys.exit(1 if fails else 0)
