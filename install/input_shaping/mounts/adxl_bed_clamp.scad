// DP200 bed clamp for a USB accelerometer board (input shaping, Y axis).
// DRAFT: the plate dimensions are placeholders - measure and set them
// (docs/input_shaping.md, "Mounts").
//
// A C-clamp that grips the front edge of the bed plate, tightened by an M3
// screw from below (nut trapped in the lower jaw). The board screws on top.
// Y moves the whole bed, so any rigid point on the plate measures Y; the
// front edge is reachable without removing anything. Print upright (the
// C opening facing sideways) in PETG/PLA, 4 walls, 40 % infill.

/* [Bed plate - MEASURE] */
plate_thick     = 4;    // plate (+ build sheet) thickness at the front edge (mm)
grip_depth      = 10;   // how far the jaws reach over the plate (mm); keep
                        // clear of the print area and the levelling screws
under_clear     = 6;    // free space under the plate edge for the lower jaw (mm)

/* [Sensor board] */
board_holes     = [[-9.5, 0], [9.5, 0]];  // BTT ADXL345 V2.0 placeholders
hole_d          = 2.4;
standoff        = 4;

/* [Part] */
width           = 30;   // along the bed edge
jaw             = 3;    // jaw thickness
fit             = 0.3;
m3_d            = 3.4;
m3_nut          = 6.4;  // across flats + clearance

$fn = 32;
gap = plate_thick + fit;
lower = min(jaw + 1, under_clear);

difference() {
    union() {
        // back of the C (in front of the plate edge)
        translate([-width / 2, -jaw, -lower]) cube([width, jaw, lower + gap + jaw]);
        // upper jaw on top of the plate, carries the board
        translate([-width / 2, 0, gap]) cube([width, grip_depth, jaw]);
        // lower jaw under the plate, holds the clamp screw
        translate([-width / 2, 0, -lower]) cube([width, grip_depth, lower]);
        for (p = board_holes)
            translate([p[0], grip_depth / 2 + p[1], gap + jaw]) cylinder(d = hole_d + 3, h = standoff);
    }
    // clamp screw up through the lower jaw, nut trapped from below
    translate([0, grip_depth / 2, -lower - 1]) cylinder(d = m3_d, h = lower + 2);
    translate([0, grip_depth / 2, -lower - 0.01]) cylinder(d = m3_nut / cos(30), h = 2.5, $fn = 6);
    for (p = board_holes)
        translate([p[0], grip_depth / 2 + p[1], gap]) cylinder(d = hole_d, h = jaw + standoff + 1);
}
