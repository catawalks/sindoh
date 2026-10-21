"""Does a cheap byte scan of the JPEG entropy data find the frames that a full decode
rejects? Inside scan data only FF 00 (stuffing), FF D0..D7 (restart) and FF D9 (end) are
legal; anything else means corruption. Run on the printer with Pillow (moonraker-env).
usage: marker_scan_check.py URL N"""
import io, sys, time, urllib.request
from PIL import Image, ImageFile

def scan_bad(d):
    sos = d.find(b'\xff\xda')
    if sos < 0:
        return 'no-SOS'
    i = sos + 2 + int.from_bytes(d[sos + 2:sos + 4], 'big')   # skip the SOS header
    n = len(d)
    while True:
        i = d.find(b'\xff', i)
        if i < 0 or i + 1 >= n:
            return None
        b = d[i + 1]
        if b == 0x00 or 0xd0 <= b <= 0xd7 or b == 0xff:
            i += 2 if b != 0xff else 1
            continue
        if b == 0xd9:
            return None
        return 'bad marker FF %02X at %d of %d' % (b, i, n)

url, n = sys.argv[1], int(sys.argv[2])
tab = {}
for k in range(n):
    d = urllib.request.urlopen(url, timeout=5).read()
    try:
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        Image.open(io.BytesIO(d)).load()
        dec = 'ok'
    except OSError as e:
        dec = 'trunc' if 'truncated' in str(e) else 'broken'
    sc = scan_bad(d)
    key = (dec, 'scan-bad' if sc else 'scan-ok')
    tab[key] = tab.get(key, 0) + 1
    if dec != 'ok' and k < 400 and tab[key] <= 3:
        print('frame %d: decode=%s scan=%s' % (k, dec, sc))
    time.sleep(0.05)
print('decode vs scan:', tab)
