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
import json, os, re, select, shutil, socket, struct, sys, threading, time, urllib.error, urllib.parse, urllib.request
from PIL import Image, ImageChops, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import dp200_wifi as wifi              # WiFi setup (install/display/dp200_wifi.py)
except ImportError:
    wifi = None
try:
    import dp200_net as net                # port info / IP settings (install/display/dp200_net.py)
except ImportError:
    net = None

PW, PH = 480, 800                     # portrait, as mounted
FB_W, FB_H = 800, 480                 # fb0 geometry (stock: two pages, 800x960 virtual)
# Stock kernel 3.2 names the touch device /dev/event0; mainline uses /dev/input/event0
FB = '/dev/fb0'
EV = next((p for p in ('/dev/event0', '/dev/input/event0') if os.path.exists(p)), '/dev/event0')
API = 'http://127.0.0.1:7125'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
MONO = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'

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
# A G-code request the screen waits on (LOAD: 1-3 min) whose reply does not
# come: once Klipper is idle (idle_timeout not "Printing") this long, the
# script has ended. The busy state is released then and the outcome is read
# from Moonraker's G-code log instead (a LOAD stopped on 11-12 and the reply
# never came; the screen stayed busy and refused every button).
BUSY_MIN = 10.0                       # s a request runs before Klipper's idle state counts
IDLE_RELEASE = 5.0                    # s of idle Klipper that end a request

# Front power button: GPIO bank 5 pin 27, 1 = pressed (found 2026-10-22).
# A short press opens the POWER page. Holding it ~HW_CUT s makes the
# power-management MCU cut the power (hardware, no clean shutdown); this app
# only warns. dp200-powerkey.sh syncs the cards on every press and shuts down
# cleanly after LONG_POWER s if the hardware didn't (other SW1-4 settings).
KEY_REG, KEY_BIT = 0xF8045000, 1 << 27
HW_CUT = 2.0                          # measured roughly: "2 s hold" switched it off
HOLD_WARN = 0.4                       # s held before the warning appears
LONG_POWER = 5.0
POWER_REQ = '/run/dp200/power'        # "reboot" / "poweroff" for dp200-powerkey.sh
# Shutdown/reboot progress: the stop scripts end this app first, so it draws
# one frame per step beforehand (raw fb data, in RAM). rc.dp200 stop and the
# init (dp200-powerkey.sh on stock) copy each frame to the panel as its step
# starts, and done.fb once the files are saved and the root is read-only.
SHUT_DIR = '/tmp/dp200-shutdown'
SHUT_STEPS = ('Web page and camera', 'Moonraker', 'Klipper',
              'Heaters and motors off', 'Saving files')
BOOTBAR_STOP = '/sys/module/dp200_bootbar/parameters/stop'
# Back to stock with a Sindoh update stick (our kernel only: the guarded
# NAND driver's write window exists; under the stock kernel stock handles
# its sticks itself). A stick with _update_rodin/update.she plugged in ->
# two confirmations -> REVERT_MARK in our root + reboot; the nandboot
# initramfs then restores stock from mtd5, and stock runs the stick's
# update (docs/end_goal_install_plan.md, stage 3).
OUR_KERNEL = '/sys/module/marvell_nand/parameters/write_window'
REVERT_MARK = '/.dp200-revert'
STICK_MNT = '/run/dp200/stick'
STICK_UPDATE = '_update_rodin/update.she'

# Preheat presets (nozzle, bed); bed max_temp is 100, nozzle 260
PRESETS = (('PLA', 200, 60), ('ABS', 240, 90))
LOWER_BED_Z = 120                     # Z grows downwards on this machine (bed moves down)
# Purge bin: _SINDOH_BIN_COUNT counts purges in save_variables bin_count and
# asks for emptying from bin_threshold (_DP200, dp200_macros.cfg) on
BIN_THRESHOLD = 15
BIN_DROP = 70                         # EMPTY_BIN lowers the bed this far (bin_drop)
# Custom macro buttons (MOVE -> MACROS): a JSON file in Klipper's config
# folder, so it can also be edited in Mainsail. {"buttons": [{"label":
# "PURGE", "gcode": "MY_PURGE"}, ...]}; every button asks before it runs.
MACROS_FILE = '/home/klipper/printer_data/config/dp200_screen_macros.json'
MAC_PER_PAGE = 8                      # buttons per MACROS page
MAC_EDIT_PER_PAGE = 10                # macros per EDIT page
RESUME_Q = 'Resume the print? The head goes back to the part.'

# Input shaping with a USB accelerometer (docs/input_shaping.md): the sensor
# config is included only while it has the .cfg name (see dp200_printer.cfg)
ADXL_ON = '/home/klipper/printer_data/config/dp200_adxl.cfg'
ADXL_OFF = ADXL_ON + '.off'
NUMPY_LINK = '/usr/local/lib/dp200-numpy/numpy'   # install/input_shaping/setup_numpy.sh
# Filament dryer presets (material, bed C, hours) and time choices; the
# build sheet's continuous limit comes from _DRY's sheet_max (dp200_macros.cfg)
DRY_PRESETS = (('PLA', 50, 4), ('PETG', 65, 4), ('TPU', 50, 5),
               ('ABS', 80, 4), ('ASA', 80, 4), ('NYLON', 85, 8))
DRY_HOURS = (2, 4, 6, 8, 12)
# LOAD / UNLOAD temperatures (nozzle C). PLA and ABS run the macros' stock
# settings (MATERIAL=); the others and CUSTOM pass TEMP=. The extruder's
# max_temp is 260 and min_extrude_temp 170 (dp200_printer.cfg).
FIL_PRESETS = (('PLA', 230), ('PETG', 240), ('ABS', 250),
               ('ASA', 250), ('TPU', 230), ('NYLON', 255))
FIL_STOCK = ('PLA', 'ABS')
FIL_MIN, FIL_MAX = 180, 260
FIL_STEPS = (-10, -5, 5, 10)
# Bed level page: 4x4 probe grid, the two front screws and the fixed back support
PROBE_RE = re.compile(r'probe: at ([\d.]+),([\d.]+) bed will contact at z=(-?[\d.]+)')
BL_SCREWS = (('Left', 8, 8), ('Right', 202, 8))   # ~10 mm in from the front corners
BL_PIVOT = (105, 196)                             # fixed back support (no screw)
BL_PLATE = (-2, -2, 212, 205.5)                   # plate in printer coordinates
BL_OK = 0.05                                      # mm: a screw closer than this is level
# Measured 2026-10-28: 1/4 turn clockwise (seen from above) raised the left
# front corner ~0.2 mm, so ~0.8 mm per turn (M4 would be 0.7) and CW = raise.
BL_MM_PER_TURN = 0.8
SHAPER_RE = re.compile(r'Recommended shaper_type_([xy]) = (\w+), shaper_freq_\1 = ([\d.]+) Hz')

OBJECTS = ('webhooks', 'print_stats', 'virtual_sdcard', 'display_status', 'extruder',
           'heater_bed', 'output_pin lamp', 'gcode_move', 'toolhead', 'idle_timeout',
           'filament_switch_sensor cartridge_lever', 'filament_motion_sensor filament_encoder',
           'dp200_cartridge', 'gcode_macro _DRY', 'gcode_macro BED_CLEAR', 'manual_probe',
           'exclude_object', 'save_variables', 'gcode_macro PRINT_START')

C_BG = (20, 20, 26)
C_BAR = (36, 36, 44)
C_TXT = (235, 235, 235)
C_DIM = (160, 160, 172)
C_BTN = (50, 50, 62)
C_ON = (55, 140, 90)
C_RED = (160, 40, 40)
C_WARN = (210, 140, 40)
C_FULL = (130, 82, 18)                # a button that wants attention (full bin)
C_NOZ = (255, 170, 80)
C_BED = (110, 180, 255)

_fonts = {}

def font(size, path=FONT):
    if (size, path) not in _fonts:
        try:
            _fonts[size, path] = ImageFont.truetype(path, size)
        except OSError:
            _fonts[size, path] = font(size) if path != FONT else ImageFont.load_default()
    return _fonts[size, path]

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

