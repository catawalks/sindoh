#!/usr/bin/python3
"""Touch screen UI for the Sindoh DP200 running Klipper.

Draws on the built-in panel (/dev/fb0, mounted in portrait: we draw 480x800
and turn it 90 degrees clockwise) and reads the Rohm BU21029 touch
controller on /dev/event0 (time32 input_event, multitouch protocol A).
Talks to Moonraker over HTTP on localhost. See docs/touchscreen_options.md.

Run as root inside the Debian chroot with Debian's python3-pil:
    /usr/bin/python3 dp200_screen.py
    /usr/bin/python3 dp200_screen.py --demo FILE   (render FILE as a PNG, no panel)

Anything that moves or heats asks for confirmation first. STOP (bottom
right on every screen) is an emergency stop: hold it for 1 second.
"""
import json, os, select, socket, struct, sys, threading, time, urllib.parse, urllib.request
from PIL import Image, ImageChops, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import dp200_wifi as wifi              # WiFi setup (install/display/dp200_wifi.py)
except ImportError:
    wifi = None

PW, PH = 480, 800                     # portrait, as mounted
FB_W, FB_H = 800, 480                 # fb0 geometry (two pages: 800x960 virtual)
FB, EV = '/dev/fb0', '/dev/event0'
API = 'http://127.0.0.1:7125'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

# Touch calibration (4-corner test 2026-10-20): axes swapped, raw x inverted
CAL_U = (0.14471, -66.6)              # u = a * raw_y + b
CAL_V = (-0.22272, 856.2)             # v = a * raw_x + b

REFRESH_BUSY = 1.0                    # s between status polls while printing/heating
REFRESH_IDLE = 2.0
DIM_AFTER = 600                       # default s without touch while idle -> black image (the
                                      # backlight is not controllable); SYSTEM -> DISPLAY -> TIMEOUT
TIMEOUTS = (60, 300, 600, 1800, 0)    # choices on the TIMEOUT page; 0 = never
SETTINGS = '/etc/dp200/screen_settings.json'   # saved touch-screen settings
HOLD_STOP = 1.0                       # s to hold STOP

# Preheat presets (nozzle, bed); bed max_temp is 100, nozzle 260
PRESETS = (('PLA', 200, 60), ('ABS', 240, 90))
LOWER_BED_Z = 120                     # Z grows downwards on this machine (bed moves down)

OBJECTS = ('webhooks', 'print_stats', 'virtual_sdcard', 'display_status', 'extruder',
           'heater_bed', 'output_pin lamp', 'gcode_move', 'toolhead', 'idle_timeout',
           'filament_switch_sensor cartridge_lever', 'filament_motion_sensor filament_encoder',
           'dp200_cartridge')

C_BG = (20, 20, 26)
C_BAR = (36, 36, 44)
C_TXT = (235, 235, 235)
C_DIM = (160, 160, 172)
C_BTN = (50, 50, 62)
C_ON = (55, 140, 90)
C_RED = (160, 40, 40)
C_WARN = (210, 140, 40)
C_NOZ = (255, 170, 80)
C_BED = (110, 180, 255)

_fonts = {}

def font(size):
    if size not in _fonts:
        try:
            _fonts[size] = ImageFont.truetype(FONT, size)
        except OSError:
            _fonts[size] = ImageFont.load_default()
    return _fonts[size]

# ---------------------------------------------------------------------------
# Framebuffer output: RGB565 LE, only the changed region is converted/written
# ---------------------------------------------------------------------------
_LUT = ([v & 0xf8 for v in range(256)], [v >> 5 for v in range(256)],
        [(v << 3) & 0xe0 for v in range(256)], [v >> 3 for v in range(256)])

def rgb565(im):
    r, g, b = im.split()
    hi = ImageChops.add(r.point(_LUT[0]), g.point(_LUT[1]))
    lo = ImageChops.add(g.point(_LUT[2]), b.point(_LUT[3]))
    return Image.merge('LA', (lo, hi)).tobytes()

class Panel:
    def __init__(self, path=FB):
        self.f = open(path, 'r+b', buffering=0)
        self.prev = None

    def show(self, im):
        if self.prev is None:
            box = (0, 0, PW, PH)
        else:
            box = ImageChops.difference(im, self.prev).getbbox()
            if box is None:
                return
        self.prev = im
        u0, v0, u1, v1 = box
        part = im.crop(box).transpose(Image.Transpose.ROTATE_270)
        raw = rgb565(part)
        # portrait (u, v) -> fb (x = 799 - v, y = u)
        x0, w = FB_W - v1, v1 - v0
        for page in (0, FB_H):                       # write both pages
            for row in range(u1 - u0):
                self.f.seek(((page + u0 + row) * FB_W + x0) * 2)
                self.f.write(raw[row * w * 2:(row + 1) * w * 2])

# ---------------------------------------------------------------------------
# Touch input
# ---------------------------------------------------------------------------
EVENT = struct.Struct('<llHHi')        # kernel 3.2 time32 input_event
EV_SYN, EV_ABS, SYN_REPORT = 0, 3, 0
ABS_MT_X, ABS_MT_Y = 0x35, 0x36

