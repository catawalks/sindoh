#!/usr/bin/env python3
"""DP200 print head clip for the Mellow FLY-ADXL345 USB board (input shaping,
X axis). Writes adxl_head_clip.stl next to this file; no other tools needed.

    py -3 adxl_head_clip.py            (edit the numbers below first)

Shape: a bridge on the flat top of the head's front block, an arm down each
side face, and two screw posts for the board on top. Each arm has a hook
with a lead-in ramp for a slot in its side face: left (the side with the
side fan) the rear, 7 x 3 mm slot; right that side's single slot. To fit it,
hook one side in at an angle, then press the other side down until it snaps.
The part is a union of plain boxes, wedges and tubes that overlap each other;
slicers merge them (Cura: "Union Overlapping Volumes", on by default).

Print it standing on its FRONT face (the flat face nearest the posts: "place
on face" in the slicer), PETG or PLA, 4 walls, 40 % infill. It has to be stiff: a mount that
flexes measures its own wobble.

Coordinates (mm): X across the head (left is negative, seen from the front),
Y from the front face toward the back, Z up, Z = 0 at the head's top surface.

Dimensions marked PHOTO were read from photos with a ruler (2026-11-15) and
are good to about 1 mm; the others are the owner's caliper readings of the
same day. Print, test the fit, correct them here.
"""
import math
import os
import struct

# ---- print head --------------------------------------------------------
HEAD_W = 55.8        # calipers: width across the two side faces
TOP_DEPTH = 23.0     # PHOTO  flat top: front face back to the step
SIDE_DEPTH = 32.0    # PHOTO  side face: front to back
FRONT_CUT = 10.0     # the clip starts this far behind the front face: at the
                     # X home position (right end) the Bowden tube comes down
                     # in front of the head, and the first version, which
                     # reached the front face, hit it (2026-11-16)
# Slots in the side faces (calipers): (from the front face, length along Y,
# top surface down to the slot's top edge, slot height)
SLOT_L = (20.0, 7.0, 3.8, 3.0)   # left, rear slot
SLOT_R = (21.0, 5.0, 4.0, 6.0)   # right, its only slot
# (the left side also has a 5 x 5 opening 12 mm back and 4.5 down, with a
#  spring behind it: not used)

# ---- fit ---------------------------------------------------------------
FIT = 0.0            # clearance per side between arms and head; 0 = light clamp
HOOK_IN = 1.0        # how far the hooks reach into the slots
HOOK_T = 2.0         # hook thickness
HOOK_GAP = 0.4       # hook top below the slot's top edge; also the end play along Y
RAMP = 1.6           # height of the lead-in wedge under each hook
ARM_DOWN = 9.0       # arms reach this far below the top surface
WALL = 3.0           # bridge and arm thickness

# ---- sensor board (Mellow FLY-ADXL345 USB) ------------------------------
HOLE_PITCH = 15.5    # calipers: the two mounting holes, center to center
POST_Y = 17.0        # posts this far back from the front face
# The posts sit at the LEFT end of the bridge, the left post flush with the
# clip's left side: at X home the head is close to the right side wall, and a
# USB cable from a board in the middle would hit that wall (2026-11-16).
POST_H = 3.0         # keeps the solder side clear of the bridge
POST_OD = 6.0
POST_ID = 2.5        # M3 screw cutting its own thread (board holes 3.2 mm)

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


def wedge(pts, y0, y1):
    """Triangle pts = three (x, z) corners, extruded from y0 to y1."""
    (ax, az), (bx, bz), (cx, cz) = pts
    if (bx - ax) * (cz - az) - (bz - az) * (cx - ax) < 0:
        pts = [pts[0], pts[2], pts[1]]
    f = [(x, y0, z) for x, z in pts]; r = [(x, y1, z) for x, z in pts]
    tris.append((f[0], f[1], f[2])); tris.append((r[0], r[2], r[1]))
    for i in range(3):
        j = (i + 1) % 3
        quad(f[j], f[i], r[i], r[j])


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
# bridge on the top surface
box(-half - WALL, half + WALL, FRONT_CUT, TOP_DEPTH, 0, WALL)
# arms down both side faces (they overlap the bridge ends)
box(-half - WALL, -half, FRONT_CUT, SIDE_DEPTH, -ARM_DOWN, WALL)
box(half, half + WALL, FRONT_CUT, SIDE_DEPTH, -ARM_DOWN, WALL)
# a hook per arm: just under the slot's top edge, with a ramp below it so the
# arm rides over the edge of the head when the clip is pressed on
for sx, (sy, sl, stop, sh) in ((-1, SLOT_L), (1, SLOT_R)):
    assert HOOK_T + HOOK_GAP <= sh and stop + HOOK_GAP + HOOK_T + RAMP <= ARM_DOWN
    y0, y1 = sy + HOOK_GAP, sy + sl - HOOK_GAP
    zt = -(stop + HOOK_GAP); zb = zt - HOOK_T
    face = sx * half                        # the arm's inner face
    xa, xb = sorted((face + sx * 0.5, face - sx * HOOK_IN))
    box(xa, xb, y0, y1, zb, zt)
    wedge([(face + sx * 0.5, zb), (face - sx * HOOK_IN, zb), (face + sx * 0.5, zb - RAMP)], y0, y1)
# screw posts for the board (0.5 mm into the bridge so the shells overlap)
assert FRONT_CUT + POST_OD / 2 <= POST_Y <= TOP_DEPTH - POST_OD / 2
post_x = -half - WALL + POST_OD / 2
for px in (post_x, post_x + HOLE_PITCH):
    tube(px, POST_Y, WALL - 0.5, WALL + POST_H, POST_OD / 2, POST_ID / 2)


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
