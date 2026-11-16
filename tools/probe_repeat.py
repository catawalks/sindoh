"""One deploy, N single touches at the mesh reference spot (bed X95 Y100), lifting to Z10
between touches as a mesh does; then the Z switch is re-read by homing Z again.
A steady drift of the readings = Z steps lost per cycle.  probe_repeat.py N"""
import json, sys, time, urllib.parse, urllib.request
API = 'http://10.10.0.147:7125'
OX, OY = 23.5, -28.0
def gc(script, timeout=300):
    req = urllib.request.Request(API + '/printer/gcode/script?script=' + urllib.parse.quote(script), data=b'', method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)
def q(obj):
    with urllib.request.urlopen(API + '/printer/objects/query?' + obj, timeout=10) as r:
        return json.load(r)['result']['status']
n = int(sys.argv[1])
print('mcu', q('mcu')['mcu']['mcu_version'], flush=True)
gc('SET_GCODE_OFFSET Z=0\nBED_MESH_CLEAR\nBED_CLEAR', 30)
gc('G28', 300)
gc('G90\nG1 Z10 F600\nLV_DEPLOY', 120)
gc('G1 X%.2f Y%.2f F6000\nM400' % (95 - OX, 100 - OY))
v = []
for i in range(n):
    gc('_PROBE_BASE SAMPLES=1\nG1 Z10 F600\nM400')
    v.append(q('probe')['probe']['last_z_result'])
    if i % 10 == 9:
        print(' '.join('%.3f' % a for a in v[-10:]), flush=True)
gc('G90\nG1 Z10 F600\nLV_STOW', 120)
print('first5 %.4f  last5 %.4f  drift %.4f' % (sum(v[:5]) / 5, sum(v[-5:]) / 5, sum(v[-5:]) / 5 - sum(v[:5]) / 5))
