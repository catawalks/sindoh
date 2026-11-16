#!/usr/bin/env python3
"""DP200 bed mount for the Mellow FLY-ADXL345 USB board (input shaping, Y
axis). Writes adxl_bed_bar.stl next to this file; no other tools needed.

    py -3 adxl_bed_bar.py            (edit the numbers below first)

The build plate has two aluminum tabs at its front edge, each with one
threaded M3 hole; a plastic grip is screwed under each pair of tabs from
below (two grips: left and right). This part takes the place of ONE grip:
a flat bar under the two tabs, held by the grip's own two screws from below.
A rib on top of the bar fills the gap between the tabs (it locates the bar
sideways) and carries two screw posts for the board.

Fitting: remove one grip (two screws from below), hold the bar under the
tabs with the rib in the gap and the posts up, put the two screws back. The
screws may stick out of the tabs' top: the holes go right through.
Screw the board to the posts with two M3 x 6 screws (they cut their own
thread). The bed moves in Y, so run SHAPER_CALIBRATE AXIS=Y.

Print it lying flat, bar down, posts up: no supports. PETG or PLA, 4 walls,
40 % infill. The part is a union of overlapping solids; slicers merge them.

Coordinates (mm): X along the plate's front edge, X = 0 midway between the
two screw holes; Y = 0 at the tabs' front edge, negative toward the plate;
Z = 0 at the underside of the tabs, up positive.

All dimensions are the owner's caliper readings of 2026-11-16.
"""
import math
import os
import struct

# ---- build plate tabs ----------------------------------------------------
SCREW_PITCH = 73.5   # the two threaded holes, center to center
SCREW_BACK = 3.75    # hole centers behind the tabs' front edge
TAB_W = 27.0         # width of each tab
TAB_GAP = 34.0       # open gap between the two tabs
TAB_OUT = 10.0       # tabs stick out this far from the plate's front edge
TAB_T = 2.0          # tab thickness

# ---- bar -----------------------------------------------------------------
BAR_T = 4.0          # the grip's screws are M3 x 6 under the head: 4 mm of
                     # bar leaves 2 mm of thread, the full tab thickness
BAR_BACK = 9.0       # bar reaches this far behind the tabs' front edge
                     # (1 mm short of the plate's own edge)
BAR_FRONT = 3.0      # and this far in front of it
SCREW_D = 3.4        # clearance hole for M3
RIB_FIT = 0.5        # clearance per side between the rib and the tabs

# ---- sensor board (Mellow FLY-ADXL345 USB) --------------------------------
HOLE_PITCH = 15.5    # the board's two mounting holes, center to center
POST_H = 5.0         # above the rib; an M3 x 6 screw through the 1.6 mm
                     # board must not bottom out (the bore is blind)
POST_OD = 6.0
POST_ID = 2.5        # M3 screw cutting its own thread (board holes 3.2 mm)

tris = []


def quad(a, b, c, d):
    tris.append((a, b, c)); tris.append((a, c, d))


def box(x0, x1, y0, y1, z0, z1):
    p = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    quad(p[0], p[2], p[3], p[1])    # bottom (-z)
    quad(p[4], p[5], p[7], p[6])    # top (+z)
    quad(p[0], p[1], p[5], p[4])    # front (-y)
    quad(p[2], p[6], p[7], p[3])    # back (+y)
    quad(p[0], p[4], p[6], p[2])    # left (-x)
    quad(p[1], p[3], p[7], p[5])    # right (+x)


def tube(cx, cy, z0, z1, ro, ri, n=48):
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)
        o0, o1 = (cx + ro * c0, cy + ro * s0), (cx + ro * c1, cy + ro * s1)
        i0, i1 = (cx + ri * c0, cy + ri * s0), (cx + ri * c1, cy + ri * s1)
        quad(o0 + (z0,), o1 + (z0,), o1 + (z1,), o0 + (z1,))      # outside
        quad(i1 + (z0,), i0 + (z0,), i0 + (z1,), i1 + (z1,))      # bore
        quad(o0 + (z1,), o1 + (z1,), i1 + (z1,), i0 + (z1,))      # top ring
        quad(o1 + (z0,), o0 + (z0,), i0 + (z0,), i1 + (z0,))      # bottom ring


