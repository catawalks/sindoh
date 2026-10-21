"""Fetch N snapshots from ustreamer and check each frame properly (run on the printer with
Pillow, e.g. ~/moonraker-env/bin/python): end marker present? decodes without truncation?
mean brightness of the whole frame and of the bottom 16 rows (a truncated or broken JPEG
shows grey/white bottom rows or a black frame).
usage: frame_check.py URL N"""
import io, sys, time, urllib.request
from PIL import Image, ImageFile, ImageStat
url, n = sys.argv[1], int(sys.argv[2])
stats = {'eoi_missing': 0, 'truncated': 0, 'decode_error': 0, 'black': 0, 'bright_bottom': 0}
lines = []
for i in range(n):
    d = urllib.request.urlopen(url, timeout=5).read()
    has_eoi = d.rstrip(b'\x00').endswith(b'\xff\xd9')
    if not has_eoi:
        stats['eoi_missing'] += 1
    try:
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        im = Image.open(io.BytesIO(d)).convert('L')
        im.load()
        state = 'ok'
    except OSError as e:
        state = 'TRUNC' if 'truncated' in str(e) else 'ERR:%s' % e
        stats['truncated' if state == 'TRUNC' else 'decode_error'] += 1
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        im = Image.open(io.BytesIO(d)).convert('L')
        im.load()
    w, h = im.size
    mean = ImageStat.Stat(im).mean[0]
    bottom = ImageStat.Stat(im.crop((0, h - 16, w, h))).mean[0]
    if mean < 15:
        stats['black'] += 1
    if bottom > 170:
        stats['bright_bottom'] += 1
    if state != 'ok' or mean < 15 or bottom > 170 or i < 3:
        lines.append('#%d %d bytes eoi=%s %s mean=%.0f bottom=%.0f' % (i, len(d), has_eoi, state, mean, bottom))
    time.sleep(0.05)
print('frames=%d %s' % (n, stats))
print('\n'.join(lines[:20]))
