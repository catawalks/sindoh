#!/bin/sh
# Bed-camera pose sweep for the object-on-bed check (PROJECTS.md #4).
# Homes if needed, parks the head back-right, lamp on, then steps the bed
# down and saves one rotated snapshot per height into OUT.
# Usage: bed_pose_sweep.sh OUT_DIR [Z ...]   (default Z 10 30 50 ... 190)
# Runs on the PC; needs curl and Python with Pillow (PYTHONPATH).
H=${PRINTER:-http://10.10.0.21}
OUT=$1; shift
[ -n "$OUT" ] || { echo "usage: $0 OUT_DIR [Z ...]"; exit 1; }
ZS=${*:-10 30 50 70 90 110 130 150 170 190}
mkdir -p "$OUT"
gc() { curl -s -G --data-urlencode "script=$1" "$H/printer/gcode/script" >/dev/null; }
# Never home here: Z homes UPWARD to a switch ~2 mm above the bed, so
# anything on the bed is crushed against the top before the switch trips
# (2026-10-28: a 20 mm cube jammed, emergency stop). Home with an empty bed
# first, then put objects on it and run this.
homed=$(curl -s "$H/printer/objects/query?toolhead=homed_axes" | python -c "import json,sys;print(json.load(sys.stdin)['result']['status']['toolhead']['homed_axes'])")
[ "$homed" = xyz ] || { echo "not homed - home with an EMPTY bed first"; exit 1; }
gc "SET_PIN PIN=lamp VALUE=1"
gc "G90"
gc "G1 X226 Y201 F6000"
for z in $ZS; do
    gc "G1 Z$z F600"
    gc "M400"
    sleep 2
    curl -s -o "$OUT/z$z.jpg" "$H/webcam/?action=snapshot"
    python -c "import sys;from PIL import Image;p=sys.argv[1];Image.open(p).rotate(90,expand=True).save(p)" "$OUT/z$z.jpg"
    echo "z$z.jpg"
done