def block_with_hole(x0, x1, y0, y1, z0, z1, cx, cy, r, n=48):
    """A box with a round hole straight through it along Z."""
    def edge_point(a):
        # where the ray from the hole's center at angle a leaves the box
        dx, dy = math.cos(a), math.sin(a)
        best = None
        for t, side in (((x1 - cx) / dx if dx > 1e-12 else None, 'E'),
                        ((x0 - cx) / dx if dx < -1e-12 else None, 'W'),
                        ((y1 - cy) / dy if dy > 1e-12 else None, 'N'),
                        ((y0 - cy) / dy if dy < -1e-12 else None, 'S')):
            if t is not None and t > 0 and (best is None or t < best[0]):
                best = (t, side)
        t, side = best
        return (cx + t * dx, cy + t * dy), side
    corner = {('E', 'N'): (x1, y1), ('N', 'W'): (x0, y1),
              ('W', 'S'): (x0, y0), ('S', 'E'): (x1, y0)}
    ang = [2 * math.pi * i / n + 1e-4 for i in range(n)]
    inner = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in ang]
    outer = [edge_point(a) for a in ang]
    for i in range(n):
        j = (i + 1) % n
        (oi, si), (oj, sj) = outer[i], outer[j]
        ii, ij = inner[i], inner[j]
        # top face (normal +z) and bottom face (normal -z): ring pieces
        quad(ii + (z1,), oi + (z1,), oj + (z1,), ij + (z1,))
        quad(ii + (z0,), ij + (z0,), oj + (z0,), oi + (z0,))
        # hole wall (normal toward the hole's axis)
        quad(ii + (z0,), ii + (z1,), ij + (z1,), ij + (z0,))
        if si == sj:
            quad(oi + (z0,), oj + (z0,), oj + (z1,), oi + (z1,))  # outer wall
        else:
            c = corner[(si, sj)]
            tris.append((oi + (z1,), c + (z1,), oj + (z1,)))
            tris.append((oi + (z0,), oj + (z0,), c + (z0,)))
            quad(oi + (z0,), c + (z0,), c + (z1,), oi + (z1,))
            quad(c + (z0,), oj + (z0,), oj + (z1,), c + (z1,))


half = TAB_GAP / 2 + TAB_W           # outer edge of each tab
sx = SCREW_PITCH / 2
assert TAB_GAP / 2 < sx - SCREW_D < sx + SCREW_D < half
split = sx - 7.0                     # the hole blocks start here
# bar under the tabs: a plain middle and a block with a screw hole per end
box(-split - 0.5, split + 0.5, -BAR_BACK, BAR_FRONT, -BAR_T, 0)
for s in (-1, 1):
    xa, xb = sorted((s * split, s * half))
    block_with_hole(xa, xb, -BAR_BACK, BAR_FRONT, -BAR_T, 0, s * sx, -SCREW_BACK, SCREW_D / 2)
# rib in the gap between the tabs, up to the tabs' top surface
rib = TAB_GAP / 2 - RIB_FIT
box(-rib, rib, -BAR_BACK, BAR_FRONT, -0.5, TAB_T)
# screw posts for the board, on the rib
post_y = (BAR_FRONT - BAR_BACK) / 2
for s in (-1, 1):
    tube(s * HOLE_PITCH / 2, post_y, TAB_T - 0.5, TAB_T + POST_H, POST_OD / 2, POST_ID / 2)


def normal(a, b, c):
    u = [b[i] - a[i] for i in range(3)]; v = [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    m = math.sqrt(sum(k * k for k in n)) or 1.0
    return tuple(k / m for k in n)


out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'adxl_bed_bar.stl')
with open(out, 'wb') as f:
    f.write(b'DP200 FLY-ADXL345 bed bar'.ljust(80, b' '))
    f.write(struct.pack('<I', len(tris)))
    for a, b, c in tris:
        f.write(struct.pack('<12fH', *normal(a, b, c), *a, *b, *c, 0))
xs = [p[0] for t in tris for p in t]; ys = [p[1] for t in tris for p in t]; zs = [p[2] for t in tris for p in t]
print('%s: %d triangles, %.1f x %.1f x %.1f mm' % (out, len(tris), max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))
