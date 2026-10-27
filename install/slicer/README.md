# Slicer profiles for the DP200 with Klipper

All profiles describe the same machine:

- **Bed:** 210 × 201 mm, origin at the front-left (Klipper X 0 / Y 0, about
  2 mm in from the plate's front and left edges). Y can't reach the last
  ~4 mm at the back of the 216 × 209 mm plate.
- **Back-corner cut-outs:** the plate has 4 × 11 mm notches at both back
  corners (the old levelling touch points). They're left out of the bed as
  4 × 8 mm areas at X 0–4 and 206–210, Y 193–201.
- **Height:** 190 mm.
- **Start G-code:** `PRINT_START BED=… EXTRUDER=…` then `PRIME_LINE`.
  PRINT_START heats, homes, meshes, purges and wipes; the slicer must not
  send its own heating commands.
- **End G-code:** `PRINT_END`.
- **Extrusion:** relative (M83), 4 mm retraction at 35 mm/s on the long
  bowden. Retraction and pressure advance are first guesses.
- **Starting point:** a 0.20 mm PLA process (210 °C first layer, 205 °C,
  bed 60 °C).

Bed size and cut-outs are from a measurement on 2026-10-27, accurate to
about ±1 mm.

## PrusaSlicer and SuperSlicer

`DP200_Klipper_PrusaSlicer.ini`: **File → Import → Import Config Bundle**.
It adds the printer "Sindoh DP200 Klipper", the print profile "DP200 0.20mm
Klipper" and the filament "DP200 PLA". The cut-outs are part of the bed
shape. Objects are labelled for Klipper's exclude-object (cancel one
object in Mainsail).

## OrcaSlicer

The three files in `orca/`: **File → Import → Import Configs…** and select
all three. Import the printer first if Orca asks; the process and filament
are tied to "Sindoh DP200 Klipper 0.4 nozzle". The cut-outs are part of the
printable area, and exclude-object labels are on.

## Cura

Cura has no import for printers; copy the definition files into Cura's
configuration folder (Help → Show Configuration Folder), then restart
Cura:

- `cura/definitions/sindoh_dp200_klipper.def.json` → `definitions/`
- `cura/extruders/sindoh_dp200_klipper_extruder_0.def.json` → `extruders/`

Then **Preferences → Printers → Add → Non-networked → Sindoh → Sindoh DP200
(Klipper)** and choose Generic PLA. The cut-outs are disallowed areas (grey
on the build plate). **Check once that they show at the back corners**;
if they're at the front, change the sign of the second number of every
point in `machine_disallowed_areas`. Cura doesn't label objects for
exclude-object.

## Other slicers

- **SuperSlicer:** use the PrusaSlicer bundle (same format).
- **Bambu Studio:** imports OrcaSlicer's JSON, but it is made for Bambu
  printers. Prefer OrcaSlicer.
- **Simplify3D, IdeaMaker and others:** set the values above by hand.
  Use the start and end G-code as given, and turn off the slicer's own
  temperature commands at the start.
