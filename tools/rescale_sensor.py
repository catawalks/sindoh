#!/usr/bin/env python3
"""Rescale an [adc_temperature] table in dp200_printer.cfg to reference readings.

Give pairs "klipper_reading:reference" (Klipper's reported temperature with
the CURRENT table, and the thermocouple at the same time, after a soak):

  rescale_sensor.py klipper/config/dp200_printer.cfg dp200_nozzle 26.3:19 150.2:141 210:196

A least-squares line  T_ref = a * T_klipper + b  is fitted and applied to
every temperatureN of the section (the voltages stay). The new section is
printed; nothing is written. With one pair only the offset b is fitted (a=1).
"""
import re
import sys


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    path, name, pairs = sys.argv[1], sys.argv[2], sys.argv[3:]
    pts = [tuple(float(v) for v in p.split(':')) for p in pairs]
    n = len(pts)
    if n == 1:
        a, b = 1.0, pts[0][1] - pts[0][0]
    else:
        sx = sum(p[0] for p in pts); sy = sum(p[1] for p in pts)
        sxx = sum(p[0] ** 2 for p in pts); sxy = sum(p[0] * p[1] for p in pts)
        a = (n * sxy - sx * sy) / (n * sxx - sx ** 2)
        b = (sy - a * sx) / n
    text = open(path, encoding='utf-8').read()
    m = re.search(r'^\[adc_temperature %s\]\n(.*?)(?=^\[|\Z)' % re.escape(name), text, re.S | re.M)
    if not m:
        sys.exit('section [adc_temperature %s] not found' % name)
    body = m.group(1)
    out = ['[adc_temperature %s]' % name,
           '# rescaled by tools/rescale_sensor.py: T = %.4f * T_old %+.2f' % (a, b),
           '# reference pairs (old reading:reference): %s' % ' '.join(pairs)]
    for line in body.splitlines():
        t = re.match(r'(temperature\d+):\s*(-?[\d.]+)', line)
        if t:
            out.append('%s: %.2f' % (t.group(1), a * float(t.group(2)) + b))
        elif re.match(r'voltage\d+:', line):
            out.append(line)
    print('fit: T_ref = %.4f * T_klipper %+.3f' % (a, b))
    for x, y in pts:
        print('  %.1f -> %.2f (ref %.1f, error %+.2f)' % (x, a * x + b, y, a * x + b - y))
    print()
    print('\n'.join(out))


if __name__ == '__main__':
    main()