class Touch:
    """Turns raw events into press state. poll() returns a list of
    ('down', u, v) / ('move', u, v) / ('up', u, v) tuples."""
    def __init__(self, path=EV):
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        self.x = self.y = None
        self.samples = []
        self.down = False
        self.last = 0.0

    def _pos(self):
        xs = sorted(s[0] for s in self.samples[-7:])
        ys = sorted(s[1] for s in self.samples[-7:])
        rx, ry = xs[len(xs) // 2], ys[len(ys) // 2]
        u = CAL_U[0] * ry + CAL_U[1]
        v = CAL_V[0] * rx + CAL_V[1]
        return min(max(int(u), 0), PW - 1), min(max(int(v), 0), PH - 1)

    def poll(self):
        out, now = [], time.time()
        try:
            data = os.read(self.fd, EVENT.size * 128)
        except BlockingIOError:
            data = b''
        for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
            _, _, typ, code, val = EVENT.unpack_from(data, off)
            if typ == EV_ABS and code == ABS_MT_X:
                self.x = val
            elif typ == EV_ABS and code == ABS_MT_Y:
                self.y = val
            elif typ == EV_SYN and code == SYN_REPORT:
                if self.x is not None and self.y is not None:
                    self.samples.append((self.x, self.y))
                    self.last = now
                    self.x = self.y = None
                    if not self.down:
                        if len(self.samples) >= 2:    # ignore single-sample glitches
                            self.down = True
                            out.append(('down',) + self._pos())
                    else:
                        out.append(('move',) + self._pos())
                elif self.samples:                  # empty frame = lifted
                    out += self._release()
        if self.samples and now - self.last > 0.3:  # silence = lifted
            out += self._release()
        return out

    def _release(self):
        out = [('up',) + self._pos()] if self.down else []
        self.samples, self.down = [], False
        return out

# ---------------------------------------------------------------------------
# Moonraker
# ---------------------------------------------------------------------------
def query():
    q = '&'.join(urllib.parse.quote(o) for o in OBJECTS)
    with urllib.request.urlopen(API + '/printer/objects/query?' + q, timeout=3) as r:
        return json.load(r)['result']['status']

def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(API + path, data=data, method='POST',
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=3600) as r:   # gcode scripts block until done
        return json.load(r)

def my_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except OSError:
        return '?'
    finally:
        s.close()

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def wrap(d, text, f, width):
    lines, line = [], ''
    for word in str(text).split():
        t = (line + ' ' + word).strip()
        if d.textlength(t, font=f) <= width:
            line = t
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines

def fmt_time(s):
    s = int(max(s, 0))
    return '%d:%02d' % (s // 3600, s // 60 % 60) if s >= 3600 else '%d:%02d' % (s // 60, s % 60)

class UI:
    def __init__(self):
        self.screen = 'home'
        self.confirm = None            # (question, action)
        self.buttons = []              # (box, action)
        self.st = None
        self.err = None
        self.busy = None               # text of the running command
        self.msg = None                # (text, until)
        self.press = None              # (u, v, t0)
        self.last_touch = time.time()
        self.ip = my_ip()
        self.settings = load_settings()          # e.g. {'timeout': 600}
        # WiFi setup state (pages wifi, wifi_list, wifi_kb)
        self.wf = {'rev': 0, 'status': {}, 'saved': 0, 'list': [], 'page': 0,
                   'busy': None, 'checked': 0.0, 'target': b'', 'kb_for': 'psk',
                   'text': '', 'mode': 'abc', 'shift': False, 'show': False, 'hidden': False}

    # ---- actions -------------------------------------------------------
    def run(self, action):
        kind = action[0]
        if kind == 'screen':
            self.screen = action[1]
            if self.screen == 'wifi':
                self.wifi_refresh()
        elif kind.startswith('wifi') or kind.startswith('kb'):
            self.wifi_action(action)
        elif kind == 'set_timeout':
            self.settings['timeout'] = action[1]
            ok = save_settings(self.settings)
            self.flash('Screen timeout: %s%s' % (fmt_timeout(action[1]), '' if ok else ' (not saved!)'))
            self.screen = 'display'
        elif kind == 'confirm':
            self.confirm = (action[1], action[2])
        elif kind == 'cancel':
            self.confirm = None
        elif kind == 'gcode':
            self._bg(action[2] if len(action) > 2 else action[1],
                     lambda: post('/printer/gcode/script', {'script': action[1]}))
        elif kind == 'post':
            self._bg(action[2], lambda: post(action[1]))

    def _bg(self, label, fn):
        if self.busy:
            self.flash('Busy: ' + self.busy)
            return
        self.busy = label

        def work():
            try:
                fn()
            except Exception as e:
                self.flash('%s failed: %s' % (label, getattr(e, 'reason', e)))
            finally:
                self.busy = None
        threading.Thread(target=work, daemon=True).start()

    def flash(self, text, secs=6):
        self.msg = (text, time.time() + secs)

    def emergency_stop(self):
        try:
            post('/printer/emergency_stop')
            self.flash('EMERGENCY STOP sent')
        except Exception as e:
            self.flash('E-stop failed: %s' % e)

    # ---- WiFi ------------------------------------------------------------
    def wifi_bg(self, label, fn):
        """Run a WiFi operation in a worker thread (wpa_supplicant calls block)."""
        wf = self.wf
        if wf['busy'] or wifi is None:
            if wifi is None:
                self.flash('WiFi support not installed')
            return
        wf['busy'] = label
        wf['rev'] += 1

        def work():
            w = None
            try:
                w = wifi.WpaCtrl()
                fn(w)
            except Exception as e:
                self.flash('WiFi: %s' % e)
            finally:
                if w is not None:
                    w.close()
                wf['busy'] = None
                wf['rev'] += 1
        threading.Thread(target=work, daemon=True).start()

    def wifi_refresh(self):
        def fn(w):
            self.wf['status'] = wifi.status(w)
            self.wf['saved'] = len(wifi.load_saved())
            self.ip = my_ip()
        self.wf['checked'] = time.time()
        self.wifi_bg(None, fn)

    def wifi_tick(self):
        """Keep the WiFi page's status current while it is shown, and run the
        no-IP watchdog every 10 s on any page."""
        if self.screen == 'wifi' and not self.wf['busy'] and time.time() - self.wf['checked'] > 4:
            self.wifi_refresh()
        if wifi is not None and time.time() - self.wf.get('wd_at', 0) > 10 and not self.wf.get('wd_run'):
            self.wf['wd_at'] = time.time()
            self.wf['wd_run'] = True

            def work():
                w = None
                try:
                    w = wifi.WpaCtrl()
                    if wifi.watchdog(w, self.wf.setdefault('wd', {})):
                        self.flash('WiFi: no address - reconnecting')
                except Exception:
                    pass
                finally:
                    if w is not None:
                        w.close()
                    self.wf['wd_run'] = False
            threading.Thread(target=work, daemon=True).start()

    def wifi_action(self, action):
        wf, kind = self.wf, action[0]
        if kind in ('wifi_scan', 'wifi_rescan'):
            self.screen = 'wifi_list'
            wf['page'] = 0

            def fn(w):
                wf['list'] = wifi.scan(w, fresh=False)        # known results at once...
                wf['rev'] += 1
                wf['list'] = wifi.scan(w, fresh=True)         # ...then a scan that keeps the link
            self.wifi_bg('Scanning...', fn)
        elif kind == 'wifi_down':
            wf['page'] += 1
        elif kind == 'wifi_up':
            wf['page'] = max(0, wf['page'] - 1)
        elif kind == 'wifi_pick':
            n = action[1]
            if n['secured']:
                self.kb_start(n['ssid'], 'psk')
            else:
                self.confirm = ('Join the OPEN network %s? (no password, anyone can listen in)'
                                % n['ssid'].decode('utf-8', 'replace'), ('wifi_join', n['ssid'], None))
        elif kind == 'wifi_hidden':
            self.kb_start(b'', 'ssid')
        elif kind == 'wifi_join':
            ssid, psk = action[1], action[2]
            self.screen = 'wifi'
            name = ssid.decode('utf-8', 'replace')

            def fn(w):
                ok, msg = wifi.connect(w, ssid, psk)
                wf['status'] = wifi.status(w)
                wf['saved'] = len(wifi.load_saved())
                self.flash(('%s: %s' % (name, msg))[:40], 10)
            self.wifi_bg('Connecting to %s...' % name, fn)
        elif kind == 'wifi_forget':
            ssid = action[1]

            def fn(w):
                wifi.forget(w, ssid)
                wf['status'] = wifi.status(w)
                wf['saved'] = len(wifi.load_saved())
            self.wifi_bg('Forgetting...', fn)
        elif kind == 'kb':
            ch = action[1]
            if len(wf['text']) < 63:
                wf['text'] += ch.upper() if wf['shift'] and wf['mode'] == 'abc' else ch
            wf['shift'] = False
        elif kind == 'kb_bs':
            wf['text'] = wf['text'][:-1]
        elif kind == 'kb_shift':
            wf['shift'] = not wf['shift']
        elif kind == 'kb_mode':
            wf['mode'] = 'sym' if wf['mode'] == 'abc' else 'abc'
        elif kind == 'kb_show':
            wf['show'] = not wf['show']
        elif kind == 'kb_cancel':
            wf['text'] = ''
            self.screen = 'wifi_list' if wf['list'] else 'wifi'
        elif kind == 'kb_ok':
            text = wf['text']
            if wf['kb_for'] == 'ssid':
                if not text or len(text.encode()) > 32:
                    self.flash('Network name: 1-32 characters')
                    return
                self.kb_start(text.encode(), 'psk', hidden=True)
            else:
                if not text and wf['hidden']:
                    self.run(('wifi_join', wf['target'], None))    # open hidden network
                    return
                if not 8 <= len(text) <= 63:
                    self.flash('Password must be 8-63 characters')
                    return
                wf['text'] = ''
                self.run(('wifi_join', wf['target'], text))
        wf['rev'] += 1

    def kb_start(self, ssid, kb_for, hidden=False):
        self.wf.update(target=ssid, kb_for=kb_for, text='', mode='abc', shift=False,
                       show=(kb_for == 'ssid'), hidden=hidden)
        self.screen = 'wifi_kb'

    def page_wifi(self, d, st):
        wf = self.wf
        s = wf['status']
        d.text((20, 160), 'WiFi', font=font(28), fill=C_TXT)
        name = s.get('ssid', b'').decode('utf-8', 'replace') if s.get('wpa_state') == 'COMPLETED' else ''
        state = {'COMPLETED': 'connected', 'SCANNING': 'searching', 'DISCONNECTED': 'not connected',
                 'INACTIVE': 'idle', 'INTERFACE_DISABLED': 'radio off'}.get(
                     s.get('wpa_state', ''), 'connecting' if s.get('wpa_state') else '...')
        lines = [('Network', name or 'not connected'),
                 ('Address', 'http://%s/' % self.ip if self.ip != '?' else '-'),
                 ('State', state),
                 ('Saved', '%d network%s' % (wf['saved'], '' if wf['saved'] == 1 else 's'))]
        for i, (k, v) in enumerate(lines):
            d.text((20, 204 + i * 32), k, font=font(20), fill=C_DIM)
            d.text((150, 204 + i * 32), v[:24], font=font(20), fill=C_TXT)
        if wf['busy']:
            d.text((20, 340), wf['busy'], font=font(22), fill=C_WARN)
        items = [('SCAN', ('wifi_scan',), C_BTN, 30, 'choose network')]
        if name:
            items.append(('FORGET', ('confirm', 'Forget %s? The printer will leave this network.' % name,
                                     ('wifi_forget', s['ssid'])), C_RED, 28, name[:14]))
        self.grid(d, items, top=380, rows_h=100)

    def page_wifi_list(self, d, st):
        wf = self.wf
        nets, per = wf['list'], 5
        pages = (len(nets) + 1 + per - 1) // per       # +1: the hidden-network row
        title = 'Choose a network' + (' (%d/%d)' % (min(wf['page'], pages - 1) + 1, pages) if pages > 1 else '')
        d.text((20, 160), title, font=font(26), fill=C_TXT)
        if wf['busy']:
            d.text((20, 200), wf['busy'], font=font(20), fill=C_WARN)
        elif not nets:
            d.text((20, 200), 'No networks found', font=font(20), fill=C_DIM)
        rows = nets + [None]                           # last row: hidden network
        page = wf['page'] if wf['page'] * per < len(rows) else 0
        for i, n in enumerate(rows[page * per:(page + 1) * per]):
            y = 232 + i * 70
            box = (20, y, PW - 20, y + 62)
            d.rounded_rectangle(box, radius=12,
                                fill=tuple(c + 45 for c in C_BTN) if self.pressed(box) else C_BTN)
            if n is None:
                d.text((36, y + 16), 'Hidden network…', font=font(24), fill=C_DIM)
                self.buttons.append((box, ('wifi_hidden',)))
                continue
            label = n['ssid'].decode('utf-8', 'replace')
            f = font(24)
            while d.textlength(label, font=f) > PW - 130 and len(label) > 4:
                label = label[:-2] + '…'
            d.text((36, y + 16), label, font=f, fill=C_TXT)
            b = wifi.bars(n['level']) if wifi else 0
            bx = PW - 86                               # signal bars, right edge
            for k in range(4):
                x = bx + k * 12
                h = 8 + k * 8
                d.rectangle((x, y + 50 - h, x + 8, y + 50), fill=C_TXT if k < b else (80, 80, 92))
            if n['secured']:                           # small padlock in the bars' top-left corner
                lx, ly = bx - 2, y + 10
                d.arc((lx + 2, ly, lx + 12, ly + 12), 180, 360, fill=C_DIM, width=2)
                d.rectangle((lx, ly + 6, lx + 14, ly + 17), fill=C_DIM)
            self.buttons.append((box, ('wifi_pick', n)))
        wf['page'] = page
        down = len(rows) > (page + 1) * per
        up = page > 0
        off, off_fg = (32, 32, 40), (75, 75, 88)       # greyed out: no action
        self.grid(d, [('▲', ('wifi_up',) if up else None, C_BTN if up else off, 34, None,
                       C_TXT if up else off_fg),
                      ('▼', ('wifi_down',) if down else None, C_BTN if down else off, 34, None,
                       C_TXT if down else off_fg),
                      ('RESCAN', ('wifi_rescan',), C_BTN, 24)], top=590, rows_h=74, cols=3)

    KB_ROWS = {
        'abc': ['1234567890', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm.-_'],
        'sym': ['1234567890', '!@#$%^&*()', '-_=+[]{}\\|', ';:\'",.<>/?'],
    }

    def page_wifi_kb(self, d, st):
        wf = self.wf
        if wf['kb_for'] == 'ssid':
            title = 'Network name (hidden network)'
        else:
            title = 'Password for %s' % wf['target'].decode('utf-8', 'replace')
        d.text((12, 158), title[:34], font=font(22), fill=C_TXT)
        # text field
        d.rounded_rectangle((8, 190, PW - 8, 244), radius=10, fill=(12, 12, 16), outline=(90, 90, 100), width=2)
        shown = wf['text'] if wf['show'] else '•' * len(wf['text'])
        f = font(28)
        while d.textlength(shown + '|', font=f) > PW - 40 and shown:
            shown = shown[1:]                          # show the end of a long entry
        d.text((20, 200), shown + '|', font=f, fill=C_TXT)
        if not wf['text'] and wf['kb_for'] == 'psk' and wf['hidden']:
            d.text((44, 208), 'empty = open network', font=font(18), fill=C_DIM)
        # keys
        kw, gap, top = 43, 4, 254
        for r, row in enumerate(self.KB_ROWS[wf['mode']]):
            x0 = 6 + (len(row) < 10) * (kw + gap) // 2
            y = top + r * 62
            for i, ch in enumerate(row):
                label = ch.upper() if wf['shift'] and wf['mode'] == 'abc' else ch
                x = x0 + i * (kw + gap)
                self.button(d, (x, y, x + kw, y + 56), label, ('kb', ch), C_BTN, 26)
        y = top + 4 * 62
        u = kw + gap                                   # bottom row in key units
        if wf['mode'] == 'abc':
            self.button(d, (6, y, 6 + 2 * u - gap, y + 56), '?123', ('kb_mode',), C_BAR, 22)
            self.button(d, (6 + 2 * u, y, 6 + 4 * u - gap, y + 56), 'SHIFT', ('kb_shift',),
                        C_ON if wf['shift'] else C_BAR, 20)
        else:
            self.button(d, (6, y, 6 + 2 * u - gap, y + 56), 'ABC', ('kb_mode',), C_BAR, 22)
            self.button(d, (6 + 2 * u, y, 6 + 3 * u - gap, y + 56), '`', ('kb', '`'), C_BTN, 26)
            self.button(d, (6 + 3 * u, y, 6 + 4 * u - gap, y + 56), '~', ('kb', '~'), C_BTN, 26)
        self.button(d, (6 + 4 * u, y, 6 + 8 * u - gap, y + 56), 'space', ('kb', ' '), C_BTN, 20)
        self.button(d, (6 + 8 * u, y, PW - 6, y + 56), 'DEL', ('kb_bs',), C_BAR, 20)
        # actions
        y += 66
        ok = 'NEXT' if wf['kb_for'] == 'ssid' else 'CONNECT'
        # (cancel = the BACK button in the bottom bar)
        self.button(d, (6, y, 186, y + 58), 'HIDE' if wf['show'] else 'SHOW', ('kb_show',), C_BAR, 24)
        self.button(d, (194, y, PW - 6, y + 58), ok, ('kb_ok',), C_ON, 26)

    # ---- touch -----------------------------------------------------------
    def hit(self, u, v):
        for (x0, y0, x1, y1), action in reversed(self.buttons):
            if x0 <= u < x1 and y0 <= v < y1:
                return action
        return None

    def on_touch(self, ev):
        kind, u, v = ev
        self.last_touch = time.time()
        if kind == 'down':
            self.press = (u, v, time.time())
        elif kind == 'up' and self.press:
            a0 = self.hit(self.press[0], self.press[1])
            a1 = self.hit(u, v)
            self.press = None
            if a0 is not None and a0 == a1 and a0[0] != 'estop':
                if self.confirm and a0[0] not in ('cancel',):
                    self.confirm = None
                self.run(a0)

    def check_hold(self):
        if self.press and self.hit(self.press[0], self.press[1]) == ('estop',):
            if time.time() - self.press[2] >= HOLD_STOP:
                self.press = None
                self.emergency_stop()

    # ---- drawing ---------------------------------------------------------
    def pressed(self, box):
        """Is the finger currently down on this box (visual feedback)?"""
        if not self.press:
            return False
        u, v = self.press[0], self.press[1]
        return box[0] <= u < box[2] and box[1] <= v < box[3]

    def button(self, d, box, label, action, colour=C_BTN, size=30, sub=None, fg=C_TXT):
        x0, y0, x1, y1 = box
        down = action is not None and self.pressed(box)
        if down:
            # pressed: lighter face, label pushed down 2 px
            colour = tuple(min(255, c + 45) for c in colour)
        d.rounded_rectangle(box, radius=14, fill=colour)
        if down:
            y0, y1 = y0 + 2, y1 + 2
        while size > 16 and d.textlength(label, font=font(size)) > x1 - x0 - 20:
            size -= 2                                  # shrink long labels to fit
        f = font(size)
        tw = d.textlength(label, font=f)
        ty = (y0 + y1) // 2 - size // 2 - (10 if sub else 0)
        d.text(((x0 + x1 - tw) // 2, ty), label, font=f, fill=fg)
        if sub:
            fs = font(18)
            sw = d.textlength(sub, font=fs)
            d.text(((x0 + x1 - sw) // 2, ty + size + 6), sub, font=fs, fill=C_DIM)
        if action is not None:
            self.buttons.append((box, action))

    def grid(self, d, items, top, rows_h=110, cols=2):
        w = (PW - 30 * 2 - 20 * (cols - 1)) // cols
        for i, it in enumerate(items):
            if it is None:
                continue
            x = 30 + (i % cols) * (w + 20)
            y = top + (i // cols) * (rows_h + 16)
            self.button(d, (x, y, x + w, y + rows_h), *it)

    def render(self):
        im = Image.new('RGB', (PW, PH), C_BG)
        d = ImageDraw.Draw(im)
        self.buttons = []
        st = self.st
        if self.dimmed():
            return Image.new('RGB', (PW, PH), (0, 0, 0))
        if self.screen.startswith('wifi'):
            # WiFi setup works with or without Klipper/Moonraker
            if st is not None:
                self.header(d, st)
            else:
                d.rectangle((0, 0, PW, 64), fill=C_BAR)
                d.text((20, 14), 'Sindoh DP200', font=font(30), fill=C_TXT)
            getattr(self, 'page_' + self.screen)(d, st)
            if self.confirm:
                self.overlay_confirm(d)
            self.footer(d)
            return im
        if st is None:
            d.text((30, 330), 'Waiting for Klipper...', font=font(32), fill=C_TXT)
            if self.err:
                for i, l in enumerate(wrap(d, self.err, font(20), PW - 60)[:4]):
                    d.text((30, 390 + i * 28), l, font=font(20), fill=C_DIM)
            self.button(d, (30, 520, 250, 610), 'WIFI', ('screen', 'wifi'), C_BTN, 30, 'setup')
            self.footer(d)
            return im
        self.header(d, st)
        state = st['webhooks']['state']
        if state != 'ready':
            self.page_error(d, st)
        else:
            pstate = st['print_stats']['state']
            if pstate in ('printing', 'paused') and self.screen == 'home':
                self.screen = 'print'
            if pstate not in ('printing', 'paused') and self.screen == 'print':
                self.screen = 'home'
            getattr(self, 'page_' + self.screen)(d, st)
        if self.confirm:
            self.overlay_confirm(d)
        self.footer(d)
        return im

    def dimmed(self):
        idle = self.st and self.st['print_stats']['state'] not in ('printing', 'paused') \
            and not self.busy and self.st['extruder']['target'] == 0 \
            and self.st['heater_bed']['target'] == 0
        t = self.settings.get('timeout', DIM_AFTER)
        return idle and t and time.time() - self.last_touch > t

    def header(self, d, st):
        d.rectangle((0, 0, PW, 64), fill=C_BAR)
        d.text((20, 14), 'Sindoh DP200', font=font(30), fill=C_TXT)
        state = st['webhooks']['state']
        col = (80, 200, 120) if state == 'ready' else (230, 80, 70)
        txt = state.upper()
        d.text((PW - 20 - d.textlength(txt, font=font(20)), 22), txt, font=font(20), fill=col)
        e, b = st['extruder'], st['heater_bed']
        d.text((20, 78), 'Nozzle', font=font(18), fill=C_DIM)
        d.text((20, 100), '%.0f/%.0f°' % (e['temperature'], e['target']), font=font(36), fill=C_NOZ)
        d.text((250, 78), 'Bed', font=font(18), fill=C_DIM)
        d.text((250, 100), '%.0f/%.0f°' % (b['temperature'], b['target']), font=font(36), fill=C_BED)

    # page -> page that BACK returns to (None: top level, no BACK)
    PARENT = {'filament': 'home', 'preheat': 'home', 'move': 'home', 'system': 'home',
              'wifi': 'system', 'wifi_list': 'wifi', 'display': 'system', 'timeout': 'display'}

    def back_action(self):
        if self.confirm:
            return ('cancel',)                         # BACK = NO in a dialog
        if self.screen == 'wifi_kb':
            return ('kb_cancel',)
        ready = self.st is not None and self.st['webhooks']['state'] == 'ready'
        if not ready:
            # only the WiFi pages work without Klipper; their top goes back to
            # the waiting/error page (screen "home")
            if self.screen == 'wifi':
                return ('screen', 'home')
            if not self.screen.startswith('wifi'):
                return None
        parent = self.PARENT.get(self.screen)
        return ('screen', parent) if parent else None

    def footer(self, d):
        y = PH - 86
        if self.busy:
            d.text((20, y - 34), 'Running: ' + self.busy, font=font(20), fill=C_WARN)
        elif self.msg and time.time() < self.msg[1]:
            d.text((20, y - 34), self.msg[0][:40], font=font(20), fill=C_WARN)
        d.rectangle((0, y, PW, PH), fill=C_BAR)
        # BACK: one fixed spot on every page (bottom left); none on top-level pages
        back = self.back_action()
        bbox = (14, y + 10, 150, PH - 10)
        if back is not None:
            self.button(d, bbox, 'BACK', back, C_BTN, 24)
            down = 2 if self.pressed(bbox) else 0      # arrow follows the pressed label
            cy = (bbox[1] + bbox[3]) // 2 + down
            d.polygon([(22, cy), (32, cy - 8), (32, cy + 8)], fill=C_TXT)
        d.text((162, y + 16), self.ip, font=font(18), fill=C_DIM)
        d.text((162, y + 46), time.strftime('%H:%M'), font=font(18), fill=C_DIM)
        box = (PW - 170, y + 10, PW - 14, PH - 10)
        held = 0.0
        if self.press and self.hit(self.press[0], self.press[1]) == ('estop',):
            held = min((time.time() - self.press[2]) / HOLD_STOP, 1.0)
        d.rounded_rectangle(box, radius=12, fill=C_RED)
        if held:
            d.rounded_rectangle((box[0], box[1], box[0] + int((box[2] - box[0]) * held), box[3]),
                                radius=12, fill=(240, 60, 60))
        d.text((box[0] + 30, box[1] + 6), 'STOP', font=font(30), fill=C_TXT)
        d.text((box[0] + 22, box[1] + 42), 'hold 1 s', font=font(16), fill=(240, 200, 200))
        self.buttons.append((box, ('estop',)))

    def lamp_on(self, st):
        return st.get('output_pin lamp', {}).get('value', 0) > 0

    # ---- pages -----------------------------------------------------------
    def page_home(self, d, st):
        ps = st['print_stats']
        d.text((20, 160), 'Job: %s' % ps['state'], font=font(26), fill=C_TXT)
        if ps.get('filename'):
            d.text((20, 196), ps['filename'][:34], font=font(18), fill=C_DIM)
        lamp = self.lamp_on(st)
        self.grid(d, [
            ('LAMP', ('gcode', 'LAMP_TOGGLE', 'Lamp'), C_ON if lamp else C_BTN, 30, 'on' if lamp else 'off'),
            ('FILAMENT', ('screen', 'filament')),
            ('PREHEAT', ('screen', 'preheat')),
            ('MOVE', ('screen', 'move')),
            ('SYSTEM', ('screen', 'system')),
            ('COOL DOWN', ('gcode', 'TURN_OFF_HEATERS', 'Cool down')),
        ], top=236)

    def page_print(self, d, st):
        ps, vs = st['print_stats'], st.get('virtual_sdcard', {})
        prog = st.get('display_status', {}).get('progress') or vs.get('progress', 0.0)
        name = ps.get('filename') or '?'
        d.text((20, 160), name[:30], font=font(22), fill=C_TXT)
        d.rounded_rectangle((20, 196, PW - 20, 236), radius=8, outline=(90, 90, 100), width=2)
        d.rounded_rectangle((22, 198, 22 + int((PW - 44) * prog), 234), radius=7, fill=(80, 200, 120))
        el = ps.get('print_duration', 0.0)
        left = el / prog - el if prog > 0.01 else 0
        d.text((20, 246), '%d %%   %s   left %s' % (prog * 100, fmt_time(el), fmt_time(left) if left else '--'),
               font=font(22), fill=C_TXT)
        zoff = st['gcode_move']['homing_origin'][2]
        d.text((20, 280), '%s    Z offset %+.3f' % (ps['state'].upper(), zoff), font=font(20),
               fill=C_WARN if ps['state'] == 'paused' else C_DIM)
        paused = ps['state'] == 'paused'
        lamp = self.lamp_on(st)
        self.grid(d, [
            ('RESUME' if paused else 'PAUSE', ('gcode', 'RESUME' if paused else 'PAUSE')),
            ('CANCEL', ('confirm', 'Cancel the print?', ('gcode', 'CANCEL_PRINT', 'Cancel')), C_RED),
            ('Z -0.025', ('gcode', 'SET_GCODE_OFFSET Z_ADJUST=-0.025 MOVE=1', 'Z -0.025'), C_BTN, 26, 'closer'),
            ('Z +0.025', ('gcode', 'SET_GCODE_OFFSET Z_ADJUST=0.025 MOVE=1', 'Z +0.025'), C_BTN, 26, 'further'),
            ('LAMP', ('gcode', 'LAMP_TOGGLE', 'Lamp'), C_ON if lamp else C_BTN, 30, 'on' if lamp else 'off'),
        ], top=320, rows_h=96)

    def page_filament(self, d, st):
        lever = st.get('filament_switch_sensor cartridge_lever', {})
        enc = st.get('filament_motion_sensor filament_encoder', {})
        d.text((20, 160), 'Filament', font=font(28), fill=C_TXT)
        cart = st.get('dp200_cartridge') or {}
        if cart.get('present'):
            d.text((20, 200), 'Cartridge: %s, %.0f of %d m left (%.0f%%)'
                   % (cart.get('material', '?'), cart.get('remaining_m', 0), cart.get('total_m', 0),
                      cart.get('remaining_percent', 0)), font=font(20), fill=C_TXT)
        else:
            d.text((20, 200), 'Cartridge: none (open filament)', font=font(20), fill=C_DIM)
        d.text((20, 228), 'Runout encoder: %s' % ('on' if enc.get('enabled') else 'off'),
               font=font(20), fill=C_DIM)
        items = []
        for mat in ('PLA', 'ABS'):
            items.append(('LOAD ' + mat, ('confirm', 'Heat and LOAD %s?' % mat,
                                          ('gcode', 'LOAD_FILAMENT MATERIAL=' + mat, 'Load ' + mat))))
        for mat in ('PLA', 'ABS'):
            items.append(('UNLOAD ' + mat, ('confirm', 'Heat and UNLOAD %s?' % mat,
                                            ('gcode', 'UNLOAD_FILAMENT MATERIAL=' + mat, 'Unload ' + mat))))
        items.append(('UNLOCK', ('confirm', 'Release the cartridge latch for 4 s? Unload the filament first.',
                                 ('gcode', 'CARTRIDGE_RELEASE', 'Cartridge release')), C_BTN, 28, 'cartridge'))
        self.grid(d, items, top=270, rows_h=96)

    def page_preheat(self, d, st):
        d.text((20, 160), 'Preheat', font=font(28), fill=C_TXT)
        items = []
        for name, noz, bed in PRESETS:
            items.append((name, ('confirm', 'Preheat %s: nozzle %d, bed %d?' % (name, noz, bed),
                                 ('gcode', 'M104 S%d\nM140 S%d' % (noz, bed), 'Preheat ' + name)),
                          C_BTN, 30, '%d / %d' % (noz, bed)))
        items.append(('COOL DOWN', ('gcode', 'TURN_OFF_HEATERS', 'Cool down')))
        self.grid(d, items, top=210)

    def page_move(self, d, st):
        homed = st['toolhead'].get('homed_axes', '')
        d.text((20, 160), 'Move / maintenance', font=font(28), fill=C_TXT)
        d.text((20, 200), 'Homed: %s' % (homed.upper() or 'no'), font=font(20), fill=C_DIM)
        self.grid(d, [
            ('HOME ALL', ('confirm', 'Home all axes?', ('gcode', 'G28', 'Home'))),
            ('LOWER BED', ('confirm', 'Lower the bed to Z%d?' % LOWER_BED_Z,
                           ('gcode', '_SINDOH_ENSURE_HOMED\nG90\nG1 Z%d F600' % LOWER_BED_Z, 'Lower bed'))),
            ('CLEAN', ('confirm', 'Heat, purge and wipe the nozzle?',
                       ('gcode', 'CLEAN_NOZZLE', 'Clean nozzle')), C_BTN, 30, 'nozzle'),
            ('MOTORS OFF', ('gcode', 'M84', 'Motors off')),
            ('BIN EMPTIED', ('gcode', 'BIN_EMPTIED', 'Bin emptied'), C_BTN, 24),
        ], top=240)

    def page_system(self, d, st):
        d.text((20, 160), 'System', font=font(28), fill=C_TXT)
        d.text((20, 200), 'Web: http://%s/' % self.ip, font=font(20), fill=C_DIM)
        d.text((20, 228), 'Klipper: %s' % st['webhooks']['state'], font=font(20), fill=C_DIM)
        self.grid(d, [
            ('FIRMWARE', ('confirm', 'FIRMWARE_RESTART? (stops everything)',
                          ('post', '/printer/firmware_restart', 'Firmware restart')), C_BTN, 28, 'restart'),
            ('KLIPPER', ('confirm', 'Restart Klipper host?', ('post', '/printer/restart', 'Restart')),
             C_BTN, 28, 'restart'),
            ('WIFI', ('screen', 'wifi'), C_BTN, 30, 'network'),
            ('DISPLAY', ('screen', 'display'), C_BTN, 28, 'screen'),
        ], top=270)

    def page_display(self, d, st):
        t = self.settings.get('timeout', DIM_AFTER)
        d.text((20, 160), 'Display', font=font(28), fill=C_TXT)
        d.text((20, 204), 'Turns black when idle (no print, heaters off)', font=font(18), fill=C_DIM)
        d.text((20, 230), 'and wakes on the first tap.', font=font(18), fill=C_DIM)
        self.grid(d, [
            ('TIMEOUT', ('screen', 'timeout'), C_BTN, 28, fmt_timeout(t)),
        ], top=280)

    def page_timeout(self, d, st):
        cur = self.settings.get('timeout', DIM_AFTER)
        d.text((20, 160), 'Screen timeout', font=font(28), fill=C_TXT)
        items = [(fmt_timeout(t).upper(), ('set_timeout', t), C_ON if t == cur else C_BTN, 28)
                 for t in TIMEOUTS]
        self.grid(d, items, top=210, rows_h=100)

    def page_error(self, d, st):
        wh = st['webhooks']
        d.rectangle((0, 160, PW, 480), fill=(90, 24, 24))
        d.text((20, 172), 'Klipper: %s' % wh['state'].upper(), font=font(28), fill=C_TXT)
        for i, l in enumerate(wrap(d, wh.get('state_message', ''), font(20), PW - 40)[:9]):
            d.text((20, 214 + i * 28), l, font=font(20), fill=(240, 210, 210))
        self.grid(d, [
            ('FIRMWARE', ('post', '/printer/firmware_restart', 'Firmware restart'), C_BTN, 28, 'restart'),
            ('KLIPPER', ('post', '/printer/restart', 'Restart'), C_BTN, 28, 'restart'),
            ('WIFI', ('screen', 'wifi'), C_BTN, 30, 'setup'),
        ], top=500, rows_h=80)

    def overlay_confirm(self, d):
        q, action = self.confirm
        self.buttons = [b for b in self.buttons if b[1] == ('estop',)]   # modal (STOP stays)
        d.rectangle((0, 64, PW, PH - 86), fill=(10, 10, 14))
        d.rounded_rectangle((20, 220, PW - 20, 560), radius=16, fill=C_BAR)
        for i, l in enumerate(wrap(d, q, font(28), PW - 80)[:4]):
            d.text((40, 250 + i * 38), l, font=font(28), fill=C_TXT)
        self.button(d, (40, 440, 220, 530), 'YES', action, C_ON)
        self.button(d, (260, 440, PW - 40, 530), 'NO', ('cancel',))

def load_settings():
    try:
        with open(SETTINGS) as f:
            s = json.load(f)
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}

def save_settings(s):
    tmp = SETTINGS + '.tmp'
    try:
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        with open(tmp, 'w') as f:
            json.dump(s, f)
        os.replace(tmp, SETTINGS)
        return True
    except OSError:
        return False

def fmt_timeout(s):
    return 'never' if not s else '%d min' % (s // 60) if s >= 60 else '%d s' % s

def unblank():
    """Switch the panel's display DMA back on. The kernel's text console
    blanks it after 10 min without keyboard input (dp200-start.sh turns that
    off; this is the safety net)."""
    try:
        with open('/sys/class/graphics/fb0/blank', 'w') as f:
            f.write('0')
    except OSError:
        pass

def view_key(ui):
    """The status values as displayed (rounded), so a poll that changes
    nothing visible does not cost a redraw."""
    st = ui.st
    if st is None:
        return None
    ps, e, b = st['print_stats'], st['extruder'], st['heater_bed']
    prog = st.get('display_status', {}).get('progress') or st.get('virtual_sdcard', {}).get('progress', 0)
    return (st['webhooks']['state'], st['webhooks'].get('state_message'), ps['state'], ps.get('filename'),
            round(e['temperature']), e['target'], round(b['temperature']), b['target'],
            int(prog * 100), int(ps.get('print_duration', 0) // 60),
            st.get('output_pin lamp', {}).get('value'), st['toolhead'].get('homed_axes'),
            st['gcode_move']['homing_origin'][2],
            st.get('filament_switch_sensor cartridge_lever', {}).get('filament_detected'),
            st.get('filament_motion_sensor filament_encoder', {}).get('enabled'), ui.ip,
            tuple(sorted((st.get('dp200_cartridge') or {}).items(), key=lambda kv: kv[0]))
            if st.get('dp200_cartridge') else None)

# ---------------------------------------------------------------------------
def main():
    ui = UI()
    if '--demo' in sys.argv:
        out = sys.argv[sys.argv.index('--demo') + 1]
        ui.st = query()
        if len(sys.argv) > sys.argv.index('--demo') + 2:
            ui.screen = sys.argv[sys.argv.index('--demo') + 2]
        ui.render().save(out)
        return
    panel, touch = Panel(), Touch()
    unblank()
    unblanked = time.time()
    next_poll = 0.0
    last_key = None
    while True:
        now = time.time()
        polled = now >= next_poll
        if polled:
            try:
                ui.st, ui.err = query(), None
                ui.ip = my_ip()
            except Exception as e:
                ui.st, ui.err = None, str(getattr(e, 'reason', e))
            busy = ui.st and (ui.st['print_stats']['state'] in ('printing', 'paused')
                              or ui.st['extruder']['target'] or ui.st['heater_bed']['target'])
            next_poll = now + (REFRESH_BUSY if busy or ui.busy else
                               5.0 if ui.dimmed() else REFRESH_IDLE)
        events = touch.poll()
        woke = ui.dimmed() and any(e[0] == 'down' for e in events)
        if any(e[0] == 'down' for e in events) and time.time() - unblanked > 60:
            unblank()                   # in case the kernel console blanked the panel
            unblanked = time.time()
        for ev in events:
            if woke:                    # first touch only wakes the screen
                ui.last_touch = time.time()
                ui.press = None
                continue
            ui.on_touch(ev)
        ui.check_hold()
        ui.wifi_tick()
        # Redraw only when something can have changed: new status, touch,
        # STOP being held, the clock minute, a message or busy state, dimming,
        # WiFi state (scan results, connect progress).
        key = (time.strftime('%H:%M'), ui.busy, ui.msg and time.time() < ui.msg[1],
               bool(ui.dimmed()), ui.screen, ui.confirm is not None, view_key(ui), ui.err,
               ui.wf['rev'])
        if events or ui.press or key != last_key:
            panel.show(ui.render())
            last_key = key
        timeout = 0.05 if ui.press else max(0.0, min(next_poll - time.time(), 0.5))
        select.select([touch.fd], [], [], timeout)

if __name__ == '__main__':
    main()
