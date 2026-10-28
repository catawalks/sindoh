"""Write a pressure-advance tuning tower for the DP200 (Klipper's
TUNING_TOWER method, docs/Pressure_Advance.md): a hollow square, one wall,
printed fast with slow, sharp corners so the advance shows at the corners.
Pressure advance rises with height: PA = START + FACTOR * Z.

    python make_pa_tower.py [out.gcode] [--factor 0.020] [--height 50]

The DP200 is a bowden printer (~335 mm tube), so the default FACTOR is
0.020 (0 at the bottom, 1.0 at 50 mm). Reading it: find the height where
the corners are sharpest without a dent/gap after the corner, then
PA = FACTOR * that height (measured from the bed, in mm).
Ignore the corner with the layer-change seam (front left)."""
import argparse
import math

p = argparse.ArgumentParser()
p.add_argument('out', nargs='?', default='dp200_pa_tower.gcode')
p.add_argument('--factor', type=float, default=0.020)
p.add_argument('--start', type=float, default=0.0)
p.add_argument('--height', type=float, default=50.0)
p.add_argument('--size', type=float, default=50.0)
p.add_argument('--speed', type=float, default=60.0)    # mm/s, walls
p.add_argument('--bed', type=int, default=60)
p.add_argument('--temp', type=int, default=205)
a = p.parse_args()

CX, CY = 105.0, 100.0          # bed centre, clear of the prime line (Y 35)
W = 0.45                       # extrusion width
LH, FLH = 0.2, 0.25            # layer heights
FIL = math.pi * 1.75 ** 2 / 4


def epm(h):
    """mm of filament per mm of a W x h line (PrusaSlicer's flow model)"""
    return ((W - h) * h + math.pi * (h / 2) ** 2) / FIL


out = []
w = out.append
w('; DP200 pressure-advance tower: START=%g FACTOR=%g, %g mm square, %g mm tall'
  % (a.start, a.factor, a.size, a.height))
w('PRINT_START BED=%d EXTRUDER=%d' % (a.bed, a.temp + 5))
w('PRIME_LINE')
w('G90')
w('M83')
w('M107')
w('SET_VELOCITY_LIMIT ACCEL=500 SQUARE_CORNER_VELOCITY=1')
w('TUNING_TOWER COMMAND=SET_PRESSURE_ADVANCE PARAMETER=ADVANCE START=%g FACTOR=%g'
  % (a.start, a.factor))


def square(s):
    h = s / 2
    return [(CX - h, CY - h), (CX + h, CY - h), (CX + h, CY + h), (CX - h, CY + h)]


# first layer: the tower wall plus two brim loops outside it, slow
z = FLH
w('G1 X%.3f Y%.3f F6000' % square(a.size + 4 * W)[0])
w('G1 Z%.3f F600' % z)
for s in (a.size + 4 * W, a.size + 2 * W, a.size):
    pts = square(s)
    w('G1 X%.3f Y%.3f F6000' % pts[0])
    for x, y in pts[1:] + pts[:1]:
        w('G1 X%.3f Y%.3f E%.5f F1200' % (x, y, s * epm(FLH)))

layer = 1
pts = square(a.size)
while z + LH <= a.height + 1e-6:
    z += LH
    layer += 1
    w(';LAYER %d' % layer)
    w('G1 Z%.3f F600' % z)
    if layer == 3:
        w('M106 S255')
    w('M117 PA tower %.2f' % (a.start + a.factor * z))
    for x, y in pts[1:] + pts[:1]:
        w('G1 X%.3f Y%.3f E%.5f F%d' % (x, y, a.size * epm(LH), a.speed * 60))

w('SET_PRESSURE_ADVANCE ADVANCE=0')
w('SET_VELOCITY_LIMIT ACCEL=1500 SQUARE_CORNER_VELOCITY=5')
w('PRINT_END')
with open(a.out, 'w', newline='\n') as f:
    f.write('\n'.join(out) + '\n')
print('%s: %d layers, %.0f mm of filament' % (
    a.out, layer, a.size * 4 * (epm(FLH) * 3 + epm(LH) * (layer - 1))))
