"""Probe settling after ONE deploy (as a bed mesh does), mesh off.
Single-sample probes, lifted to Z10 between, at bed X 25/100/175, Y 30."""
import json, time, urllib.parse, urllib.request
API = 'http://10.10.0.147:7125'
OX, OY = 23.5, -28.0
def gc(script, timeout=240):
    req = urllib.request.Request(API + '/printer/gcode/script?script=' + urllib.parse.quote(script), data=b'', method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)
def q(obj):
    with urllib.request.urlopen(API + '/printer/objects/query?' + obj, timeout=10) as r:
        return json.load(r)['result']['status']
def probes(px, n, label):
    gc('G90\nG1 Z10 F600\nG1 X%.2f Y%.2f F6000\nM400' % (px - OX, 30 - OY))
    v = []
    for _ in range(n):
        gc('_PROBE_BASE SAMPLES=1\nG1 Z10 F600\nM400')
        v.append(q('probe')['probe']['last_z_result'])
    print('%s %-12s %s  mean(last 3) %.4f' % (time.strftime('%H:%M:%S'), label, ' '.join('%.4f' % a for a in v), sum(v[-3:]) / 3), flush=True)
    return v
gc('SET_GCODE_OFFSET Z=0\nBED_MESH_CLEAR', 30)
if q('toolhead')['toolhead']['homed_axes'] != 'xyz':
    gc('BED_CLEAR', 30)
    gc('G28', 240)
    print('homed', flush=True)
gc('G90\nG1 Z10 F600\nLV_DEPLOY', 120)
print('deployed', flush=True)
probes(100, 10, 'center #1')
for px, lab in ((25, 'left #1'), (100, 'center #2'), (175, 'right #1'), (100, 'center #3'), (25, 'left #2'), (175, 'right #2')):
    probes(px, 6, lab)
gc('G90\nG1 Z10 F600\nLV_STOW', 120)
print('stowed')
