"""4-corner touch test for the DP200 panel (portrait 480x800 as mounted).
Draws numbered targets, records the raw touch position for each tap and
prints the result. Run as root in the chroot (needs /dev/fb0 and /dev/event0):
    /usr/bin/python3 touch_cal.py"""
import fcntl, os, select, struct, sys, time
from PIL import Image, ImageChops, ImageDraw, ImageFont

PW, PH = 480, 800          # portrait, as the user sees it
FB, EV = '/dev/fb0', '/dev/event0'
INSET = 50
TARGETS = [(INSET, INSET), (PW - INSET, INSET), (PW - INSET, PH - INSET), (INSET, PH - INSET)]
NAMES = ['top-left', 'top-right', 'bottom-right', 'bottom-left']

EV_SYN, EV_ABS = 0, 3
SYN_REPORT, SYN_MT_REPORT = 0, 2
ABS_MT_TOUCH_MAJOR, ABS_MT_X, ABS_MT_Y, ABS_MT_TRACKING_ID = 0x30, 0x35, 0x36, 0x39
EVENT = struct.Struct('<llHHi')    # kernel 3.2: time32 input_event, 16 bytes

_LUT = ([v & 0xf8 for v in range(256)], [v >> 5 for v in range(256)],
        [(v << 3) & 0xe0 for v in range(256)], [v >> 3 for v in range(256)])

def show(portrait):
    # The panel's fb0 is 800x480 landscape; mounted it is rotated, so turn
    # the portrait image 90 degrees clockwise before writing.
    im = portrait.transpose(Image.Transpose.ROTATE_270)
    r, g, b = im.split()
    hi = ImageChops.add(r.point(_LUT[0]), g.point(_LUT[1]))
    lo = ImageChops.add(g.point(_LUT[2]), b.point(_LUT[3]))
    raw = Image.merge('LA', (lo, hi)).tobytes()
    with open(FB, 'r+b') as f:
        f.write(raw)
        f.write(raw)

def font(size):
    try:
        return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', size)
    except OSError:
        return ImageFont.load_default()

def draw(active, done):
    im = Image.new('RGB', (PW, PH), (20, 20, 26))
    d = ImageDraw.Draw(im)
    f, fs = font(40), font(26)
    d.text((40, 300), 'TOUCH TEST', font=f, fill=(240, 240, 240))
    if active < 4:
        d.text((40, 360), 'Tap target %d' % (active + 1), font=fs, fill=(255, 200, 80))
        d.text((40, 400), '(%s)' % NAMES[active], font=fs, fill=(180, 180, 190))
    else:
        d.text((40, 360), 'Done - thank you', font=fs, fill=(80, 220, 120))
    for i, (x, y) in enumerate(TARGETS):
        col = (80, 220, 120) if i in done else (255, 200, 80) if i == active else (90, 90, 100)
        d.ellipse((x - 30, y - 30, x + 30, y + 30), outline=col, width=4)
        d.line((x - 40, y, x + 40, y), fill=col, width=2)
        d.line((x, y - 40, x, y + 40), fill=col, width=2)
        tx = x + 40 if x < PW / 2 else x - 70
        ty = y + 30 if y < PH / 2 else y - 70
        d.text((tx, ty), str(i + 1), font=f, fill=col)
    show(im)

def absinfo(fd, code):
    req = 0x80000000 | (24 << 16) | (ord('E') << 8) | (0x40 + code)   # EVIOCGABS
    buf = bytearray(24)
    fcntl.ioctl(fd, req, buf)
    return struct.unpack('<6i', buf)   # value, min, max, fuzz, flat, resolution

def main():
    fd = os.open(EV, os.O_RDONLY)
    for name, code in (('X', ABS_MT_X), ('Y', ABS_MT_Y)):
        try:
            print('abs %s: value/min/max/fuzz/flat/res = %s' % (name, absinfo(fd, code)), flush=True)
        except OSError as e:
            print('abs %s: EVIOCGABS failed: %s' % (name, e), flush=True)
    results, active = [], 0
    draw(active, [])
    pts, x, y, touching, last_ev = [], None, None, False, 0.0
    deadline = time.time() + 180
    while active < 4 and time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.25)
        now = time.time()
        if not r:
            if touching and now - last_ev > 0.3:      # no events: finger lifted
                touching = False
            else:
                continue
        else:
            data = os.read(fd, EVENT.size * 64)
            last_ev = now
            for off in range(0, len(data) - EVENT.size + 1, EVENT.size):
                _, _, typ, code, val = EVENT.unpack_from(data, off)
                if typ == EV_ABS and code == ABS_MT_X:
                    x = val
                elif typ == EV_ABS and code == ABS_MT_Y:
                    y = val
                elif typ == EV_SYN and code == SYN_REPORT:
                    if x is not None and y is not None:
                        touching = True
                        pts.append((x, y))
                        x = y = None
                    elif touching:                      # empty frame = release
                        touching = False
            if touching:
                continue
        if pts:
            # median of the samples of this tap (resistive panels are noisy)
            xs, ys = sorted(p[0] for p in pts), sorted(p[1] for p in pts)
            mx, my = xs[len(xs) // 2], ys[len(ys) // 2]
            print('target %d (%s) portrait %s: raw x=%d y=%d  (%d samples, x %d..%d, y %d..%d)'
                  % (active + 1, NAMES[active], TARGETS[active], mx, my, len(pts),
                     xs[0], xs[-1], ys[0], ys[-1]), flush=True)
            results.append((mx, my))
            active += 1
            pts = []
            draw(active, list(range(active)))
            time.sleep(0.5)
            os.read(fd, 65536) if select.select([fd], [], [], 0)[0] else None
    if active < 4:
        print('timeout after %d targets' % active)
    print('RESULT', results, flush=True)

main()
