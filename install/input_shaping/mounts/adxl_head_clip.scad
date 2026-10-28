// DP200 print head clip for a USB accelerometer board (input shaping, X axis).
// DRAFT: the head dimensions below are placeholders - measure the head and
// set them before printing (docs/input_shaping.md, "Mounts").
//
// A bridge sits on top of the print head; two arms reach down its sides and
// hook into the notches near the top of each side. The sensor board screws
// to the bridge. Print it bridge-down in PETG/PLA, 4 walls, 40 % infill: it
// has to be stiff, a flexible mount measures its own wobble.

/* [Print head - MEASURE] */
head_width      = 40;   // across the head where the arms grip (mm)
head_depth      = 30;   // front-to-back length of the bridge (mm)
notch_down      = 8;    // top of head -> top edge of the side notches (mm)
notch_height    = 3;    // notch opening height (mm)
notch_depth     = 1.5;  // how far the hook reaches into the notch (mm)
fit             = 0.2;  // clearance per side (snap fit: 0.1-0.3)

/* [Sensor board] */
// BTT ADXL345 V2.0 placeholders - check against the board
board_holes     = [[-9.5, 0], [9.5, 0]];  // hole positions from the bridge centre
hole_d          = 2.4;                     // M2 screw, self-tapping into the plastic
standoff        = 4;                       // keep the parts on the back of the board clear

/* [Part] */
wall            = 3;    // bridge and arm thickness (stiffness)

$fn = 32;
w = head_width + 2 * fit;

module arm() {
    // arm down the side of the head, hook pointing inward at the notch
    translate([0, -head_depth / 2, -(notch_down + notch_height)])
        cube([wall, head_depth, notch_down + notch_height + wall]);
    translate([-notch_depth, -head_depth / 2, -(notch_down + notch_height)])
        cube([notch_depth + wall, head_depth, notch_height - fit]);
}

difference() {
    union() {
        // bridge over the top
        translate([-w / 2 - wall, -head_depth / 2, 0]) cube([w + 2 * wall, head_depth, wall]);
        translate([w / 2, 0, 0]) arm();
        translate([-w / 2, 0, 0]) mirror([1, 0, 0]) arm();
        // standoffs for the board
        for (p = board_holes) translate([p[0], p[1], wall]) cylinder(d = hole_d + 3, h = standoff);
    }
    for (p = board_holes) translate([p[0], p[1], -1]) cylinder(d = hole_d, h = wall + standoff + 2);
}