def fb_pages(path):
    """Row offsets of the fb's pages: stock 3.2 has two (800x960 virtual),
    mainline simplefb only one (800x480), and writing past its end fails."""
    try:
        with open('/sys/class/graphics/%s/virtual_size' % os.path.basename(path)) as f:
            vh = int(f.read().split(',')[1])
    except (OSError, ValueError, IndexError):
        try:                                    # a plain file (tests): its size
            vh = os.path.getsize(path) // (FB_W * 2)
        except OSError:
            vh = FB_H
    return tuple(range(0, max(vh // FB_H, 1) * FB_H, FB_H))

def draw_shutdown(d, what, step):
    """Shutdown ('poweroff') or reboot progress: step 1..len(SHUT_STEPS)
    running, one more = finished."""
    d.rectangle((0, 0, PW, PH), fill=(0, 0, 0))
    n = len(SHUT_STEPS)
    if step > n:
        if what == 'reboot':
            d.text((PW // 2, 360), 'Restarting...', font=font(36), fill=C_TXT, anchor='mm')
            # (the boot logo may be the owner's own: no 'Sindoh logo')
            d.text((PW // 2, 420), 'Rebooting now.', font=font(22),
                   fill=C_DIM, anchor='mm')
        else:
            # the old Windows 95 screen, in its colours
            for i, l in enumerate(("It's now safe", 'to turn off', 'your printer.')):
                d.text((PW // 2, 260 + i * 62), l, font=font(46), fill=(255, 160, 0), anchor='mm')
            for i, l in enumerate(('Hold the POWER BUTTON', 'for about 2 seconds.')):
                d.text((PW // 2, 500 + i * 36), l, font=font(24), fill=C_DIM, anchor='mm')
        return
    d.text((30, 130), 'Restarting' if what == 'reboot' else 'Shutting down',
           font=font(36), fill=C_TXT)
    d.text((30, 182), 'Step %d of %d' % (step, n), font=font(22), fill=C_DIM)
    for i, name in enumerate(SHUT_STEPS):
        y = 250 + i * 58
        if i < step - 1:                       # done: a tick
            d.line((36, y + 16, 46, y + 26, 64, y + 4), fill=C_ON, width=5)
            col = C_TXT
        elif i == step - 1:                    # running
            d.ellipse((38, y + 4, 60, y + 26), fill=C_WARN)
            col = C_TXT
        else:
            d.ellipse((40, y + 6, 58, y + 24), outline=C_DIM, width=2)
            col = C_DIM
        d.text((80, y), name, font=font(26), fill=col)
    frac = (step - 1) / n
    d.rounded_rectangle((30, 560, PW - 30, 596), radius=8, outline=C_DIM, width=2)
    if frac:
        d.rounded_rectangle((32, 562, 32 + int((PW - 64) * frac), 594), radius=7, fill=C_ON)
    d.text((30, 620), "Don't switch it off yet.", font=font(24), fill=C_WARN)

def write_shutdown_frames(what, path=FB):
    """The frames the stop scripts show (SHUT_DIR/1.fb .. N.fb, done.fb), one
    copy per fb page, as Panel.show() writes them."""
    os.makedirs(SHUT_DIR, exist_ok=True)
    pages = len(fb_pages(path))
    for step in range(1, len(SHUT_STEPS) + 2):
        im = Image.new('RGB', (PW, PH))
        draw_shutdown(ImageDraw.Draw(im), what, step)
        raw = rgb565(im.transpose(Image.Transpose.ROTATE_270)) * pages
        name = os.path.join(SHUT_DIR, str(step) if step <= len(SHUT_STEPS) else 'done')
        with open(name + '.tmp', 'wb') as f:
            f.write(raw)
        os.replace(name + '.tmp', name + '.fb')

class Panel:
    def __init__(self, path=FB):
        self.f = open(path, 'r+b', buffering=0)
        self.prev = None
        self.pages = fb_pages(path)

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
        for page in self.pages:                      # every page the fb has
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

class PowerKey:
    """Front power button, read from the GPIO data register (mmap of
    /dev/mem, read only). pressed() is False if the register can't be read."""
    def __init__(self):
        import mmap
        self.m = None
        try:
            fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
            self.m = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ, offset=KEY_REG & ~0xfff)
            os.close(fd)
        except (OSError, ValueError):
            pass

    def pressed(self):
        if self.m is None:
            return False
        return bool(struct.unpack_from('<I', self.m, KEY_REG & 0xfff)[0] & KEY_BIT)

# ---------------------------------------------------------------------------
# Moonraker
# ---------------------------------------------------------------------------
def query():
    q = '&'.join(urllib.parse.quote(o) for o in OBJECTS)
    with urllib.request.urlopen(API + '/printer/objects/query?' + q, timeout=3) as r:
        return json.load(r)['result']['status']

def err_text(e):
    """A query() failure as the waiting page shows it (not '[Errno 111] ...')."""
    r = getattr(e, 'reason', e)
    if isinstance(r, ConnectionRefusedError):
        return 'Moonraker is starting (not answering yet)'
    if isinstance(r, (TimeoutError, socket.timeout)):
        return 'Moonraker is not answering (busy or starting)'
    if isinstance(e, urllib.error.HTTPError):
        return 'Moonraker: Klipper not connected yet (HTTP %d)' % e.code
    return str(r)

def log(msg):
    """A line in the screen app's log (stdout)."""
    print('%s %s' % (time.strftime('%H:%M:%S'), msg), flush=True)

def gcode_lines_since(t0):
    """Moonraker's G-code log (console lines) since t0 (time.time(), same host)."""
    log = get('/server/gcode_store?count=100').get('gcode_store') or []
    return [str(e.get('message', '')) for e in log if e.get('time', 0) >= t0 - 1]

def gcode_error_since(t0, lines=None):
    """The last Klipper error ("!! ...") since t0, without the "!! ", or None."""
    for m in reversed(gcode_lines_since(t0) if lines is None else lines):
        if m.startswith('!! '):
            return m[3:].strip().splitlines()[0][:400]
    return None

def fail_text(e, n=160):
    """Why a Moonraker request failed: for a refused G-code that is
    Klipper's own message in the JSON body (the HTTP reason phrase is just
    'Bad Request' or 'unknown')."""
    if isinstance(e, urllib.error.HTTPError):
        try:
            msg = json.load(e)['error']['message']
            return str(msg).strip().splitlines()[0][:n]
        except Exception:
            return 'HTTP %d' % e.code
    return str(getattr(e, 'reason', e))

def get(path):
    with urllib.request.urlopen(API + path, timeout=5) as r:
        return json.load(r)['result']

def post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(API + path, data=data, method='POST',
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=3600) as r:   # gcode scripts block until done
        return json.load(r)

STOCK_INFO = '/run/dp200/stock_info'          # written at boot by dp200-start.sh (stock side)
BUILD_FILE = '/etc/dp200/build'                # written by make_payload.sh
ON_NAND = '/etc/dp200/on_nand'                 # written by the USB installer
RECOVERY_INFO = '/etc/dp200/recovery_info'     # the installer reads it from mtd5 once

def read_kv(path):
    try:
        with open(path) as f:
            return dict(l.rstrip('\n').split('=', 1) for l in f if '=' in l)
    except OSError:
        return {}

def system_info(ip):
    """(label, value) rows for SYSTEM -> INFO. Files and two local requests
    only; anything missing shows as '-'."""
    def first(path, default='-'):
        try:
            with open(path) as f:
                return f.readline().strip() or default
        except OSError:
            return default
    def req(path, key):
        try:
            return str(get(path).get(key) or '-')
        except Exception:
            return '-'
    stock = read_kv(STOCK_INFO)
    rec = read_kv(RECOVERY_INFO).get('recovery_app')
    try:
        with open('/home/klipper/mainsail/release_info.json') as f:
            mainsail = json.load(f).get('version', '-')
    except (OSError, ValueError):
        mainsail = '-'
    try:
        v = os.statvfs('/')
        disk = '%d MB free of %d MB' % (v.f_bavail * v.f_frsize >> 20, v.f_blocks * v.f_frsize >> 20)
    except OSError:
        disk = '-'
    mem = read_meminfo()
    try:
        with open('/proc/uptime') as f:
            up = int(float(f.read().split()[0]))
        uptime = '%dd %dh %02dm' % (up // 86400, up % 86400 // 3600, up % 3600 // 60)
    except (OSError, ValueError):
        uptime = '-'
    return [
        ('Build', first(BUILD_FILE, 'not stamped (SD build)')),
        ('Installed on', 'internal NAND' if os.path.exists(ON_NAND) else 'microSD card'),
        ('Klipper', req('/printer/info', 'software_version')),
        ('Moonraker', req('/server/info', 'moonraker_version')),
        ('Mainsail', mainsail),
        ('Kernel', stock.get('kernel') or os.uname().release),
        ('Sindoh FW', stock.get('firmware') or ('- (mainline boot)' if not stock else '-')),
        ('Model ID', stock.get('model') or '-'),
        ('Serial', stock.get('serial') or '-'),
        ('Recovery set', 'Sindoh app %s' % rec if rec else '- (read at install)'),
        ('IP address', ip),
        ('Storage', disk),
        ('Memory', mem),
        ('Uptime', uptime),
    ]

def read_meminfo():
    try:
        m = {}
        with open('/proc/meminfo') as f:
            for l in f:
                k, v = l.split(':', 1)
                m[k] = int(v.split()[0])
        # kernel 3.2 has no MemAvailable: free + buffers + page cache
        avail = m.get('MemAvailable', m.get('MemFree', 0) + m.get('Buffers', 0) + m.get('Cached', 0))
        return '%d MB free of %d MB' % (avail >> 10, m.get('MemTotal', 0) >> 10)
    except (OSError, ValueError):
        return '-'

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

def fmt_mins(m):
    m = int(max(m, 0))
    return '%d:%02d' % (m // 60, m % 60)

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
        self.key_down = None           # time the power button went down
        self.power_at = 0.0            # when a reboot/power-off was requested
        self.last_touch = time.time()
        self.ip = my_ip()
        self.settings = load_settings()          # e.g. {'timeout': 600}
        # network pages: port info (refreshed in the background), IP settings draft
        self.net = {'rev': 0, 'info': {}, 'dns': [], 'checked': 0.0, 'busy': False,
                    'iface': 'eth0', 'draft': {}, 'field': 'ip', 'text': ''}
        # WiFi setup state (pages wifi, wifi_list, wifi_kb)
        self.wf = {'rev': 0, 'status': {}, 'saved': 0, 'saved_list': [], 'list': [], 'page': 0,
                   'busy': None, 'checked': 0.0, 'target': b'', 'kb_for': 'psk',
                   'text': '', 'mode': 'abc', 'shift': False, 'show': False, 'hidden': False}
        # input shaping page: last recommended shaper per axis from the console
        self.shp = {'rev': 0, 'checked': 0.0, 'busy': False, 'res': {}}
        # CALIBRATE: paper test mode ('zend' / 'probe'), accepted, PID tuned
        self.cal = {}
        self.dry = {'mat': 'PLA', 'temp': 50, 'hours': 4}   # dryer page selection
        # LOAD/UNLOAD page: which one, and the CUSTOM temperature (remembered)
        self.info = None               # SYSTEM -> INFO rows
        self.upd = {}                  # SYSTEM -> UPDATE: versions from Moonraker
        self.fil = {'mode': 'load', 'temp': int(self.settings.get('fil_custom', 220))}
        self.bed_answered = 0.0        # last BED_CLEAR answer (status lags behind it)
        # bed level page: mode start/probing/result, live points {(col, row): z}
        self.bl = {'rev': 0, 'mode': 'start', 'pts': {}, 'mesh': None, 'xs': None, 'ys': None,
                   't0': 0.0, 'checked': 0.0, 'busy': False}
        # console page: the kernel log, refreshed while shown
        self.con = {'rev': 0, 'checked': 0.0, 'busy': False, 'lines': []}
        # USB sticks seen (sdX names), and which of them hold a Sindoh update
        self.stk = {'checked': 0.0, 'busy': False, 'seen': set(), 'sindoh': set(), 'asked': set()}
        self.last_pstate = None        # print state at the last render (jump to the print page)
        self.fil_fail = None           # a LOAD/UNLOAD that stopped: {'mode', 'msg', 'script'}
        self.busy_tok = None           # the _bg job that holds self.busy
        self.req = None                # the G-code request it waits on (see busy_tick)
        # custom macro buttons: the file's buttons (or its error), the printer's macros (EDIT)
        self.mac = {'buttons': [], 'error': None, 'all': None, 'page': 0, 'edit_page': 0}

    # ---- actions -------------------------------------------------------
    def run(self, action):
        kind = action[0]
        if kind == 'screen':
            self.screen = action[1]
            if self.screen in ('wifi', 'wifi_saved', 'network'):
                self.wifi_refresh()
            if self.screen == 'network':
                self.net['checked'] = 0
            if self.screen == 'console':
                self.con['checked'] = 0
            if self.screen == 'macros':
                self.mac_load()                        # re-read: it may be edited in Mainsail
        elif kind == 'mac_edit':                       # MACROS -> EDIT: the printer's macros
            self.mac_load()
            if self.mac['error']:
                self.flash('Macro file not valid: fix it in Mainsail', 10)
                return
            self.screen = 'macros_edit'
            self._bg('Reading macros', self.mac_list)
        elif kind == 'mac_toggle':
            self.mac_toggle(action[1])
        elif kind == 'mac_more':
            self.mac['page'] += 1
        elif kind == 'mac_edit_more':
            self.mac['edit_page'] += 1
        elif kind.startswith('wifi') or kind.startswith('kb'):
            self.wifi_action(action)
        elif kind.startswith('net') or kind.startswith('np'):
            self.net_action(action)
        elif kind == 'obj_more':
            self.obj_page = getattr(self, 'obj_page', 0) + 1
        elif kind == 'go_home':                        # the HOME button in the header
            if self.screen == 'papertest':
                self.run(('cal_abort',))               # leaving ends the paper test
            self.confirm = None
            self.screen = 'home'
        elif kind == 'cal_start':                      # Z HEIGHT / PROBE OFFSET paper test
            mode = action[1]
            self.cal = {'mode': mode}
            self.screen = 'papertest'
            script = ('BED_CLEAR\nG28\nZ_ENDSTOP_CALIBRATE' if mode == 'zend'
                      else 'BED_CLEAR\nLV_PROBE_CALIBRATE')
            self.bed_answered = time.time()
            self._bg('Homing' if mode == 'zend' else 'Probing',
                     lambda: post('/printer/gcode/script', {'script': script}))
        elif kind == 'cal_accept':
            self._bg('Accepting', self.cal_accept)
        elif kind == 'cal_abort':
            # (after ACCEPT the paper test is over: nothing to abort)
            active = (((self.st or {}).get('manual_probe') or {}).get('is_active')
                      and not self.cal.get('done'))
            self.cal = {}
            self.screen = 'calibrate'
            if active:
                self._bg('Aborting', lambda: post('/printer/gcode/script', {'script': 'ABORT'}))
        elif kind == 'cal_save':                       # [script before] SAVE_CONFIG
            script = (action[1] + '\n' if len(action) > 1 else '') + 'SAVE_CONFIG'
            self.cal = {}
            self.screen = 'calibrate'
            def save():
                try:
                    post('/printer/gcode/script', {'script': script})
                except urllib.error.HTTPError:
                    pass        # SAVE_CONFIG restarts Klipper: the reply can be a disconnect
                self.flash('Saved: Klipper restarts (about 30 s)', 10)
            self._bg('Saving (Klipper restarts)', save)
        elif kind == 'pid_run':
            heater, t = action[1], action[2]
            def run_pid():
                post('/printer/gcode/script',
                     {'script': 'PID_CALIBRATE HEATER=%s TARGET=%d' % (heater, t)})
                self.cal.setdefault('pid_done', []).append(heater)
            self._bg('Tuning %s (5-10 min)' % ('nozzle' if heater == 'extruder' else 'bed'), run_pid)
        elif kind == 'upd_open':                       # SYSTEM -> UPDATE
            self.screen = 'update'
            self._bg('Reading versions', self.upd_status)
        elif kind == 'upd_check':
            self._bg('Checking for updates', lambda: (
                post('/machine/update/refresh?name=mainsail'), self.upd_status()))
        elif kind == 'upd_mainsail':
            self._bg('Updating Mainsail', lambda: (
                post('/machine/update/upgrade?name=mainsail'), self.upd_status(),
                self.flash('Mainsail updated: reload the web page')))
        elif kind == 'info':                           # SYSTEM -> INFO (read once when opened)
            self.info = system_info(self.ip)
            self.screen = 'info'
        elif kind == 'fil_mode':                       # LOAD or UNLOAD: choose the filament
            self.fil['mode'] = action[1]
            self.screen = 'fil_mat'
        elif kind == 'fil_step':                       # CUSTOM temperature +/-
            self.fil['temp'] = max(FIL_MIN, min(FIL_MAX, self.fil['temp'] + action[1]))
        elif kind == 'fil_custom_go':
            t = self.fil['temp']
            if self.settings.get('fil_custom') != t:
                self.settings['fil_custom'] = t
                save_settings(self.settings)
            self.run(fil_confirm(self.fil['mode'], 'CUSTOM', t))
        elif kind == 'set_timeout':
            self.settings['timeout'] = action[1]
            ok = save_settings(self.settings)
            self.flash('Screen timeout: %s%s' % (fmt_timeout(action[1]), '' if ok else ' (not saved!)'))
            self.screen = 'display'
        elif kind == 'confirm':                        # (question, yes[, no])
            why = paused_refusal(action[2], self.st)
            if why:
                self.flash(why, 10)
                return
            self.confirm = with_bed_check(action[1], action[2], self.st) + tuple(action[3:4])
        elif kind == 'cancel':
            self.confirm = None
        elif kind == 'gcode':                          # (script[, label[, after]])
            if action[1].startswith('BED_CLEAR'):
                self.bed_answered = time.time()
            label = action[2] if len(action) > 2 else action[1]
            after = action[3] if len(action) > 3 else None
            if after == 'detach':
                # the bed answer runs a whole print start (~7 min) before it
                # returns: don't hold the busy slot (CANCEL must stay usable)
                def work():
                    try:
                        post('/printer/gcode/script', {'script': action[1]})
                    except Exception as e:
                        self.flash('%s failed: %s' % (label, fail_text(e)))
                threading.Thread(target=work, daemon=True).start()
                return
            req = {'script': action[1], 'label': label, 'after': after, 't0': time.time(),
                   'done': False, 'idle_since': None}
            self._bg(label, lambda: self.gcode_then(req), req)
        elif kind == 'post':
            self._bg(action[2], lambda: post(action[1]))
        elif kind == 'dry_mat':
            self.dry.update(mat=action[1], temp=action[2], hours=action[3])
        elif kind == 'dry_hours':
            self.dry['hours'] = action[1]
        elif kind == 'bl_probe':
            self.bl_probe(action[1])
        elif kind == 'adxl':
            self._bg('Sensor ' + ('on' if action[1] else 'off'), lambda: self.adxl_switch(action[1]))
        elif kind == 'power':
            self.power_request(action[1])
        elif kind == 'revert_go':                      # second YES: marker, then reboot
            try:
                with open(REVERT_MARK, 'w') as f:
                    f.write('screen app %s\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                self.flash('Back to stock failed: %s' % e)
                return
            self.power_request('reboot')
        elif kind == 'revert_no':
            self.stk['asked'] |= self.stk['sindoh']
        elif kind == 'screen_off':
            self.last_touch = 0.0              # black now (only while idle, see dimmed())
            self.screen = 'home'

    def power_request(self, what):
        """Ask dp200-powerkey.sh (stock side) to reboot or power off. It stops
        this app first, so the progress frames are written before asking."""
        self.screen = 'powering_' + what
        self.power_at = time.time()

        def work():
            try:
                write_shutdown_frames(what)
            except Exception as e:             # no progress frames: still go ahead
                print('shutdown frames: %s' % e, flush=True)
            try:
                os.makedirs(os.path.dirname(POWER_REQ), exist_ok=True)
                with open(POWER_REQ, 'w') as f:
                    f.write(what)
            except OSError as e:
                self.screen = 'home'
                self.flash('%s failed: %s' % (what, e))
        threading.Thread(target=work, daemon=True).start()

    def key_event(self, down, now):
        """Power button edges from the main loop."""
        if down:
            self.key_down = now
            self.last_touch = now              # wakes the screen
        elif self.key_down is not None:
            held, self.key_down = now - self.key_down, None
            if held < LONG_POWER and not self.screen.startswith('powering'):
                self.confirm = None
                self.screen = 'power'

    def cal_accept(self):
        """ACCEPT the paper test. PROBE OFFSET then needs the accepted
        height for LV_PROBE_CALIBRATE_SAVE: Klipper clears it after ACCEPT,
        so it is read fresh first and sent in the same script."""
        mp = get('/printer/objects/query?manual_probe')['status'].get('manual_probe') or {}
        z = mp.get('z_position')
        if self.cal.get('mode') == 'probe':
            if z is None:
                raise RuntimeError('no paper-test height')
            script = 'ACCEPT\nLV_PROBE_CALIBRATE_SAVE Z=%.3f' % z
        else:
            script = 'ACCEPT'
        post('/printer/gcode/script', {'script': script})
        self.cal.update(done=True, z=z)

    def upd_status(self):
        """Versions from Moonraker's updater (no network: its last check)."""
        try:
            vi = get('/machine/update/status')['version_info']
        except Exception as e:
            self.upd = {'error': 'Moonraker: %s' % fail_text(e)}
            return
        m = vi.get('mainsail', {})
        self.upd = {'mainsail': m.get('version', '-'), 'mainsail_new': m.get('remote_version', '?'),
                    'klipper': (vi.get('klipper') or {}).get('version', '-'),
                    'moonraker': (vi.get('moonraker') or {}).get('version', '-')}

    def _bg(self, label, fn, req=None):
        """Run fn in a worker thread while the footer says "Running: label";
        other commands are refused meanwhile. The busy state always ends
        with the job, or earlier for a G-code request `req` once Klipper is
        idle again (busy_tick). STOP never waits for it."""
        if self.busy:
            self.flash('Busy: ' + self.busy)
            return
        tok = object()
        self.busy, self.busy_tok, self.req = label, tok, req

        def work():
            try:
                fn()
            except Exception as e:
                self.flash('%s failed: %s' % (label, fail_text(e)))
            finally:
                if self.busy_tok is tok:               # not released and reused meanwhile
                    self.busy, self.busy_tok, self.req = None, None, None
        threading.Thread(target=work, daemon=True).start()

    def gcode_then(self, req):
        """Run a G-code script (in the _bg thread), then what req['after'] says:
        'fil'      LOAD/UNLOAD: say it finished, or show why it stopped
                   (page fil_error: UNLOAD / TRY AGAIN) instead of a short flash
        'bin'      EMPTY_BIN: the bin is reachable -> the empty-the-bin page
        'bin_done' BIN_EMPTIED: confirm the reset, back to MOVE
        If busy_tick has already settled the request, a late reply is ignored."""
        try:
            post('/printer/gcode/script', {'script': req['script']})
        except Exception as e:
            msg = fail_text(e, 400)                    # reads the reply body: once
            log('request %r: %s after %.0f s%s' % (req['label'], msg, time.time() - req['t0'],
                                                  ' (already ended)' if req['done'] else ''))
            if req['done']:
                return
            req['done'] = True
            if not isinstance(e, urllib.error.HTTPError):
                # timeout / lost connection: Klipper's own words, if it logged any
                msg = gcode_error_since(req['t0']) or msg
            self.gcode_failed(req, msg)
            return
        if req['done']:
            log('request %r: late reply after %.0f s (already ended)' % (req['label'], time.time() - req['t0']))
            return
        req['done'] = True
        self.gcode_ok(req)

    def gcode_failed(self, req, msg):
        if req['after'] != 'fil':
            self.flash('%s failed: %s' % (req['label'], msg), 10)
            return
        last = req['script'].splitlines()[-1]
        self.fil_fail = {'mode': 'unload' if last.startswith('UNLOAD') else 'load',
                         'msg': msg, 'script': last}
        self.confirm = None
        self.screen = 'fil_error'

    def busy_tick(self, now=None):
        """Main loop: end a G-code request whose reply did not come once
        Klipper has been idle for IDLE_RELEASE s (idle_timeout stays
        "Printing" while a script holds the G-code lock, heating waits
        included). Frees the screen at once, then reads the outcome from
        Moonraker's G-code log in a thread."""
        r = self.req
        if r is None or r['done'] or self.st is None:
            return
        now = time.time() if now is None else now
        state = (self.st.get('idle_timeout') or {}).get('state')
        if state == 'Printing' or now - r['t0'] < BUSY_MIN:
            r['idle_since'] = None
            return
        if r['idle_since'] is None:
            r['idle_since'] = now
            return
        if now - r['idle_since'] < IDLE_RELEASE:
            return
        r['done'] = True
        log('request %r: no reply, Klipper idle %.0f s after %.0f s: released'
            % (r['label'], now - r['idle_since'], now - r['t0']))
        self.busy, self.busy_tok, self.req = None, None, None
        threading.Thread(target=self.req_ended, args=(r,), daemon=True).start()

    def req_ended(self, r):
        """A request busy_tick ended: what did Klipper say meanwhile?"""
        try:
            lines = gcode_lines_since(r['t0'])
        except Exception:
            lines = None
        err = gcode_error_since(r['t0'], lines) if lines is not None else None
        if err:
            self.gcode_failed(r, err)
        elif r['after'] == 'fil' and not any('oad complete' in l for l in lines or ()):
            # neither an error nor LOAD/UNLOAD's "... complete": say so
            self.flash('%s ended (no reply): check it' % r['label'], 15)
        else:
            self.gcode_ok(r)

    def gcode_ok(self, req):
        label, after = req['label'], req['after']
        paused = job_state(self.st) == 'paused'
        if after == 'fil':
            if self.screen == 'fil_error':             # TRY AGAIN / UNLOAD worked
                self.screen = 'filament'
            self.flash('%s complete%s' % (label, ': RESUME when ready' if paused else ''), 10)
        elif after == 'bin':
            self.screen = 'bin'
        elif after == 'bin_done':
            self.screen = 'move'
            self.flash('Bin emptied: purge count 0 / %d' % BIN_THRESHOLD, 10)

    # ---- custom macro buttons (MOVE -> MACROS) ------------------------------
    def mac_load(self):
        """Read MACROS_FILE. A missing file is no buttons; a broken one is
        shown (and EDIT refuses, so the user's file is not overwritten)."""
        try:
            with open(MACROS_FILE) as f:
                self.mac['buttons'], self.mac['error'] = parse_macros(json.load(f)), None
        except FileNotFoundError:
            self.mac['buttons'], self.mac['error'] = [], None
        except (OSError, ValueError) as e:
            self.mac['buttons'], self.mac['error'] = [], str(e)

    def mac_list(self):
        """The printer's own G-code macros for EDIT (names with _ are internal)."""
        objs = get('/printer/objects/list')['objects']
        self.mac['all'] = sorted(o.split(None, 1)[1] for o in objs
                                 if o.startswith('gcode_macro ') and not o.split(None, 1)[1].startswith('_'))

    def mac_toggle(self, name):
        """EDIT: add a button for macro `name`, or remove the one there is."""
        self.mac_load()
        if self.mac['error']:
            self.flash('Macro file not valid: fix it in Mainsail', 10)
            return
        btns = [b for b in self.mac['buttons'] if b['gcode'] != name]
        if len(btns) == len(self.mac['buttons']):
            btns.append({'label': name, 'gcode': name})
        try:
            save_macros(btns)
        except OSError as e:
            self.flash('Not saved: %s' % e, 10)
            return
        self.mac['buttons'] = btns

    # ---- input shaping (USB accelerometer) --------------------------------
    def adxl_switch(self, on):
        """Enable/disable the sensor config by renaming it, then restart
        Klipper (it won't start with the sensor's MCU configured but absent)."""
        src, dst = (ADXL_OFF, ADXL_ON) if on else (ADXL_ON, ADXL_OFF)
        if not os.path.exists(src):
            self.flash('Sensor config missing (%s)' % os.path.basename(src))
            return
        os.rename(src, dst)
        self.shp['res'] = {}
        post('/printer/restart')

    def shaper_tick(self):
        """While the input shaping page is shown, pick the latest
        'Recommended shaper_type_x = ...' lines from the console (3 s)."""
        s = self.shp
        if self.screen != 'shaper' or s['busy'] or time.time() - s['checked'] < 3:
            return
        s['busy'], s['checked'] = True, time.time()

        def work():
            try:
                res = {}
                for m in get('/server/gcode_store?count=200')['gcode_store']:
                    for ax, typ, freq in SHAPER_RE.findall(m.get('message', '')):
                        res[ax] = '%s @ %.1f Hz' % (typ, float(freq))
                if res != s['res']:
                    s['res'] = res
                    s['rev'] += 1
            except Exception:
                pass
            finally:
                s['busy'] = False
        threading.Thread(target=work, daemon=True).start()

    # ---- bed level ---------------------------------------------------------
    def bl_probe(self, heat):
        """Probe a 4x4 mesh (profile 'level'); the page fills in point by point."""
        bl = self.bl
        if self.busy:
            self.flash('Busy: ' + self.busy)
            return
        bl.update(mode='probing', pts={}, mesh=None, t0=time.time(), checked=0.0)
        bl['rev'] += 1
        script = 'BED_CLEAR\n' + ('M190 S60\n' if heat else '') + \
            'BED_MESH_CALIBRATE PROBE_COUNT=4,4 PROFILE=level'

        def fn():
            try:
                if bl['xs'] is None:
                    cfg = get('/printer/objects/query?configfile=settings')
                    m = cfg['status']['configfile']['settings']['bed_mesh']
                    lo, hi = [[float(v) for v in (x.split(',') if isinstance(x, str) else x)]
                              for x in (m['mesh_min'], m['mesh_max'])]
                    bl['xs'] = [lo[0] + (hi[0] - lo[0]) * i / 3 for i in range(4)]
                    bl['ys'] = [lo[1] + (hi[1] - lo[1]) * i / 3 for i in range(4)]
                post('/printer/gcode/script', {'script': script})
                q = get('/printer/objects/query?bed_mesh')['status']['bed_mesh']
                if len(q['probed_matrix']) != 4 or len(q['probed_matrix'][0]) != 4:
                    raise ValueError('no 4x4 mesh came back')
                bl['mesh'] = q['probed_matrix']
                bl['mode'] = 'result'
            except Exception:
                bl['mode'] = 'start'
                raise
            finally:
                bl['rev'] += 1
        self._bg('Bed level probe', fn)

    # ---- console page (kernel log) -------------------------------------
    def console_tick(self):
        """While the console page is shown, read the kernel log (1 s).
        dmesg -S uses syslog(2): stock 3.2 has no readable /dev/kmsg."""
        c = self.con
        if self.screen != 'console' or c['busy'] or time.time() - c['checked'] < 1:
            return
        c['busy'], c['checked'] = True, time.time()

        def work():
            import subprocess
            try:
                out = ''
                for cmd in (['dmesg', '-S'], ['dmesg']):
                    try:
                        out = subprocess.run(cmd, capture_output=True, text=True, errors='replace',
                                             timeout=5).stdout
                    except (OSError, subprocess.SubprocessError):
                        continue
                    if out:
                        break
                lines = out.splitlines()[-200:] or ['(no kernel log: dmesg failed)']
                if lines != c['lines']:
                    c['lines'] = lines
                    c['rev'] += 1
            finally:
                c['busy'] = False
        threading.Thread(target=work, daemon=True).start()

    def bl_tick(self):
        """While probing, pick up each finished point from the console (1 s)."""
        bl = self.bl
        if bl['mode'] != 'probing' or bl['busy'] or bl['xs'] is None \
                or time.time() - bl['checked'] < 1:
            return
        bl['busy'], bl['checked'] = True, time.time()

        def work():
            try:
                pts = {}
                for m in get('/server/gcode_store?count=100')['gcode_store']:
                    if m.get('time', 0) < bl['t0'] - 1:
                        continue
                    for x, y, z in PROBE_RE.findall(m.get('message', '')):
                        c = min(range(4), key=lambda i: abs(bl['xs'][i] - float(x)))
                        r = min(range(4), key=lambda i: abs(bl['ys'][i] - float(y)))
                        if abs(bl['xs'][c] - float(x)) < 1 and abs(bl['ys'][r] - float(y)) < 1:
                            pts[(c, r)] = float(z)   # reference point (not on the grid) skipped
                if pts != bl['pts'] and bl['mode'] == 'probing':
                    bl['pts'] = pts
                    bl['rev'] += 1
            except Exception:
                pass
            finally:
                bl['busy'] = False
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
            self.load_saved_list()
            self.ip = my_ip()
        self.wf['checked'] = time.time()
        self.wifi_bg(None, fn)

    def load_saved_list(self):
        """Saved networks, first choice first (names and priorities only)."""
        nets = sorted(wifi.load_saved(), key=lambda n: -n['priority'])
        self.wf['saved_list'] = [(n['ssid'], n['priority']) for n in nets]
        self.wf['saved'] = len(nets)

    def stick_tick(self):
        """Every 3 s: a newly plugged-in USB stick with a Sindoh update asks
        (once per plug-in, not while printing) whether to go back to stock."""
        if not os.path.exists(OUR_KERNEL) or self.stk['busy'] or time.time() - self.stk['checked'] < 3:
            return
        self.stk['checked'] = time.time()
        now = set(usb_disks())
        new, self.stk['seen'] = now - self.stk['seen'], now
        self.stk['sindoh'] &= now
        self.stk['asked'] &= now                       # unplugged: ask again next time
        if new:
            self.stk['busy'] = True

            def work():
                try:
                    self.stk['sindoh'] |= {d for d in new if sindoh_stick(d)}
                finally:
                    self.stk['busy'] = False
            threading.Thread(target=work, daemon=True).start()
        state = ((self.st or {}).get('print_stats') or {}).get('state')
        if (self.stk['sindoh'] - self.stk['asked'] and not self.confirm
                and state not in ('printing', 'paused') and not self.screen.startswith('powering')):
            self.stk['asked'] |= self.stk['sindoh']
            self.screen = 'home'
            self.last_touch = time.time()              # wake the screen for it
            self.confirm = revert_confirm()

    def wifi_tick(self):
        """Keep the WiFi page's status current while it is shown, and run the
        no-IP watchdog every 10 s on any page."""
        if self.screen in ('wifi', 'wifi_saved') and not self.wf['busy'] and time.time() - self.wf['checked'] > 4:
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
                self.load_saved_list()
                self.flash(('%s: %s' % (name, msg))[:40], 10)
            self.wifi_bg('Connecting to %s...' % name, fn)
        elif kind == 'wifi_forget':
            ssid = action[1]

            def fn(w):
                wifi.forget(w, ssid)
                wf['status'] = wifi.status(w)
                self.load_saved_list()
            self.wifi_bg('Forgetting...', fn)
        elif kind == 'wifi_prefer':
            ssid = action[1]

            def fn(w):
                wifi.prefer(w, ssid)
                self.load_saved_list()
                self.flash('%s is now the first choice' % ssid.decode('utf-8', 'replace')[:20])
            self.wifi_bg('Saving...', fn)
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

    # ---- network (both ports) ---------------------------------------------
    FIELDS = (('ip', 'IP address'), ('mask', 'Netmask'), ('gw', 'Gateway'), ('dns', 'DNS server'))
    PORT_NAME = {'mlan0': 'WiFi', 'eth0': 'Ethernet'}

    def net_tick(self):
        """Refresh the port info every 3 s while a network page is shown."""
        n = self.net
        if net is None or self.screen not in ('network', 'ipcfg') or n['busy'] \
                or time.time() - n['checked'] < 3:
            return
        n['busy'], n['checked'] = True, time.time()

        def work():
            try:
                n['info'] = {i: net.info(i) for i, _ in net.PORTS}
                n['dns'] = net.dns()
                self.ip = my_ip()
            except Exception as e:
                self.flash('Network: %s' % e)
            finally:
                n['busy'] = False
                n['rev'] += 1
        threading.Thread(target=work, daemon=True).start()

    def net_action(self, action):
        n, kind = self.net, action[0]
        if kind == 'net_cfg':                          # open the IP settings of a port
            iface = action[1]
            saved = net.load().get(iface, {}) if net else {}
            cur = n['info'].get(iface, {})
            n['iface'] = iface
            # draft: saved static values, else the current (DHCP) ones as a starting point
            n['draft'] = {'mode': saved.get('mode', 'dhcp'),
                          'ip': saved.get('ip', cur.get('ip', '')),
                          'mask': saved.get('mask', cur.get('mask', '') or '255.255.255.0'),
                          'gw': saved.get('gw', cur.get('gw', '')),
                          'dns': saved.get('dns', (n['dns'] or [''])[0])}
            self.screen = 'ipcfg'
        elif kind == 'net_mode':
            n['draft']['mode'] = action[1]
        elif kind == 'net_edit':
            n['field'] = action[1]
            n['text'] = n['draft'].get(action[1], '')
            self.screen = 'numpad'
        elif kind == 'np':
            if len(n['text']) < 15:
                n['text'] += action[1]
        elif kind == 'np_bs':
            n['text'] = n['text'][:-1]
        elif kind == 'np_clear':
            n['text'] = ''
        elif kind == 'np_ok':
            t = n['text']
            ok = net.valid_mask(t) if n['field'] == 'mask' else net.valid_ip(t)
            if t and not ok:
                self.flash('Not a valid %s' % dict(self.FIELDS)[n['field']].lower())
                return
            n['draft'][n['field']] = t
            self.screen = 'ipcfg'
        elif kind == 'np_cancel':
            self.screen = 'ipcfg'
        elif kind == 'net_save':
            d = n['draft']
            if d['mode'] == 'static':
                err = net.check_static(d)
                if err:
                    self.flash(err)
                    return
            name = self.PORT_NAME[n['iface']]
            what = 'DHCP' if d['mode'] == 'dhcp' else 'static %s' % d['ip']
            self.confirm = ('Apply %s for %s? The connection can drop for a moment.' % (what, name),
                            ('net_apply',))
        elif kind == 'net_apply':
            d = dict(n['draft'])
            conf = net.load()
            conf[n['iface']] = d if d['mode'] == 'static' else {'mode': 'dhcp'}
            try:
                net.save(conf)
                self.flash('%s: settings applied' % self.PORT_NAME[n['iface']])
            except OSError as e:
                self.flash('Not saved: %s' % e)
            n['checked'] = 0                           # refresh soon
            self.screen = 'network'
        n['rev'] += 1

    def page_network(self, d, st):
        n = self.net
        d.text((20, 160), 'Network', font=font(28), fill=C_TXT)
        if not n['info']:
            self.net_tick()
            d.text((20, 204), 'Reading...', font=font(20), fill=C_DIM)
        y = 200
        for iface, name in (net.PORTS if net else ()):
            i = n['info'].get(iface)
            if not i:
                continue
            if iface == 'mlan0':
                ssid = self.wf['status'].get('ssid', b'').decode('utf-8', 'replace') \
                    if self.wf['status'].get('wpa_state') == 'COMPLETED' else ''
                state = ('on %s' % ssid) if ssid else 'not connected'
            else:
                state = 'cable connected' if i['link'] else 'no cable'
            d.text((20, y), '%s: %s' % (name, state), font=font(22), fill=C_TXT)
            rows = [('IP', ('%s / %s' % (i['ip'], i['mask'])) if i['ip'] else '-'),
                    ('Gateway', i['gw'] or '-'),
                    ('MAC', i['mac'].upper() or '-'),
                    ('Mode', 'static' if i['mode'] == 'static' else 'DHCP (automatic)')]
            for k, (lbl, val) in enumerate(rows):
                d.text((36, y + 30 + k * 24), lbl, font=font(17), fill=C_DIM)
                d.text((140, y + 30 + k * 24), val, font=font(17), fill=C_TXT)
            y += 30 + len(rows) * 24 + 14
        if n['dns']:
            d.text((20, y), 'DNS: %s' % ', '.join(n['dns'][:2]), font=font(17), fill=C_DIM)
        self.grid(d, [('WIFI', ('screen', 'wifi'), C_BTN, 28, 'networks'),
                      ('WIFI IP', ('net_cfg', 'mlan0'), C_BTN, 24, 'DHCP / static'),
                      ('ETHERNET IP', ('net_cfg', 'eth0'), C_BTN, 22, 'DHCP / static')],
                  top=508, rows_h=80)

    def page_ipcfg(self, d, st):
        n = self.net
        dr = n['draft']
        d.text((20, 160), '%s IP settings' % self.PORT_NAME[n['iface']], font=font(26), fill=C_TXT)
        static = dr.get('mode') == 'static'
        self.grid(d, [('DHCP', ('net_mode', 'dhcp'), C_ON if not static else C_BTN, 26, 'automatic'),
                      ('STATIC', ('net_mode', 'static'), C_ON if static else C_BTN, 26, 'fixed address')],
                  top=200, rows_h=80)
        y = 300
        if static:
            for key, label in self.FIELDS:
                box = (20, y, PW - 20, y + 54)
                d.rounded_rectangle(box, radius=10,
                                    fill=tuple(c + 45 for c in C_BTN) if self.pressed(box) else C_BTN)
                d.text((34, y + 6), label, font=font(15), fill=C_DIM)
                d.text((34, y + 24), dr.get(key) or ('(optional)' if key in ('gw', 'dns') else '(tap to set)'),
                       font=font(22), fill=C_TXT if dr.get(key) else C_DIM)
                self.buttons.append((box, ('net_edit', key)))
                y += 62
        else:
            d.text((20, y), 'The router assigns the address.', font=font(20), fill=C_DIM)
            y += 40
        self.button(d, (20, 552, PW - 20, 620), 'SAVE & APPLY', ('net_save',), C_ON, 26)

    def page_numpad(self, d, st):
        n = self.net
        d.text((20, 158), '%s - %s' % (self.PORT_NAME[n['iface']], dict(self.FIELDS)[n['field']]),
               font=font(22), fill=C_TXT)
        d.rounded_rectangle((20, 192, PW - 20, 248), radius=10, fill=(12, 12, 16), outline=(90, 90, 100), width=2)
        d.text((34, 202), n['text'] + '|', font=font(30), fill=C_TXT)
        keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '.', '0', 'DEL']
        w, h, gap = (PW - 40 - 2 * 10) // 3, 66, 8
        for i, k in enumerate(keys):
            x = 20 + (i % 3) * (w + 10)
            y = 258 + (i // 3) * (h + gap)
            act = ('np_bs',) if k == 'DEL' else ('np', k)
            self.button(d, (x, y, x + w, y + h), k, act, C_BAR if k == 'DEL' else C_BTN, 30)
        y = 258 + 4 * (h + gap)
        self.button(d, (20, y, 170, y + 60), 'CLEAR', ('np_clear',), C_BAR, 22)
        self.button(d, (180, y, PW - 20, y + 60), 'OK', ('np_ok',), C_ON, 28)

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
        # Wi-Fi's own address (wpa_supplicant STATUS), not self.ip: that is
        # the main address and was Ethernet's with a cable in (2026-11-06)
        wip = s.get('ip_address', '') if name else ''
        lines = [('Network', name or 'not connected'),
                 ('Address', 'http://%s/' % wip if wip else '-'),
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
        if wf['saved']:
            items.append(('SAVED', ('screen', 'wifi_saved'), C_BTN, 28, 'order, forget'))
        self.grid(d, items, top=380, rows_h=100)

    def page_wifi_saved(self, d, st):
        """The saved networks, first choice first. After a drop the printer may
        join a back-up network; it returns to the first choice when that is in
        range again (dp200_wifi.watchdog, every 10 min)."""
        wf = self.wf
        s = wf['status']
        cur = s.get('ssid') if s.get('wpa_state') == 'COMPLETED' else None
        d.text((20, 160), 'Saved networks', font=font(28), fill=C_TXT)
        d.text((20, 198), 'First choice on top. The printer goes back', font=font(18), fill=C_DIM)
        d.text((20, 222), 'to it when it is in range.', font=font(18), fill=C_DIM)
        if wf['busy']:
            d.text((20, 250), wf['busy'], font=font(20), fill=C_WARN)
        nets = wf['saved_list'][:5]
        if not nets:
            d.text((20, 290), 'No saved networks', font=font(22), fill=C_DIM)
        for i, (ssid, prio) in enumerate(nets):
            y = 284 + i * 84
            d.rounded_rectangle((20, y, PW - 20, y + 76), radius=12, fill=C_BAR)
            label = ssid.decode('utf-8', 'replace')
            f = font(22)
            while d.textlength(label, font=f) > PW - 290 and len(label) > 4:
                label = label[:-2] + '…'
            d.text((34, y + 12), label, font=f, fill=C_TXT)
            sub = ('1st choice', '2nd', '3rd')[i] if i < 3 else '%dth' % (i + 1)
            if ssid == cur:
                sub += ' - connected'
            d.text((34, y + 44), sub, font=font(18), fill=C_ON if ssid == cur else C_DIM)
            if i:
                self.button(d, (PW - 254, y + 8, PW - 144, y + 68), 'PREFER',
                            ('wifi_prefer', ssid), C_BTN, 22)
            name = ssid.decode('utf-8', 'replace')
            q = ('Forget %s? The printer will leave this network.' % name if ssid == cur
                 else 'Forget %s?' % name)
            self.button(d, (PW - 134, y + 8, PW - 30, y + 68), 'FORGET',
                        ('confirm', q, ('wifi_forget', ssid)), C_RED, 22)

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
        if self.screen.startswith('powering'):
            self.page_powering(d)
            return im
        if self.key_down is not None and time.time() - self.key_down >= HOLD_WARN:
            self.page_key_held(d)
            return im
        if self.screen == 'console':
            self.page_console(d)
            return im
        if self.dimmed():
            return Image.new('RGB', (PW, PH), (0, 0, 0))
        if self.screen in self.NO_KLIPPER:
            # network/WiFi setup works with or without Klipper/Moonraker
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
            self.button(d, (30, 520, 250, 610), 'NETWORK', ('screen', 'network'), C_BTN, 28, 'WiFi / IP')
            self.footer(d)
            return im
        self.header(d, st)
        state = st['webhooks']['state']
        if state != 'ready':
            self.page_error(d, st)
        else:
            js = job_state(st)
            pstate = 'printing' if js == 'starting' else js
            # Printing (and starting: the bed question or PRINT_START): the print page (home shows it). A print that starts or
            # resumes also leaves any page that could move or heat. Paused:
            # free to go (load filament, empty the bin), with the job on the
            # home page and nothing that homes (paused_refusal, page_move).
            started = pstate == 'printing' and self.last_pstate != 'printing'
            if pstate == 'printing' and (self.screen == 'home' or (
                    (started or js == 'starting') and self.screen not in self.IN_PRINT_OK)):
                if self.screen != 'home':
                    self.confirm = None                # e.g. a LOAD question from the pause
                self.screen = 'print'
            if pstate == 'paused' and self.screen in self.PAUSE_BLOCKED:
                self.screen = 'move'
            if pstate not in ('printing', 'paused') and self.screen in ('print', 'objects'):
                self.screen = 'home'
            self.last_pstate = pstate
            getattr(self, 'page_' + self.screen)(d, st)
            # Z homing was refused until the bed is confirmed empty (BED_CLEAR);
            # a print waits in PRINT_START for the same answer
            asking = (st.get('gcode_macro BED_CLEAR') or {}).get('asking')
            settled = time.time() - self.bed_answered > 5
            if asking and not self.confirm and settled:
                self.confirm = ('Is the bed EMPTY? Homing raises it to the top and crushes '
                                'anything on it.',
                                ('gcode', 'BED_CLEAR', 'Bed empty', 'detach'),
                                ('gcode', 'BED_CLEAR CANCEL=1', 'Homing cancelled'))
            elif (not asking and settled and self.confirm
                    and self.confirm[1][:2] == ('gcode', 'BED_CLEAR')):
                self.confirm = None                    # answered in Mainsail meanwhile
        if self.confirm:
            self.overlay_confirm(d)
        self.footer(d)
        return im

    def dimmed(self):
        idle = self.st and self.st['print_stats']['state'] not in ('printing', 'paused') \
            and not self.busy and self.st['extruder']['target'] == 0 \
            and self.st['heater_bed']['target'] == 0
        t = self.settings.get('timeout', DIM_AFTER)
        # the console page stays up until it is tapped
        return idle and t and time.time() - self.last_touch > t and self.screen != 'console'

    def header(self, d, st):
        d.rectangle((0, 0, PW, 64), fill=C_BAR)
        d.text((20, 14), 'Sindoh DP200', font=font(30), fill=C_TXT)
        state = st['webhooks']['state']
        col = (80, 200, 120) if state == 'ready' else (230, 80, 70)
        txt = state.upper()
        d.text((PW - 20 - d.textlength(txt, font=font(20)), 22), txt, font=font(20), fill=col)
        e, b = st['extruder'], st['heater_bed']
        d.text((20, 78), 'Nozzle', font=font(18), fill=C_DIM)
        d.text((20, 102), '%.0f/%.0f°' % (e['temperature'], e['target']), font=font(32), fill=C_NOZ)
        d.text((200, 78), 'Bed', font=font(18), fill=C_DIM)
        d.text((200, 102), '%.0f/%.0f°' % (b['temperature'], b['target']), font=font(32), fill=C_BED)
        # HOME: straight back to the home page from anywhere in the menus
        # (from the print page only while paused: a print shows that page)
        if self.screen != 'home' and (self.screen != 'print' or job_state(st) == 'paused'):
            box = (394, 72, PW - 12, 146)
            self.button(d, box, '', ('go_home',), C_BTN, 20)
            dy = 2 if self.pressed(box) else 0
            cx, top = (box[0] + box[2]) // 2, 84 + dy
            d.polygon([(cx - 16, top + 14), (cx, top), (cx + 16, top + 14)], fill=C_TXT)   # roof
            d.rectangle((cx - 11, top + 14, cx + 11, top + 30), fill=C_TXT)               # walls
            d.rectangle((cx - 4, top + 20, cx + 4, top + 30), fill=C_BTN)                 # door
            f = font(15)
            d.text((cx - d.textlength('HOME', font=f) // 2, top + 36), 'HOME', font=f, fill=C_DIM)

    # page -> page that BACK returns to (None: top level, no BACK)
    PARENT = {'filament': 'home', 'preheat': 'home', 'move': 'home', 'homing': 'move', 'system': 'home',
              'calibrate': 'move', 'shaper': 'calibrate', 'bedlevel': 'move', 'dryer': 'filament',
              'fil_mat': 'filament', 'fil_custom': 'fil_mat', 'info': 'system', 'update': 'system',
              'pid': 'calibrate', 'objects': 'print',
              'network': 'system', 'ipcfg': 'network', 'wifi': 'network', 'wifi_list': 'wifi',
              'wifi_saved': 'wifi',
              'display': 'system', 'timeout': 'display', 'power': 'home',
              'fil_error': 'filament', 'bin': 'move', 'macros': 'home', 'macros_edit': 'macros'}
    # pages that also work without Klipper (to fix the network from the waiting/error page)
    NO_KLIPPER = ('network', 'ipcfg', 'numpad', 'wifi', 'wifi_list', 'wifi_saved', 'wifi_kb', 'power')
    # pages a print that starts or resumes leaves alone (no motion or heat on them)
    IN_PRINT_OK = ('print', 'objects', 'console', 'info', 'display', 'timeout') + NO_KLIPPER
    # pages that home or probe: not while a print is paused (the part is on the bed)
    PAUSE_BLOCKED = ('homing', 'calibrate', 'papertest', 'pid', 'shaper', 'bedlevel')

    def back_action(self):
        if self.confirm:
            return ('cancel',)                         # BACK = NO in a dialog
        if self.screen == 'wifi_kb':
            return ('kb_cancel',)
        if self.screen == 'numpad':
            return ('np_cancel',)
        if self.screen == 'papertest':
            return ('cal_abort',)                      # leaving ends the paper test
        ready = self.st is not None and self.st['webhooks']['state'] == 'ready'
        if not ready:
            # only the network pages work without Klipper; their top goes back
            # to the waiting/error page (screen "home")
            if self.screen in ('network', 'power'):
                return ('screen', 'home')
            if self.screen not in self.NO_KLIPPER:
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
        paused = job_state(st) == 'paused'
        top = 236
        if paused:
            # a paused print (runout, PAUSE): the job stays one tap away
            top = 316
            d.rounded_rectangle((12, 154, PW - 12, 304), radius=14, fill=(70, 52, 20))
            d.text((26, 162), 'PRINT PAUSED', font=font(24), fill=C_WARN)
            d.text((26, 194), (ps.get('filename') or '?')[:38], font=font(18), fill=C_TXT)
            w = (PW - 24 - 28 - 2 * 10) // 3
            for i, it in enumerate((
                    ('RESUME', ('confirm', RESUME_Q, ('gcode', 'RESUME', 'Resume')), C_ON, 26),
                    ('CANCEL', ('confirm', 'Cancel the print?', ('gcode', 'CANCEL_PRINT', 'Cancel')),
                     C_RED, 26),
                    ('JOB', ('screen', 'print'), C_BTN, 26, 'details'))):
                x = 26 + i * (w + 10)
                self.button(d, (x, 224, x + w, 294), *it)
        else:
            d.text((20, 160), 'Job: %s' % ps['state'], font=font(26), fill=C_TXT)
            if ps.get('filename'):
                d.text((20, 196), ps['filename'][:34], font=font(18), fill=C_DIM)
        lamp = self.lamp_on(st)
        self.grid(d, [
            ('LAMP', ('gcode', 'LAMP_TOGGLE', 'Lamp'), C_ON if lamp else C_BTN, 30, 'on' if lamp else 'off'),
            ('FILAMENT', ('screen', 'filament')),
            ('PREHEAT', ('screen', 'preheat')),
            ('MOVE', ('screen', 'move')),
            ('MACROS', ('screen', 'macros'), C_BTN, 30, 'your own'),
            ('SYSTEM', ('screen', 'system')),
            ('COOL DOWN', ('confirm', 'The print is paused: cool down anyway? It cannot resume '
                                      'until the nozzle is hot again.',
                           ('gcode', 'FILAMENT_DRY_STOP\nTURN_OFF_HEATERS', 'Cool down'))
             if paused else ('gcode', 'FILAMENT_DRY_STOP\nTURN_OFF_HEATERS', 'Cool down')),
        ], top=top, rows_h=74 if paused else 90)
        if paused:
            return
        dry = st.get('gcode_macro _DRY') or {}
        n = bin_count(st)
        if dry.get('active'):
            d.rectangle((0, 190, PW, 228), fill=C_BG)
            d.text((20, 196), 'Drying: %s left, bed %d C' % (fmt_mins(dry['remaining']), dry['temp']),
                   font=font(20), fill=C_WARN)
        elif n >= BIN_THRESHOLD:
            d.rectangle((0, 190, PW, 228), fill=C_BG)
            d.text((20, 196), 'Purge bin full (%d): MOVE -> EMPTY BIN' % n, font=font(20), fill=C_WARN)

    def page_print(self, d, st):
        if job_state(st) == 'starting':
            return self.page_starting(d, st)
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
            ('RESUME', ('confirm', RESUME_Q, ('gcode', 'RESUME', 'Resume')), C_ON) if paused
            else ('PAUSE', ('gcode', 'PAUSE')),
            ('CANCEL', ('confirm', 'Cancel the print?', ('gcode', 'CANCEL_PRINT', 'Cancel')), C_RED),
            ('Z -0.025', ('gcode', 'SET_GCODE_OFFSET Z_ADJUST=-0.025 MOVE=1', 'Z -0.025'), C_BTN, 26, 'closer'),
            ('Z +0.025', ('gcode', 'SET_GCODE_OFFSET Z_ADJUST=0.025 MOVE=1', 'Z +0.025'), C_BTN, 26, 'further'),
            ('LAMP', ('gcode', 'LAMP_TOGGLE', 'Lamp'), C_ON if lamp else C_BTN, 30, 'on' if lamp else 'off'),
            # cancel one object (Klipper's exclude_object; the slicer must
            # label the objects): only with more than one object
            ('OBJECTS', ('screen', 'objects'), C_BTN, 30, 'skip one')
            if len(print_objects(st)) > 1 else None,
        ], top=320, rows_h=96)

    def page_starting(self, d, st):
        """The bed question and PRINT_START's start (heat, home, mesh, purge;
        ~7 min). Klipper calls the job paused meanwhile, but there is
        nothing to resume: only CANCEL (and LAMP). The temperatures are in
        the header."""
        ps = st['print_stats']
        d.text((20, 160), (ps.get('filename') or '?')[:34], font=font(20), fill=C_DIM)
        d.text((20, 188), 'Starting print', font=font(30), fill=C_TXT)
        cur = start_phase(st)
        for i, (key, text) in enumerate(START_STEPS):
            y = 234 + i * 32
            done = START_KEYS.index(cur) > i
            now = key == cur
            mark = 'OK' if done else '>' if now else ''
            d.text((24, y), mark, font=font(20), fill=C_ON if done else C_WARN)
            d.text((66, y), text, font=font(22 if now else 20),
                   fill=C_WARN if now else C_DIM if done else C_TXT)
        lamp = self.lamp_on(st)
        self.grid(d, [
            ('CANCEL', ('confirm', 'Cancel the print? Klipper finishes the current start first '
                                   '(hold STOP to stop at once).',
                        ('gcode', 'CANCEL_PRINT', 'Cancel')), C_RED),
            ('LAMP', ('gcode', 'LAMP_TOGGLE', 'Lamp'), C_ON if lamp else C_BTN, 30, 'on' if lamp else 'off'),
        ], top=490, rows_h=96)

    OBJ_PER_PAGE = 8

    def page_objects(self, d, st):
        objs = print_objects(st)
        ex = set((st.get('exclude_object') or {}).get('excluded_objects') or [])
        cur = (st.get('exclude_object') or {}).get('current_object')
        left = [o for o in objs if o not in ex]
        d.text((20, 160), 'Objects (%d, %d skipped)' % (len(objs), len(ex)), font=font(26), fill=C_TXT)
        d.text((20, 196), 'Tap one to stop printing it.', font=font(20), fill=C_DIM)
        n = self.OBJ_PER_PAGE
        pages = max(1, (len(objs) + n - 1) // n)
        self.obj_page = getattr(self, 'obj_page', 0) % pages
        items = []
        for o in objs[self.obj_page * n:(self.obj_page + 1) * n]:
            label = o if len(o) <= 14 else o[:13] + '~'
            if o in ex:
                items.append((label, None, C_BAR, 22, 'skipped', C_DIM))
            elif len(left) == 1:
                # the last one: that is CANCEL on the print page
                items.append((label, None, C_BTN, 22, 'last one'))
            else:
                items.append((label, ('confirm', 'Stop printing %s? The others continue.' % o,
                                      ('gcode', 'EXCLUDE_OBJECT NAME=%s' % o, 'Skip ' + label)),
                               C_ON if o == cur else C_BTN, 22, 'printing now' if o == cur else None))
        if pages > 1:
            items += [None] * (n - len(items))
            items.append(('MORE', ('obj_more',), C_BTN, 24, '%d / %d' % (self.obj_page + 1, pages)))
        self.grid(d, items, top=232, rows_h=64)

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
        items = [('LOAD', ('fil_mode', 'load'), C_BTN, 32, 'choose filament'),
                 ('UNLOAD', ('fil_mode', 'unload'), C_BTN, 32, 'choose filament')]
        items.append(('UNLOCK', ('confirm', 'Release the cartridge latch for 4 s? Unload the filament first.',
                                 ('gcode', 'CARTRIDGE_RELEASE', 'Cartridge release')), C_BTN, 28, 'cartridge'))
        items.append(('DRYER', ('screen', 'dryer'), C_BTN, 28, 'spool on bed'))
        self.grid(d, items, top=270, rows_h=96)

    def page_fil_mat(self, d, st):
        """LOAD or UNLOAD: the filament (sets the nozzle temperature)."""
        mode = self.fil['mode']
        d.text((20, 160), '%s filament' % mode.capitalize(), font=font(28), fill=C_TXT)
        d.text((20, 200), 'Pick the filament (sets the nozzle):', font=font(20), fill=C_DIM)
        items = [(name, fil_confirm(mode, name, t), C_BTN, 30, '%d °C' % t)
                 for name, t in FIL_PRESETS]
        items.append(('CUSTOM', ('screen', 'fil_custom'), C_BTN, 30, 'other filament'))
        self.grid(d, items, top=240, rows_h=96)

    def page_fil_custom(self, d, st):
        """CUSTOM temperature for LOAD/UNLOAD (other filaments)."""
        mode = self.fil['mode']
        t = self.fil['temp']
        d.text((20, 160), '%s: custom temperature' % mode.capitalize(), font=font(26), fill=C_TXT)
        d.text((20, 198), 'The filament maker\'s print temperature', font=font(18), fill=C_DIM)
        d.text((20, 222), '(%d-%d °C)' % (FIL_MIN, FIL_MAX), font=font(18), fill=C_DIM)
        s = '%d °C' % t
        f = font(64)
        d.text(((PW - d.textlength(s, font=f)) // 2, 262), s, font=f, fill=C_NOZ)
        w, gap = (PW - 40 - 3 * 10) // 4, 10
        for i, step in enumerate(FIL_STEPS):
            x = 20 + i * (w + gap)
            ok = t < FIL_MAX if step > 0 else t > FIL_MIN   # steps stop at the limits
            self.button(d, (x, 360, x + w, 440), '%+d' % step,
                        ('fil_step', step) if ok else None, C_BTN if ok else C_BAR, 30)
        self.button(d, (20, 470, PW - 20, 570), mode.upper(), ('fil_custom_go',), C_ON, 34,
                    'heat to %d °C' % t)

    def page_fil_error(self, d, st):
        """A LOAD/UNLOAD that stopped (jam, no grab, homing refused): why,
        and what next. Klipper's message is shown in full."""
        f = self.fil_fail or {'mode': 'load', 'msg': '?', 'script': 'LOAD_FILAMENT MATERIAL=PLA'}
        mode = f['mode']
        d.rounded_rectangle((12, 154, PW - 12, 470), radius=14, fill=(90, 24, 24))
        d.text((28, 166), '%s stopped' % mode.upper(), font=font(30), fill=C_TXT)
        for i, l in enumerate(wrap(d, f['msg'], font(20), PW - 60)[:9]):
            d.text((28, 212 + i * 28), l, font=font(20), fill=(240, 210, 210))
        arg = f['script'].split(None, 1)[1] if ' ' in f['script'] else ''
        unload = ('UNLOAD_FILAMENT ' + arg).strip()
        items = []
        if mode == 'load':
            d.text((20, 482), 'Check the inlet. UNLOAD pulls the filament back.', font=font(18), fill=C_DIM)
            items.append(('UNLOAD', ('confirm', 'Heat the nozzle and UNLOAD the filament?',
                                     ('gcode', unload, 'Unload', 'fil')), C_BTN, 30))
        else:
            d.text((20, 482), 'Check the inlet and the filament path.', font=font(18), fill=C_DIM)
        items.append(('TRY AGAIN', ('confirm', 'Heat the nozzle and %s again?' % mode.upper(),
                                    ('gcode', f['script'], mode.capitalize(), 'fil')), C_BTN, 28))
        items.append(('OK', ('screen', 'filament'), C_BTN, 30))
        self.grid(d, items, top=516, rows_h=80, cols=len(items))

    def page_bin(self, d, st):
        """After EMPTY_BIN: the bin can come out; DONE resets the count."""
        n = bin_count(st)
        d.text((20, 160), 'Empty the purge bin', font=font(28), fill=C_TXT)
        y = 210
        for l in ('1. Take out the purge bin.', '2. Empty it.', '3. Put it back.', '',
                  'Then tap DONE: the purge count', 'goes back to 0 (now %d / %d).' % (n, BIN_THRESHOLD)):
            step = l[:1].isdigit()
            d.text((20, y), l, font=font(24 if step else 20), fill=C_TXT if step else C_DIM)
            y += 36
        if job_state(st) == 'paused':
            d.text((20, y + 4), 'RESUME moves the head and bed back.', font=font(20), fill=C_WARN)
        self.button(d, (30, 480, PW - 30, 580), 'DONE', ('gcode', 'BIN_EMPTIED', 'Bin emptied', 'bin_done'),
                    C_ON, 34, 'bin is empty and back in')
        self.button(d, (30, 598, PW - 30, 668), 'NOT EMPTIED', ('screen', 'move'), C_BTN, 24)

    def page_macros(self, d, st):
        """Custom macro buttons from MACROS_FILE; each asks first."""
        m = self.mac
        name = os.path.basename(MACROS_FILE)
        d.text((20, 156), 'Macros', font=font(28), fill=C_TXT)
        if m['error']:
            d.text((20, 196), '%s is not valid:' % name, font=font(18), fill=C_WARN)
            for i, l in enumerate(wrap(d, m['error'], font(18), PW - 40)[:4]):
                d.text((20, 222 + i * 24), l, font=font(18), fill=C_DIM)
            d.text((20, 330), 'Fix it in Mainsail (Machine tab).', font=font(18), fill=C_DIM)
            return
        btns = m['buttons']
        paused = job_state(st) == 'paused'
        if btns:
            d.text((20, 196), 'Paused: the part is still on the bed!' if paused else
                   'Each one asks first.', font=font(18), fill=C_WARN if paused else C_DIM)
        else:
            for i, l in enumerate(('No buttons yet. EDIT picks from', "the printer's macros, or edit",
                                   name, 'in Mainsail (Machine tab).')):
                d.text((20, 200 + i * 28), l, font=font(20), fill=C_DIM)
        n = MAC_PER_PAGE
        pages = max(1, (len(btns) + n - 1) // n)
        m['page'] %= pages
        items = []
        for b in btns[m['page'] * n:(m['page'] + 1) * n]:
            q = b.get('confirm') or ('Run %s? The screen cannot tell whether it moves or heats.'
                                     % b['gcode'].split()[0])
            items.append((b['label'], ('confirm', q, ('gcode', b['gcode'], b['label'], 'macro')),
                          C_BTN, 24))
        if btns:
            items += [None] * (n - len(items))
        items.append(('EDIT', ('mac_edit',), C_BTN, 24, 'add / remove'))
        if pages > 1:
            items.append(('MORE', ('mac_more',), C_BTN, 24, '%d / %d' % (m['page'] + 1, pages)))
        self.grid(d, items, top=226 if btns else 340, rows_h=70)

    def page_macros_edit(self, d, st):
        """EDIT: the printer's macros; tap one to add or remove its button."""
        m = self.mac
        d.text((20, 156), 'Macro buttons', font=font(28), fill=C_TXT)
        d.text((20, 196), 'Tap to add (green) or remove.', font=font(18), fill=C_DIM)
        names = m['all']
        if names is None:
            d.text((20, 240), 'Reading the macros...' if self.busy else 'Could not read the macros.',
                   font=font(22), fill=C_DIM)
            return
        if not names:
            d.text((20, 240), 'The printer has no macros of its own.', font=font(22), fill=C_DIM)
            return
        on = set(b['gcode'] for b in m['buttons'])
        n = MAC_EDIT_PER_PAGE
        pages = max(1, (len(names) + n - 1) // n)
        m['edit_page'] %= pages
        items = [(nm, ('mac_toggle', nm), C_ON if nm in on else C_BTN, 20)
                 for nm in names[m['edit_page'] * n:(m['edit_page'] + 1) * n]]
        if pages > 1:
            items += [None] * (n - len(items))
            items.append(('MORE', ('mac_edit_more',), C_BTN, 22, '%d / %d' % (m['edit_page'] + 1, pages)))
        self.grid(d, items, top=226, rows_h=56)

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
        th = st['toolhead']
        homed = th.get('homed_axes', '')
        paused = job_state(st) == 'paused'
        d.text((20, 160), 'Move / maintenance', font=font(28), fill=C_TXT)
        if paused:
            # the part is still on the bed and RESUME needs the axes as they are
            d.text((20, 200), 'Print paused: no homing' if homed == 'xyz' else
                   'Paused but NOT homed: cancel the print', font=font(20), fill=C_WARN)
        else:
            d.text((20, 200), 'Homed: %s' % (homed.upper() or 'no'), font=font(20), fill=C_DIM)
        n = bin_count(st)
        z = (th.get('position') or [0, 0, 0])[2]
        if paused:
            # only lowering (Z grows downwards), and without the homing macro
            lower = (('confirm', 'Lower the bed to Z%d? It moves away from the nozzle.' % LOWER_BED_Z,
                      ('gcode', 'G90\nG1 Z%d F600' % LOWER_BED_Z, 'Lower bed'))
                     if homed == 'xyz' and z < LOWER_BED_Z else None)
        else:
            lower = ('confirm', 'Lower the bed to Z%d?' % LOWER_BED_Z,
                     ('gcode', '_SINDOH_ENSURE_HOMED\nG90\nG1 Z%d F600' % LOWER_BED_Z, 'Lower bed'))
        no = 'not while paused'
        items = [
            ('HOME', ('screen', 'homing'), C_BTN, 30, 'all / X / Y / Z'),
            ('LOWER BED', lower, C_BTN, 30, None if lower or not paused else
             ('already low' if homed == 'xyz' else no)),
            ('CLEAN', ('confirm', 'Heat, purge and wipe the nozzle?',
                       ('gcode', 'CLEAN_NOZZLE', 'Clean nozzle')), C_BTN, 30, 'nozzle'),
            ('MOTORS OFF', ('gcode', 'M84', 'Motors off')),
            ('EMPTY BIN', ('confirm', 'Lower the bed %d mm and move the head to the left, to take '
                                      'out the purge bin?' % BIN_DROP, ('gcode', 'EMPTY_BIN', 'Empty bin', 'bin')),
             C_FULL if n >= BIN_THRESHOLD else C_BTN, 28, '%d / %d purges' % (n, BIN_THRESHOLD)),
            ('CALIBRATE', ('screen', 'calibrate'), C_BTN, 28, 'input shaping'),
            ('BED LEVEL', ('screen', 'bedlevel'), C_BTN, 28, 'probe + screws'),
        ]
        if paused:
            for k in (0, 3, 5, 6):                     # HOME, MOTORS OFF, CALIBRATE, BED LEVEL
                items[k] = (items[k][0], None, C_BAR, 28, no, C_DIM)
            if not lower:
                items[1] = items[1][:1] + (None, C_BAR) + items[1][3:] + (C_DIM,)
            if homed != 'xyz':                          # anything else would home first
                items = [(it[0], None, C_BAR, 28, no, C_DIM) for it in items]
        self.grid(d, items, top=240, rows_h=90)

    def bl_view(self, d, top, w, live):
        """Top-down plate (back at the top, door at the bottom) with the 16
        probe points: an empty circle until probed, then the value."""
        bl = self.bl
        x0 = (PW - w) // 2
        sc = w / (BL_PLATE[2] - BL_PLATE[0])
        y1 = top + (BL_PLATE[3] - BL_PLATE[1]) * sc
        px = lambda x: x0 + (x - BL_PLATE[0]) * sc
        py = lambda y: y1 - (y - BL_PLATE[1]) * sc
        # drawn wider than the plate's true shape so the value boxes stay inside
        d.rounded_rectangle((x0 - 34, top, x0 + w + 34, y1), radius=8, fill=(44, 44, 54), outline=(90, 90, 100))
        xs = bl['xs'] or [18 + 62 * i for i in range(4)]
        ys = bl['ys'] or [30 + 140 * i / 3 for i in range(4)]
        small = w < 250
        for r in range(4):
            for c in range(4):
                cx, cy = px(xs[c]), py(ys[r])
                z = bl['mesh'][r][c] if bl['mesh'] and not live else bl['pts'].get((c, r))
                if z is None or small:
                    d.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), outline=C_DIM, width=2)
                    continue
                d.rounded_rectangle((cx - 31, cy - 15, cx + 31, cy + 15), radius=7, fill=bl_colour(z))
                t = '%+.2f' % z
                d.text((cx - d.textlength(t, font=font(16)) / 2, cy - 9), t, font=font(16), fill=(15, 15, 20))
        for _, sx, sy in BL_SCREWS:
            cx, cy = px(sx), py(sy)
            d.ellipse((cx - 11, cy - 11, cx + 11, cy + 11), fill=(200, 200, 210))
            d.line((cx - 7, cy, cx + 7, cy), fill=(40, 40, 40), width=3)
        cx, cy = px(BL_PIVOT[0]), py(BL_PIVOT[1])
        d.polygon(((cx, cy - 9), (cx - 10, cy + 8), (cx + 10, cy + 8)), fill=(200, 200, 210))
        d.text((x0 - 28, y1 + 6), 'FRONT (door)', font=font(16), fill=C_DIM)
        d.text((x0 + w + 28 - d.textlength('BACK', font=font(16)), top - 22), 'BACK', font=font(16), fill=C_DIM)
        return y1

    def page_bedlevel(self, d, st):
        bl = self.bl
        d.text((20, 156), 'Bed level', font=font(28), fill=C_TXT)
        q = 'Is the bed EMPTY? Homes if needed, then probes 16 points (~3 min).'
        if bl['mode'] == 'start':
            for i, l in enumerate(['Probes the bed (16 points), shows how',
                                   'far it is from level and which way to',
                                   'turn the two front screws.', '',
                                   'Bed 60 C first gives the truest result.']):
                d.text((20, 210 + i * 30), l, font=font(20), fill=C_DIM)
            self.bl_view(d, 400, 200, True)
            self.button(d, (30, 620, 230, 705), 'PROBE', ('confirm', q, ('bl_probe', False)),
                        C_ON, 30, 'bed cold')
            self.button(d, (250, 620, 450, 705), 'PROBE', ('confirm', q, ('bl_probe', True)),
                        C_BTN, 30, 'heat bed 60 C')
            return
        if bl['mode'] == 'probing':
            n = len(bl['pts'])
            d.text((20, 198), 'Probing point %d of 16...' % min(n + 1, 16) if n else 'Homing / starting...',
                   font=font(22), fill=C_WARN)
            self.bl_view(d, 262, 300, True)
            d.text((20, 600), 'Screen and STOP keep working.', font=font(20), fill=C_DIM)
            return
        mesh = bl['mesh']
        lo, hi = min(min(r) for r in mesh), max(max(r) for r in mesh)
        d.text((20, 196), 'Range %.2f mm' % (hi - lo), font=font(22), fill=C_TXT)
        a, b, c = plane_fit(bl['xs'], bl['ys'], mesh)
        z = lambda x, y: a + b * x + c * y
        ref = z(*BL_PIVOT)
        diffs = [(name, z(sx, sy) - ref) for name, sx, sy in BL_SCREWS]
        if all(abs(v) < BL_OK for _, v in diffs):
            d.text((250, 199), 'Level', font=font(20), fill=C_ON)
        else:
            d.text((230, 201), 'turns seen from above', font=font(18), fill=C_DIM)
        y = self.bl_view(d, 262, 250, False) + 26
        for name, v in diffs:
            if abs(v) < BL_OK:
                msg, col = '%s screw: OK (%+.2f)' % (name, v), C_ON
            else:
                # mesh z > 0 = bed higher than the reference: that corner comes down
                eighths = max(1, round(abs(v) / BL_MM_PER_TURN * 8))
                turn = {1: '1/8', 2: '1/4', 3: '3/8', 4: '1/2', 5: '5/8', 6: '3/4', 7: '7/8'}.get(
                    eighths, '%.1f' % (eighths / 8))
                msg, col = '%s: %s turn %s (%.2f)' % (name, turn, 'CCW' if v > 0 else 'CW', abs(v)), C_WARN
            d.rounded_rectangle((20, y, PW - 20, y + 38), radius=10, fill=C_BAR)
            d.ellipse((32, y + 9, 52, y + 29), fill=col)
            d.text((64, y + 7), msg, font=font(21), fill=C_TXT)
            y += 44
        self.button(d, (30, 632, 230, 708), 'PROBE', ('confirm', q, ('bl_probe', False)), C_BTN, 30, 'again')
        self.button(d, (250, 632, 450, 708), 'PROBE', ('confirm', q, ('bl_probe', True)), C_BTN, 30, 'bed 60 C')

    def page_dryer(self, d, st):
        dry = st.get('gcode_macro _DRY') or {}
        limit = dry.get('sheet_max', 70)
        bed = st['heater_bed']
        d.text((20, 156), 'Filament dryer', font=font(28), fill=C_TXT)
        if dry.get('active'):
            done = dry['total'] - dry['remaining']
            lines = [('Drying: bed %.0f / %.0f C' % (bed['temperature'], bed['target']), C_TXT),
                     ('%s left of %s' % (fmt_mins(dry['remaining']), fmt_mins(dry['total'])), C_TXT),
                     ('Flip the spool now (halfway)' if dry.get('flipped') else
                      'Flip the spool at halfway (%s)' % fmt_mins(dry['total'] // 2),
                      C_WARN if dry.get('flipped') and done < dry['total'] // 2 + 30 else C_DIM),
                     ('Keep the doors closed.', C_DIM)]
            for i, (l, c) in enumerate(lines):
                d.text((20, 210 + i * 36), l, font=font(24 if i < 2 else 20), fill=c)
            self.grid(d, [('STOP DRYING', ('confirm', 'Stop drying? The bed turns off.',
                                    ('gcode', 'FILAMENT_DRY_STOP', 'Stop drying')), C_RED, 30)],
                      top=560, cols=1, rows_h=90)
            return
        sel = self.dry
        hot = sel['temp'] > limit
        d.text((20, 196), 'Material (bed temperature):', font=font(20), fill=C_DIM)
        items = []
        for mat, temp, hours in DRY_PRESETS:
            col = C_ON if mat == sel['mat'] else (C_WARN if temp > limit else C_BTN)
            items.append((mat, ('dry_mat', mat, temp, hours), col, 24, '%d C' % temp))
        self.grid(d, items, top=226, rows_h=70, cols=3)
        d.text((20, 404), 'Time:', font=font(20), fill=C_DIM)
        self.grid(d, [('%dh' % h, ('dry_hours', h), C_ON if h == sel['hours'] else C_BTN, 24)
                      for h in DRY_HOURS], top=432, rows_h=60, cols=5)
        msg = '%s: bed %d C for %d h' % (sel['mat'], sel['temp'], sel['hours'])
        d.text((20, 506), msg, font=font(22), fill=C_TXT)
        if hot:
            d.text((20, 536), 'Above the build sheet limit (%d C)!' % limit, font=font(20), fill=C_WARN)
        q = ('Bed goes down and forward. Lay the spool flat on it, close the doors. %s at %d C for %d h?'
             % (sel['mat'], sel['temp'], sel['hours']))
        if hot:
            q = ('WARNING: %d C is above the %d C build sheet limit - only for sheets rated higher. '
                 % (sel['temp'], limit)) + q
        cmd = 'FILAMENT_DRY TEMP=%d HOURS=%d MATERIAL=%s%s' % (sel['temp'], sel['hours'], sel['mat'],
                                                            ' FORCE=1' if hot else '')
        self.grid(d, [('START', ('confirm', q, ('gcode', cmd, 'Dryer')), C_WARN if hot else C_ON, 30)],
                  top=574, cols=1, rows_h=80)

    def page_calibrate(self, d, st):
        d.text((20, 160), 'Calibrate', font=font(28), fill=C_TXT)
        printing = st['print_stats']['state'] in ('printing', 'paused')
        bed = 'Is the bed EMPTY? %s homes Z (the bed rises to the top), then a paper test.'
        items = [
            ('Z HEIGHT', ('confirm', bed % 'Z HEIGHT', ('cal_start', 'zend')), C_BTN, 26, 'paper test'),
            ('PROBE OFFSET', ('confirm', bed % 'PROBE OFFSET probes, then', ('cal_start', 'probe')),
             C_BTN, 24, 'paper test'),
            ('PID TUNE', ('screen', 'pid'), C_BTN, 26, 'nozzle / bed'),
            ('INPUT SHAPING', ('screen', 'shaper'), C_BTN, 24, 'USB accelerometer'),
        ]
        if printing:
            items = [it[:1] + (None,) + it[2:] for it in items]       # not during a print
        self.grid(d, items, top=210, rows_h=96)
        # a baby-step offset from the print page can be kept for good
        zoff = st['gcode_move']['homing_origin'][2]
        if abs(zoff) >= 0.001:
            d.text((20, 446), 'Baby-step Z offset now: %+.3f mm' % zoff, font=font(20), fill=C_TXT)
            if not printing:
                self.button(d, (30, 480, PW - 30, 570), 'SAVE Z OFFSET',
                            ('confirm', 'Keep the %+.3f mm baby-step offset as the new Z height? '
                                        'Klipper restarts.' % zoff,
                             ('cal_save', 'Z_OFFSET_APPLY_ENDSTOP')),
                            C_ON, 28, 'restarts Klipper')

    def page_papertest(self, d, st):
        """The paper test of Z HEIGHT (Z_ENDSTOP_CALIBRATE) and PROBE OFFSET
        (LV_PROBE_CALIBRATE), following Klipper's manual_probe status."""
        c = self.cal
        mp = st.get('manual_probe') or {}
        d.text((20, 156), 'Z height' if c.get('mode') == 'zend' else 'Probe offset',
               font=font(28), fill=C_TXT)
        if c.get('done'):
            z = c.get('z')
            d.text((20, 204), 'Accepted at Z %.3f' % z if z is not None else 'Accepted',
                   font=font(24), fill=C_ON)
            for i, l in enumerate(('SAVE writes it to printer.cfg and', 'restarts Klipper (about 30 s).')):
                d.text((20, 246 + i * 28), l, font=font(20), fill=C_DIM)
            self.grid(d, [
                ('SAVE', ('confirm', 'Save the new value? Klipper restarts.', ('cal_save',)), C_ON, 30,
                 'printer.cfg'),
                ('DISCARD', ('cal_abort',), C_BTN, 28, 'keep the old one'),
            ], top=330)
            return
        if not mp.get('is_active'):
            d.text((20, 204), 'Moving into position...' if not self.busy else self.busy + '...',
                   font=font(22), fill=C_WARN)
            d.text((20, 240), 'The paper test starts when it stops.', font=font(20), fill=C_DIM)
            self.button(d, (30, 470, PW - 30, 560), 'ABORT', ('cal_abort',), C_RED, 28)
            return
        for i, l in enumerate(('1. Slide a sheet of paper under the nozzle.',
                               '2. Move the bed up until the paper just', '    drags when you pull it.')):
            d.text((20, 196 + i * 26), l, font=font(19), fill=C_DIM)
        z = mp.get('z_position')
        s = 'Z %.3f' % z if z is not None else 'Z ?'
        f = font(46)
        d.text(((PW - d.textlength(s, font=f)) // 2, 278), s, font=f, fill=C_NOZ)
        steps = [('-0.5', 'closer'), ('-0.1', 'closer'), ('-0.025', 'closer'),
                 ('+0.025', 'further'), ('+0.1', 'further'), ('+0.5', 'further')]
        self.grid(d, [(v, ('gcode', 'TESTZ Z=%s' % v, 'Bed ' + v), C_BTN, 26, sub) for v, sub in steps],
                  top=346, rows_h=72, cols=3)
        self.button(d, (30, 530, 230, 610), 'ACCEPT', ('cal_accept',), C_ON, 28)
        self.button(d, (250, 530, PW - 30, 610), 'ABORT', ('cal_abort',), C_RED, 28)

    def page_pid(self, d, st):
        d.text((20, 160), 'PID tune', font=font(28), fill=C_TXT)
        for i, l in enumerate(('Measures how this printer\'s heaters',
                               'respond, for steady temperatures. Several',
                               'minutes each; it cycles around the target.')):
            d.text((20, 200 + i * 26), l, font=font(19), fill=C_DIM)
        printing = st['print_stats']['state'] in ('printing', 'paused')
        items = []
        for name, heater, t in (('NOZZLE', 'extruder', 210), ('BED', 'heater_bed', 60)):
            act = ('confirm', 'Heat the %s to %d°C and tune it? About 5-10 minutes; stay nearby.'
                   % (name.lower(), t), ('pid_run', heater, t))
            items.append((name, None if printing else act, C_BTN, 30, '%d°C' % t))
        self.grid(d, items, top=300)
        if self.cal.get('pid_done'):
            names = ['nozzle' if h == 'extruder' else 'bed' for h in self.cal['pid_done']]
            d.text((20, 430), 'Tuned: %s. SAVE to keep it.' % ', '.join(names),
                   font=font(20), fill=C_ON)
            self.button(d, (30, 470, PW - 30, 560), 'SAVE',
                        ('confirm', 'Save the new PID values? Klipper restarts.', ('cal_save',)),
                        C_ON, 30, 'restarts Klipper')

    def page_shaper(self, d, st):
        on = os.path.exists(ADXL_ON)
        d.text((20, 156), 'Input shaping', font=font(28), fill=C_TXT)
        if on:
            lines = ['1. Clip the sensor on the print head,', '    then TEST X (about 2 min).',
                     '2. Clip it on the bed, then TEST Y.',
                     '3. SAVE (restarts Klipper), then', '    SENSOR OFF and unplug it.']
        else:
            lines = ['Measures how the head and bed shake',
                     'and sets the input shaper to cancel it',
                     '(less ringing at speed).',
                     '1. Plug the sensor into the front USB.',
                     '2. SENSOR ON (restarts Klipper).']
        for i, l in enumerate(lines):
            d.text((20, 200 + i * 28), l, font=font(20), fill=C_DIM)
        y = 200 + len(lines) * 28 + 8
        if not os.path.exists(NUMPY_LINK):
            d.text((20, y), 'numpy missing: run setup_numpy.sh', font=font(20), fill=C_WARN)
            y += 30
        if on:
            res = self.shp['res']
            for ax in 'xy':
                d.text((20, y), '%s: %s' % (ax.upper(), res.get(ax, 'not measured')),
                       font=font(24), fill=C_ON if ax in res else C_DIM)
                y += 34
            self.grid(d, [
                ('TEST X', ('confirm', 'Sensor on the print head? Homes, then shakes X.',
                            ('gcode', '_SINDOH_ENSURE_HOMED\nSHAPER_CALIBRATE AXIS=X', 'Test X')),
                 C_BTN, 30, 'sensor on head'),
                ('TEST Y', ('confirm', 'Sensor on the bed? Homes, then shakes Y.',
                            ('gcode', '_SINDOH_ENSURE_HOMED\nSHAPER_CALIBRATE AXIS=Y', 'Test Y')),
                 C_BTN, 30, 'sensor on bed'),
                ('SAVE', ('confirm', 'Save the results? Klipper restarts.',
                          ('gcode', 'SAVE_CONFIG', 'Save')), C_ON if res else C_BTN, 30),
                ('SENSOR OFF', ('confirm', 'Turn the sensor off? Klipper restarts; unplug it after.',
                                ('adxl', 0)), C_BTN, 26),
            ], top=max(y + 10, 470), rows_h=96)
        else:
            self.grid(d, [
                ('SENSOR ON', ('confirm', 'Sensor plugged into the front USB port? Klipper restarts.',
                               ('adxl', 1)), C_ON, 28),
            ], top=max(y + 10, 470))

    def page_homing(self, d, st):
        homed = st['toolhead'].get('homed_axes', '')
        d.text((20, 160), 'Home', font=font(28), fill=C_TXT)
        d.text((20, 200), 'Homed: %s' % (homed.upper() or 'no'), font=font(20), fill=C_DIM)
        # Z homing raises the bed to the top: Klipper refuses it until the bed
        # is confirmed empty (BED_CLEAR, dp200_macros.cfg). Ask that here, and
        # YES sends the confirmation with the homing (as the bed level page).
        bed_q = 'Is the bed EMPTY? Homing %s raises the bed to the top and crushes anything on it.'
        items = [('HOME ALL', ('confirm', bed_q % 'all axes', ('gcode', 'BED_CLEAR\nG28', 'Home all')))]
        for axis, what in (('X', 'the print head'), ('Y', 'the bed (front/back)')):
            items.append(('HOME ' + axis, ('confirm', 'Home %s? This moves %s.' % (axis, what),
                                           ('gcode', 'G28 ' + axis, 'Home ' + axis)),
                          C_ON if axis.lower() in homed else C_BTN))
        items.append(('HOME Z', ('confirm', bed_q % 'Z', ('gcode', 'BED_CLEAR\nG28 Z', 'Home Z')),
                      C_ON if 'z' in homed else C_BTN))
        self.grid(d, items, top=240)

    def page_system(self, d, st):
        d.text((20, 160), 'System', font=font(28), fill=C_TXT)
        d.text((20, 200), 'Web: http://%s/' % self.ip, font=font(20), fill=C_DIM)
        d.text((20, 228), 'Klipper: %s' % st['webhooks']['state'], font=font(20), fill=C_DIM)
        self.grid(d, [
            ('FIRMWARE', ('confirm', 'FIRMWARE_RESTART? (stops everything)',
                          ('post', '/printer/firmware_restart', 'Firmware restart')), C_BTN, 28, 'restart'),
            ('KLIPPER', ('confirm', 'Restart Klipper host?', ('post', '/printer/restart', 'Restart')),
             C_BTN, 28, 'restart'),
            ('NETWORK', ('screen', 'network'), C_BTN, 28, 'WiFi / Ethernet'),
            ('DISPLAY', ('screen', 'display'), C_BTN, 28, 'screen'),
            ('INFO', ('info',), C_BTN, 28, 'versions, storage'),
            ('UPDATE', ('upd_open',), C_BTN, 28, 'web interface'),
            # last, on its own: the same page as a short press of the front
            # power button
            ('POWER', ('screen', 'power'), C_RED, 28, 'shut down / reboot'),
        ], top=262, rows_h=88)

    def page_update(self, d, st):
        """SYSTEM -> UPDATE: Mainsail through Moonraker's updater (its
        release zips, no git needed). Klipper and Moonraker are pinned to
        the shipped commits; they come with the port's releases."""
        d.text((20, 160), 'Update', font=font(28), fill=C_TXT)
        u = self.upd
        if self.busy:
            d.text((20, 204), self.busy + '...', font=font(22), fill=C_WARN)
        elif u.get('error'):
            for i, l in enumerate(wrap(d, u['error'], font(20), PW - 40)[:3]):
                d.text((20, 204 + i * 28), l, font=font(20), fill=C_WARN)
        elif u.get('mainsail_new') not in (None, '?'):
            same = u['mainsail_new'] == u.get('mainsail')
            d.text((20, 204), 'Mainsail is up to date' if same else 'A new Mainsail is available',
                   font=font(22), fill=C_ON if same else C_WARN)
        rows = [('Mainsail', '%s  (latest %s)' % (u.get('mainsail', '-'), u.get('mainsail_new', '?'))),
                ('Klipper', u.get('klipper', '-')), ('Moonraker', u.get('moonraker', '-'))]
        f = font(20)
        for i, (k, v) in enumerate(rows):
            d.text((20, 300 + i * 32), k, font=f, fill=C_DIM)
            d.text((150, 300 + i * 32), v, font=f, fill=C_TXT)
        d.text((20, 400), 'Klipper and Moonraker come with the DP200', font=font(17), fill=C_DIM)
        d.text((20, 422), 'port\'s releases (USB stick for now).', font=font(17), fill=C_DIM)
        newer = u.get('mainsail_new') not in (None, '?', u.get('mainsail'))
        printing = st['print_stats']['state'] in ('printing', 'paused')
        items = [('CHECK NOW', ('upd_check',), C_BTN, 26, 'latest versions')]
        if newer and not printing:
            items.append(('UPDATE', ('confirm', 'Update the web interface (Mainsail) to %s?' % u['mainsail_new'],
                                     ('upd_mainsail',)), C_ON, 28, 'Mainsail ' + u['mainsail_new']))
        self.grid(d, items, top=470, rows_h=96)

    def page_info(self, d, st):
        """SYSTEM -> INFO: build and versions, the stock firmware, storage."""
        d.text((20, 160), 'System information', font=font(28), fill=C_TXT)
        f, lh = font(19), 31
        for i, (k, v) in enumerate(self.info or []):
            y = 206 + i * lh
            d.text((20, y), k, font=f, fill=C_DIM)
            while d.textlength(v, font=f) > PW - 190 and len(v) > 4:
                v = v[:-2].rstrip() + '…'                 # keep long versions on one line
            d.text((180, y), v, font=f, fill=C_TXT)

    def page_display(self, d, st):
        t = self.settings.get('timeout', DIM_AFTER)
        d.text((20, 160), 'Display', font=font(28), fill=C_TXT)
        d.text((20, 204), 'Turns black when idle (no print, heaters off)', font=font(18), fill=C_DIM)
        d.text((20, 230), 'and wakes on the first tap.', font=font(18), fill=C_DIM)
        self.grid(d, [
            ('TIMEOUT', ('screen', 'timeout'), C_BTN, 28, fmt_timeout(t)),
            ('CONSOLE', ('screen', 'console'), C_BTN, 28, 'tap to close'),
        ], top=280)

    def page_console(self, d):
        """The kernel log, newest at the bottom, full screen (like the text
        console, which isn't drawn on the panel). Any tap closes it."""
        f = font(14, MONO)
        lh = 17
        cols = max(10, int((PW - 12) // d.textlength('M', font=f)))    # monospace
        rows = []
        for l in self.con['lines']:
            l = l.expandtabs(8)
            rows.extend(l[i:i + cols] for i in range(0, max(len(l), 1), cols))
        rows = rows[-((PH - 8) // lh):]
        d.rectangle((0, 0, PW, PH), fill=(0, 0, 0))
        for i, r in enumerate(rows):
            d.text((6, 4 + i * lh), r, font=f, fill=(200, 200, 200))
        self.buttons.append(((0, 0, PW, PH), ('screen', 'display')))

    def page_timeout(self, d, st):
        cur = self.settings.get('timeout', DIM_AFTER)
        d.text((20, 160), 'Screen timeout', font=font(28), fill=C_TXT)
        items = [(fmt_timeout(t).upper(), ('set_timeout', t), C_ON if t == cur else C_BTN, 28)
                 for t in TIMEOUTS]
        self.grid(d, items, top=210, rows_h=100)

    def page_power(self, d, st):
        """Opened by a short press of the front power button."""
        d.text((20, 160 if st else 90), 'Power', font=font(28), fill=C_TXT)
        y = 200 if st else 130
        printing = st and st['print_stats']['state'] in ('printing', 'paused')
        warn = ' The running print will be lost.' if printing else ''
        if printing:
            d.text((20, y), 'A print is running!', font=font(22), fill=C_WARN)
        d.text((20, y + 30), 'Holding the button ~%d s cuts the power at once.' % HW_CUT,
               font=font(18), fill=C_DIM)
        d.text((20, y + 54), 'Better: SHUT DOWN first, then hold the button.',
               font=font(18), fill=C_DIM)
        items = [
            ('SHUT DOWN', ('confirm', 'Shut down the printer?' + warn, ('power', 'poweroff')),
             C_RED, 28, 'power off'),
            ('REBOOT', ('confirm', 'Reboot the printer?' + warn, ('power', 'reboot')),
             C_BTN, 28, 'whole printer'),
        ]
        if st is not None:
            items.append(('KLIPPER', ('confirm', 'Restart Klipper host?' + warn,
                                      ('post', '/printer/restart', 'Restart')), C_BTN, 28, 'restart'))
        items.append(('SCREEN OFF', ('screen_off',), C_BTN, 26, 'tap to wake'))
        if os.path.exists(OUR_KERNEL):          # our kernel only (see REVERT_MARK)
            items.append(('TO STOCK', back_to_stock_confirm(warn), C_RED, 26, 'factory firmware'))
        self.grid(d, items, top=y + 100)

    def page_key_held(self, d):
        """Power button held: the hardware is about to cut the power."""
        held = time.time() - self.key_down
        d.rectangle((0, 0, PW, PH), fill=(60, 16, 16))
        d.text((30, 240), 'Power button held', font=font(34), fill=C_TXT)
        if held < LONG_POWER:
            d.text((30, 300), 'Keep holding: power OFF', font=font(30), fill=C_WARN)
            d.text((30, 345), '(cut at once, no clean shutdown)', font=font(20), fill=C_DIM)
            d.text((30, 380), 'Release now for the power menu', font=font(22), fill=C_TXT)
            frac = min(held / HW_CUT, 1.0)
            d.rounded_rectangle((30, 430, PW - 30, 470), radius=8, outline=(200, 120, 120), width=2)
            d.rounded_rectangle((32, 432, 32 + int((PW - 64) * frac), 468), radius=7, fill=(240, 60, 60))
        else:
            self.screen = 'powering_hold'              # dp200-powerkey.sh acts on its own
            self.power_at = time.time()
            d.text((30, 320), 'Shutting down...', font=font(30), fill=C_WARN)

    def page_powering(self, d):
        what = self.screen.split('_', 1)[1]
        if what != 'hold':                     # the stop scripts show the next steps
            draw_shutdown(d, what, 1)
            return
        # button held (no progress frames): dp200-powerkey.sh shuts down by itself
        d.rectangle((0, 0, PW, PH), fill=(0, 0, 0))
        lines = ['Shutting down...', '', 'Klipper stops and Linux', 'halts (~30 s). Then hold',
                 'the POWER BUTTON ~2 s', 'to switch the printer off.']
        for i, l in enumerate(lines):
            d.text((30, 240 + i * 44), l, font=font(30 if i == 0 else 24),
                   fill=C_TXT if i == 0 else C_DIM)

    def page_error(self, d, st):
        wh = st['webhooks']
        d.rectangle((0, 160, PW, 480), fill=(90, 24, 24))
        d.text((20, 172), 'Klipper: %s' % wh['state'].upper(), font=font(28), fill=C_TXT)
        for i, l in enumerate(wrap(d, wh.get('state_message', ''), font(20), PW - 40)[:9]):
            d.text((20, 214 + i * 28), l, font=font(20), fill=(240, 210, 210))
        self.grid(d, [
            ('FIRMWARE', ('post', '/printer/firmware_restart', 'Firmware restart'), C_BTN, 28, 'restart'),
            ('KLIPPER', ('post', '/printer/restart', 'Restart'), C_BTN, 28, 'restart'),
            ('NETWORK', ('screen', 'network'), C_BTN, 28, 'WiFi / IP'),
            # an enabled accelerometer config stops Klipper when the sensor is unplugged
            ('SENSOR OFF', ('confirm', 'Turn the USB accelerometer config off? Klipper restarts.',
                            ('adxl', 0)), C_WARN, 26) if os.path.exists(ADXL_ON) else None,
        ], top=500, rows_h=80)

    def overlay_confirm(self, d):
        q, action = self.confirm[:2]
        no = self.confirm[2] if len(self.confirm) > 2 else ('cancel',)
        self.buttons = [b for b in self.buttons if b[1] == ('estop',)]   # modal (STOP stays)
        d.rectangle((0, 64, PW, PH - 86), fill=(10, 10, 14))
        d.rounded_rectangle((20, 220, PW - 20, 560), radius=16, fill=C_BAR)
        for i, l in enumerate(wrap(d, q, font(28), PW - 80)[:4]):
            d.text((40, 250 + i * 38), l, font=font(28), fill=C_TXT)
        self.button(d, (40, 440, 220, 530), 'YES', action, C_ON)
        self.button(d, (260, 440, PW - 40, 530), 'NO', no)

def print_objects(st):
    """Names of the labelled objects in the current print (exclude_object)."""
    return [o.get('name', '?') for o in ((st.get('exclude_object') or {}).get('objects') or [])]


def bl_colour(v, lo=-0.25, hi=0.25):
    """Blue (low) - green (level) - red (high)."""
    t = max(0.0, min(1.0, (v - lo) / (hi - lo)))
    if t < 0.5:
        u = t / 0.5
        return (60, int(110 + 90 * u), int(220 - 130 * u))
    u = (t - 0.5) / 0.5
    return (int(60 + 170 * u), int(200 - 140 * u), int(90 - 30 * u))

def plane_fit(xs, ys, mesh):
    """Least-squares plane z = a + b*x + c*y through the mesh (Cramer's rule, no numpy)."""
    pts = [(1.0, xs[c], ys[r], mesh[r][c]) for r in range(len(ys)) for c in range(len(xs))]
    A = [[sum(p[i] * p[j] for p in pts) for j in range(3)] for i in range(3)]
    B = [sum(p[i] * p[3] for p in pts) for i in range(3)]
    det = lambda m: (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                     - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                     + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    D = det(A)
    out = []
    for k in range(3):
        m = [row[:] for row in A]
        for i in range(3):
            m[i][k] = B[i]
        out.append(det(m) / D)
    return out

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

# Macros that home all axes first when the printer is not homed
# (_SINDOH_ENSURE_HOMED, dp200_macros.cfg). Homing Z needs BED_CLEAR.
HOMES_FIRST = ('_SINDOH_ENSURE_HOMED',
               'BED_MESH_CALIBRATE', 'PROBE', 'PROBE_ACCURACY', 'LV_PROBE_CALIBRATE',
               'FILAMENT_DRY', 'EMPTY_BIN')
# Macros that home only a missing X or Y and never Z (_SINDOH_ENSURE_HOMED_XY;
# without Z homed they skip their Z move): no bed question, a plain confirm.
HOMES_XY = ('CLEAN_NOZZLE', 'LOAD_FILAMENT', 'UNLOAD_FILAMENT')

REVERT_SURE = 'Are you sure? This removes Klipper and returns the printer completely to stock.'

def revert_confirm():
    """The two-step question for a Sindoh update stick (stick_tick)."""
    return ('Sindoh update stick found. Return this printer to stock and run the update?',
            ('confirm', REVERT_SURE, ('revert_go',), ('revert_no',)),
            ('revert_no',))

def back_to_stock_confirm(warn=''):
    """POWER -> TO STOCK: the same two steps, without a stick (stock comes
    back from the factory recovery set; a Sindoh update can follow later)."""
    return ('confirm', 'Return this printer to the stock Sindoh firmware?' + warn,
            ('confirm', REVERT_SURE, ('revert_go',)))

def usb_disks():
    """Names of the USB disks (sda, sdb, ...)."""
    try:
        return sorted(n for n in os.listdir('/sys/block') if re.match(r'sd[a-z]+$', n))
    except OSError:
        return []

def sindoh_stick(disk):
    """Does this disk (its first partition, else the whole disk) hold a
    Sindoh update? Mounted read-only, and unmounted again."""
    import subprocess
    for dev in ('/dev/%s1' % disk, '/dev/%s' % disk):
        if not os.path.exists(dev):
            continue
        try:
            os.makedirs(STICK_MNT, exist_ok=True)
            if subprocess.run(['mount', '-t', 'vfat', '-o', 'ro,nosuid,nodev,noexec', dev, STICK_MNT],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20).returncode:
                continue
            try:
                return os.path.isfile(os.path.join(STICK_MNT, STICK_UPDATE))
            finally:
                subprocess.run(['umount', STICK_MNT], timeout=20)
        except (OSError, subprocess.SubprocessError):
            continue
    return False

def with_bed_check(question, act, st):
    """A confirm for a command that homes first while the printer isn't
    homed: ask about the bed in the same question, and send BED_CLEAR with
    it (otherwise Klipper refuses and the user has to answer and retry)."""
    if act[0] != 'gcode' or act[1].startswith('BED_CLEAR'):
        return (question, act)
    first = act[1].split()[0] if act[1].split() else ''
    homed = ((st or {}).get('toolhead') or {}).get('homed_axes', '')
    if first not in HOMES_FIRST or homed == 'xyz':
        return (question, act)
    return (question + ' It homes first: is the bed EMPTY?',
            (act[0], 'BED_CLEAR\n' + act[1]) + tuple(act[2:]))

def bin_count(st):
    """Purges since the bin was last emptied (save_variables bin_count)."""
    v = ((st or {}).get('save_variables') or {}).get('variables') or {}
    try:
        return int(v.get('bin_count', 0))
    except (TypeError, ValueError):
        return 0

# While a print is paused the part is on the bed and RESUME needs the axes
# as they are: nothing may home (Z homing raises the bed into the part),
# probe, or turn the motors off.
def job_state(st):
    """print_stats.state, except 'starting' while PRINT_START is not done:
    its bed question is open (pending) or its start runs (starting). The
    job is paused in Klipper meanwhile, but RESUME refuses."""
    ps = ((st or {}).get('print_stats') or {}).get('state')
    if ps == 'paused':
        pst = (st or {}).get('gcode_macro PRINT_START') or {}
        if pst.get('pending') or pst.get('starting'):
            return 'starting'
    return ps

# PRINT_START's steps (_PRINT_START_BODY, dp200_printer.cfg) as the
# starting page lists them
START_STEPS = (('ask', 'Bed empty? (question)'), ('home', 'Homing'),
               ('bed', 'Heating the bed'), ('mesh', 'Probing the bed (mesh)'),
               ('nozzle', 'Heating the nozzle'), ('purge', 'Purging and wiping'))
START_KEYS = tuple(k for k, _ in START_STEPS)
START_WARM = 150              # PRINT_START's nozzle target while probing (M104 S150)

def start_phase(st):
    """Which START_STEPS step runs, from what Klipper reports: there is no
    step variable, so read the homing, the targets and the temperatures in
    the order _PRINT_START_BODY works through them."""
    if ((st.get('gcode_macro PRINT_START') or {}).get('pending')):
        return 'ask'
    e, b = st['extruder'], st['heater_bed']
    if st['toolhead'].get('homed_axes', '') != 'xyz':
        return 'home'
    if e['target'] <= START_WARM:
        # after G28: M190 waits for the bed, then the mesh (nozzle at 150)
        return 'bed' if b['target'] and b['temperature'] < b['target'] - 1 else 'mesh'
    return 'nozzle' if e['temperature'] < e['target'] - 3 else 'purge'

PAUSE_REFUSED = ('G28', 'M84', 'M18', 'BED_MESH_CALIBRATE', 'PROBE', 'PROBE_ACCURACY',
                 'LV_PROBE_CALIBRATE', 'Z_ENDSTOP_CALIBRATE', 'FILAMENT_DRY', 'SHAPER_CALIBRATE',
                 'PID_CALIBRATE', 'BED_CLEAR')

def paused_refusal(act, st):
    """Why `act` (a confirm's YES) must not run while the print is paused,
    or None. Custom macros: unknown, so never while paused."""
    if job_state(st) not in ('paused', 'starting'):
        return None
    if act[0] in ('cal_start', 'bl_probe', 'pid_run'):
        return 'Not while a print is paused'
    if act[0] != 'gcode':
        return None
    if len(act) > 3 and act[3] == 'macro':
        return None                            # the user's own macro: their call (owner, 11-12)
    cmds = [l.split()[0].upper() for l in act[1].splitlines() if l.split()]
    if any(c in PAUSE_REFUSED for c in cmds):
        return 'Not while paused (part on the bed)'
    homed = ((st or {}).get('toolhead') or {}).get('homed_axes', '')
    if homed != 'xyz' and any(c in HOMES_FIRST + HOMES_XY for c in cmds):
        return 'Not homed: cancel the paused print'
    return None

def parse_macros(data):
    """MACROS_FILE contents -> [{'label', 'gcode'[, 'confirm']}]; ValueError if malformed."""
    if not isinstance(data, dict) or not isinstance(data.get('buttons', []), list):
        raise ValueError('expected {"buttons": [{"label": ..., "gcode": ...}, ...]}')
    out = []
    for i, b in enumerate(data.get('buttons', [])):
        if not isinstance(b, dict) or not isinstance(b.get('gcode'), str) or not b['gcode'].strip():
            raise ValueError('button %d: needs "gcode" (the macro name or G-code to run)' % (i + 1))
        e = {'label': str(b.get('label') or b['gcode'].split()[0])[:24], 'gcode': b['gcode']}
        if b.get('confirm'):
            e['confirm'] = str(b['confirm'])
        out.append(e)
    return out

def save_macros(buttons):
    """Write MACROS_FILE (atomically), owned like the config folder so
    Mainsail can still edit it."""
    tmp = MACROS_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump({'buttons': buttons}, f, indent=2)
        f.write('\n')
    if hasattr(os, 'chown'):
        try:
            ds = os.stat(os.path.dirname(MACROS_FILE))
            os.chown(tmp, ds.st_uid, ds.st_gid)
        except OSError:
            pass
    os.replace(tmp, MACROS_FILE)

def fil_confirm(mode, name, t):
    """The confirm action for LOAD/UNLOAD of filament `name` at t C."""
    macro = 'LOAD_FILAMENT' if mode == 'load' else 'UNLOAD_FILAMENT'
    arg = 'MATERIAL=%s' % name if name in FIL_STOCK else 'TEMP=%d' % t
    what = name if name != 'CUSTOM' else 'filament'
    return ('confirm', 'Heat the nozzle to %d°C and %s %s?' % (t, mode.upper(), what),
            ('gcode', '%s %s' % (macro, arg), '%s %s' % (mode.capitalize(), what), 'fil'))

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
            if st.get('dp200_cartridge') else None,
            tuple(sorted((st.get('gcode_macro _DRY') or {}).items())), ui.dry['mat'], ui.dry['hours'],
            (st.get('gcode_macro BED_CLEAR') or {}).get('asking'),
            bin_count(st), int((st['toolhead'].get('position') or [0, 0, 0])[2]) >= LOWER_BED_Z,
            tuple(b['gcode'] for b in ui.mac['buttons']), ui.mac['error'], ui.mac['page'],
            ui.mac['edit_page'], None if ui.mac['all'] is None else len(ui.mac['all']),
            ui.fil_fail and ui.fil_fail['msg'], job_state(st),
            start_phase(st) if job_state(st) == 'starting' else None)

# ---------------------------------------------------------------------------
def main():
    ui = UI()
    if '--demo' in sys.argv:
        out = sys.argv[sys.argv.index('--demo') + 1]
        ui.st = query()
        if len(sys.argv) > sys.argv.index('--demo') + 2:
            ui.screen = sys.argv[sys.argv.index('--demo') + 2]
        if net is not None:                            # network pages: read the ports first
            ui.net['info'] = {i: net.info(i) for i, _ in net.PORTS}
            ui.net['dns'] = net.dns()
            ui.net['checked'] = time.time()
        if wifi is not None:
            try:
                w = wifi.WpaCtrl()
                ui.wf['status'] = wifi.status(w)
                w.close()
            except Exception:
                pass
        ui.render().save(out)
        return
    # Mainline: end the kernel's boot progress bar (dp200-bootbar) before the
    # first frame, so it can't draw over this app. Not there on stock.
    try:
        with open(BOOTBAR_STOP, 'w') as f:
            f.write('1')
    except OSError:
        pass
    panel, touch, pkey = Panel(), Touch(), PowerKey()
    unblank()
    unblanked = time.time()
    next_poll = 0.0
    last_key = None
    key_was = False
    while True:
        now = time.time()
        btn = pkey.pressed()
        if btn != key_was:
            key_was = btn
            ui.key_event(btn, now)
            if btn:
                unblank()
        if ui.screen.startswith('powering') and now - ui.power_at > 90:
            # still running: dp200-powerkey.sh didn't act (not started?)
            ui.screen = 'home'
            ui.flash('Power-off/reboot did not happen (dp200-powerkey not running?)', 15)
            shutil.rmtree(SHUT_DIR, ignore_errors=True)   # else a later rc.dp200 stop shows them
        polled = now >= next_poll
        if polled:
            try:
                ui.st, ui.err = query(), None
                ui.ip = my_ip()
            except Exception as e:
                ui.st, ui.err = None, err_text(e)
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
        ui.busy_tick()
        ui.stick_tick()
        ui.wifi_tick()
        ui.net_tick()
        ui.shaper_tick()
        ui.bl_tick()
        ui.console_tick()
        # Redraw only when something can have changed: new status, touch,
        # STOP being held, the clock minute, a message or busy state, dimming,
        # WiFi state (scan results, connect progress).
        key = (time.strftime('%H:%M'), ui.busy, ui.msg and time.time() < ui.msg[1],
               bool(ui.dimmed()), ui.screen, ui.confirm is not None, view_key(ui), ui.err,
               ui.wf['rev'], ui.net['rev'], ui.shp['rev'], ui.bl['rev'], ui.con['rev'])
        if events or ui.press or ui.key_down is not None or key != last_key:
            panel.show(ui.render())
            last_key = key
        timeout = 0.05 if ui.press or ui.key_down is not None else \
            max(0.0, min(next_poll - time.time(), 0.1 if pkey.m is not None else 0.5))
        select.select([touch.fd], [], [], timeout)

if __name__ == '__main__':
    main()
