#!/usr/bin/env python3
"""DP200 print head clip for the Mellow FLY-ADXL345 USB board (input shaping,
X axis). Writes adxl_head_clip.stl next to this file; no other tools needed.

    py -3 adxl_head_clip.py            (edit the numbers below first)

Shape: a bridge on the flat top of the head's front block, an arm down each
side face, and two screw posts for the board on top. The left arm (the side
with the side fan) has a hook for the rear slot of that side face. The part
is a union of plain boxes and tubes that overlap each other; slicers merge
them (Cura: "Union Overlapping Volumes", on by default).

Print it standing on its FRONT face (the Y = 0 plane: "place on face" in the
slicer), PETG or PLA, 4 walls, 40 % infill. It has to be stiff: a mount that
flexes measures its own wobble.

Coordinates (mm): X across the head (left is negative, seen from the front),
Y from the front face toward the back, Z up, Z = 0 at the head's top surface.

Dimensions marked PHOTO were read from photos with a ruler (2026-11-15) and
are good to about 1 mm. Print, test the fit, correct them here.
"""
import math
import os
import struct

# ---- print head --------------------------------------------------------
HEAD_W = 55.0        # PHOTO  width across the two side faces
TOP_DEPTH = 23.0     # PHOTO  flat top: front face back to the step
SIDE_DEPTH = 32.0    # PHOTO  side face: front to back
SLOT_Y0, SLOT_Y1 = 24.0, 30.0   # PHOTO  left side, rear slot: from the front face
SLOT_TOP = 4.0       # PHOTO  top surface down to the slot's top edge
SLOT_H = 4.5         # PHOTO  slot height
# (the left side's front opening, 13-20 mm back, has a spring behind it: not
#  used. The right side has one slot; its position is not measured yet.)

# ---- fit ---------------------------------------------------------------
FIT = 0.0            # clearance per side between arms and head; 0 = light clamp
HOOK_IN = 1.4        # how far the hook reaches into the slot
HOOK_T = 2.1         # hook thickness (the slot is SLOT_H high: about 1.2 mm play each way)
WALL = 3.0           # bridge and arm thickness

# ---- sensor board (Mellow FLY-ADXL345 USB) ------------------------------
HOLE_PITCH = 16.5    # PHOTO  the two mounting holes, center to center
POST_Y = 17.0        # posts this far back from the front face; the board
                     # (about 21 x 16 mm) lies toward the front, USB-C forward
POST_H = 3.0         # keeps the solder side clear of the bridge
POST_OD = 5.5
POST_ID = 2.1        # M2.5 screw cutting its own thread (board holes about 2.5 mm)

tris = []


def quad(a, b, c, d):
    tris.append((a, b, c)); tris.append((a, c, d))


def box(x0, x1, y0, y1, z0, z1):
    p = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    #     0:x0y0z0 1:x1y0z0 2:x0y1z0 3:x1y1z0 4:x0y0z1 5:x1y0z1 6:x0y1z1 7:x1y1z1
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


half = HEAD_W / 2 + FIT
arm_z0 = -(SLOT_TOP + SLOT_H)
# bridge on the top surface
box(-half - WALL, half + WALL, 0, TOP_DEPTH, 0, WALL)
# arms down both side faces (they overlap the bridge ends)
box(-half - WALL, -half, 0, SIDE_DEPTH, arm_z0, WALL)
box(half, half + WALL, 0, SIDE_DEPTH, arm_z0, WALL)
# hook on the left arm, into the rear slot, centered in the slot's height
hz = -(SLOT_TOP + SLOT_H / 2)
box(-half - 0.5, -half + HOOK_IN, SLOT_Y0 + 0.4, SLOT_Y1 - 0.4, hz - HOOK_T / 2, hz + HOOK_T / 2)
# screw posts for the board (0.5 mm into the bridge so the shells overlap)
for sx in (-1, 1):
    tube(sx * HOLE_PITCH / 2, POST_Y, WALL - 0.5, WALL + POST_H, POST_OD / 2, POST_ID / 2)


def normal(a, b, c):
    u = [b[i] - a[i] for i in range(3)]; v = [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    m = math.sqrt(sum(k * k for k in n)) or 1.0
    return tuple(k / m for k in n)


out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'adxl_head_clip.stl')
with open(out, 'wb') as f:
    f.write(b'DP200 FLY-ADXL345 head clip'.ljust(80, b' '))
    f.write(struct.pack('<I', len(tris)))
    for a, b, c in tris:
        f.write(struct.pack('<12fH', *normal(a, b, c), *a, *b, *c, 0))
xs = [p[0] for t in tris for p in t]; ys = [p[1] for t in tris for p in t]; zs = [p[2] for t in tris for p in t]
print('%s: %d triangles, %.1f x %.1f x %.1f mm' % (out, len(tris), max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))
