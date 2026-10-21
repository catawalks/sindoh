"""Proof of concept: draw a Klipper status screen on the DP200's touch panel
straight into the framebuffer (RGB565, /dev/fb0 800x480, virtual 800x960 =
two pages). The panel is mounted in PORTRAIT: we draw 480x800 and turn the
image 90 degrees clockwise when writing. Data from Moonraker's HTTP API.
Run as root in the chroot with Debian's python3-pil (fb0 is root-only):
    /usr/bin/python3 fb_status_poc.py [--loop]"""
import json, socket, sys, time, urllib.request
from PIL import Image, ImageChops, ImageDraw, ImageFont

W, H = 480, 800            # portrait, as mounted
FB = '/dev/fb0'
API = 'http://127.0.0.1:7125'

def query():
    objs = 'webhooks&extruder&heater_bed&print_stats&display_status&output_pin%20lamp&toolhead'
    with urllib.request.urlopen(API + '/printer/objects/query?' + objs, timeout=3) as r:
        return json.load(r)['result']['status']

def my_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except OSError:
        return '?'
    finally:
        s.close()

_fonts = {}

def font(size):
    if size not in _fonts:
        _fonts[size] = _load_font(size)
    return _fonts[size]

def _load_font(size):
    for f in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()

def render(st):
    im = Image.new('RGB', (W, H), (24, 24, 28))
    d = ImageDraw.Draw(im)
    big, mid, small = font(44), font(30), font(22)
    state = st['webhooks']['state']
    pstate = st['print_stats']['state']
    colour = (80, 200, 120) if state == 'ready' else (230, 80, 70)
    d.rectangle((0, 0, W, 110), fill=(36, 36, 44))
    d.text((24, 12), 'Sindoh DP200', font=mid, fill=(235, 235, 235))
    d.text((24, 58), 'Klipper', font=small, fill=(170, 170, 180))
    d.text((W - 150, 62), state.upper(), font=small, fill=colour)
    e, b = st['extruder'], st['heater_bed']
    d.text((30, 135), 'Nozzle', font=small, fill=(170, 170, 180))
    d.text((30, 165), '%.0f / %.0f °C' % (e['temperature'], e['target']), font=big, fill=(255, 170, 80))
    d.text((30, 245), 'Bed', font=small, fill=(170, 170, 180))
    d.text((30, 275), '%.0f / %.0f °C' % (b['temperature'], b['target']), font=big, fill=(110, 180, 255))
    d.text((30, 365), 'Job: %s' % pstate, font=mid, fill=(220, 220, 220))
    prog = st.get('display_status', {}).get('progress', 0.0)
    d.rectangle((30, 415, W - 30, 445), outline=(90, 90, 100), width=2)
    d.rectangle((32, 417, 32 + int((W - 64) * prog), 443), fill=(80, 200, 120))
    lamp = st.get('output_pin lamp', {}).get('value', 0)
    # touch "buttons" (drawn only - this PoC does not read touches yet), 2x2 grid
    for i, (label, on) in enumerate((('LAMP', lamp > 0), ('LOAD', False), ('UNLOAD', False), ('STOP', False))):
        x = 30 + (i % 2) * 220
        y = 480 + (i // 2) * 120
        d.rounded_rectangle((x, y, x + 200, y + 100), radius=14,
                            fill=(60, 140, 90) if on else (48, 48, 58) if label != 'STOP' else (150, 40, 40))
        d.text((x + 24, y + 32), label, font=mid, fill=(240, 240, 240))
    d.text((30, 735), 'http://%s/' % my_ip(), font=small, fill=(160, 160, 170))
    d.text((W - 120, 735), time.strftime('%H:%M'), font=small, fill=(120, 120, 130))
    return im

# RGB565 little-endian, all in Pillow's C code (Pillow 11 has no BGR;16 packer;
# a Python per-pixel loop takes ~5 s on this CPU). The bit fields of the
# high and low byte do not overlap, so ImageChops.add of two LUT-mapped
# channels is an OR.
_LUT_HI_R = [v & 0xf8 for v in range(256)]
_LUT_HI_G = [v >> 5 for v in range(256)]
_LUT_LO_G = [(v << 3) & 0xe0 for v in range(256)]
_LUT_LO_B = [v >> 3 for v in range(256)]

def to_rgb565(im):
    im = im.transpose(Image.Transpose.ROTATE_270)   # portrait -> fb0 landscape (confirmed upright)
    r, g, b = im.split()
    hi = ImageChops.add(r.point(_LUT_HI_R), g.point(_LUT_HI_G))
    lo = ImageChops.add(g.point(_LUT_LO_G), b.point(_LUT_LO_B))
    return Image.merge('LA', (lo, hi)).tobytes()   # LA = byte pairs (lo, hi)

def show(raw):
    with open(FB, 'r+b') as f:
        f.write(raw)          # page 0 (y 0..479)
        f.write(raw)          # page 1 (y 480..959): whichever page is panned in shows it

def main():
    loop = '--loop' in sys.argv
    while True:
        t0 = time.time()
        st = query()
        tq = time.time()
        im = render(st)
        tr = time.time()
        raw = to_rgb565(im)
        t1 = time.time()
        show(raw)
        print('query %.2f s, render %.2f s, convert %.2f s, write %.2f s'
              % (tq - t0, tr - tq, t1 - tr, time.time() - t1), flush=True)
        if not loop:
            break
        time.sleep(max(0.0, 2.0 - (time.time() - t0)))

main()
