"""Time the Pillow primitives on the DP200 (armel soft-float) to choose a UI approach."""
import time
from PIL import Image, ImageDraw, ImageFont

FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

def t(label, fn, n=3):
    t0 = time.time()
    for _ in range(n):
        fn()
    print('%-28s %7.1f ms' % (label, (time.time() - t0) * 1000 / n), flush=True)

im = Image.new('RGB', (800, 480), (24, 24, 28))
d = ImageDraw.Draw(im)
f44 = ImageFont.truetype(FONT, 44)
f22 = ImageFont.truetype(FONT, 22)
t('new image', lambda: Image.new('RGB', (800, 480), (24, 24, 28)))
t('rectangle fill 720x30', lambda: d.rectangle((40, 270, 760, 300), fill=(80, 200, 120)))
t('rounded_rectangle r14', lambda: d.rounded_rectangle((40, 330, 205, 410), radius=14, fill=(60, 140, 90)))
t('text 22px 20 chars', lambda: d.text((40, 440), 'Mainsail: http://10.', font=f22, fill=(160, 160, 170)))
t('text 44px "25 / 0 C"', lambda: d.text((40, 130), '25 / 0 C', font=f44, fill=(255, 170, 80)))
t('text 44px no antialias', lambda: (setattr(d, 'fontmode', '1'), d.text((40, 130), '25 / 0 C', font=f44, fill=(255, 170, 80)), setattr(d, 'fontmode', 'L')))
f44b = ImageFont.truetype(FONT, 44, layout_engine=ImageFont.Layout.BASIC)
t('text 44px BASIC layout', lambda: d.text((40, 130), '25 / 0 C', font=f44b, fill=(255, 170, 80)))
# glyph cache idea: pre-render each character once, then paste
glyphs = {}
for ch in '0123456789 /.%C':
    m = f44.getmask(ch)
    glyphs[ch] = (Image.frombytes('L', m.size, bytes(m)), f44.getlength(ch))
def paste_text(x, y, s):
    for ch in s:
        g, w = glyphs[ch]
        im.paste((255, 170, 80), (int(x), y), g)
        x += w
t('glyph-cache paste 8 chars', lambda: paste_text(40, 130, '25 / 0 C'))
import importlib.util
spec = importlib.util.spec_from_file_location('poc', '/usr/src/dp200/display/fb_status_poc.py')
src = open(spec.origin).read().replace('\nmain()\n', '\n')
poc = {}
exec(compile(src, spec.origin, 'exec'), poc)
t('to_rgb565 (LUT+chops)', lambda: poc['to_rgb565'](im))
