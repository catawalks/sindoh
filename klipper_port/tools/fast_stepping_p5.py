"""Probe repeatability: home all, then 2 x 5 probes at X95 Y130 (bed empty).
usage: p5.py LOG"""
import json, sys, time, urllib.request
sys.argv = [sys.argv[0], sys.argv[1]]
src = open(sys.argv[0].replace('p5.py', 'drift_test.py'), encoding='utf-8').read()
exec(compile(src.split("\ndef trigger")[0], 'drift_test.py', 'exec'))

def q(obj):
    with urllib.request.urlopen(API + '/printer/objects/query?' + obj, timeout=10) as r:
        return json.load(r)['result']['status']

def probe():
    gc('G90\nG1 Z15 F600\nG1 X95 Y130 F6000\nM400\nPROBE\nG1 Z15 F600\nM400', timeout=120)
    return q('probe')['probe']['last_z_result']

log('--- probe test, mcu %s' % q('mcu')['mcu']['mcu_version'])
gc('BED_CLEAR\nG28', 180)
for rnd in (1, 2):
    z = [probe() for _ in range(5)]
    log('round %d: %s  spread %.4f  mean %.4f'
        % (rnd, ' '.join('%.4f' % v for v in z), max(z) - min(z), sum(z) / 5))
gc('G90\nG1 Z20 F600\nM400')
