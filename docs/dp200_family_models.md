# DP200 family: how Sindoh's firmware tells the models apart

Read 2026-11-24 from Sindoh's `RODIN_200730_2` update (the DP200's and
DP201's firmware, byte for byte the same): the motion program
`marvell_lspsdk_3dp_gemstone-debug_stripped.elf` (disassembled, never
run) and `/app/karas_pinetree_util.sh`. Nothing was run on a printer.
The owner's facts about the DP201 are in [other_models.md](other_models.md).

## The model ID

Every printer carries its model ID ("TLI") in the settings database:

```sh
sqlite3 /app/nvram/karas.db 'select MachineTLI from INST_MACHINE'
```

The suffix is the market (K Korea, J Japan, A Americas, C/CM China, none
Europe) and the option: **Q** is the open-filament model (the "Q"
conversion), **H** another variant. The test DP200 reads `3DP200Q`.

## The families: `engine_getMachineModel`

At start-up the motion program turns the ID into a 32-bit model code and
keeps it at the start of its machine settings. The high byte is the
family:

| Model code | Family (Sindoh's name) | Model IDs |
|---|---|---|
| `0x01000100` | **Rodin P**: DP200, DP102 | `3DP200` `3DP102` `3DP200K` `3DP200A` `3DP200CM` `3DP200J` `3DP200Q` `3DP102Q` `3DP200KQ` `3DP200AQ` `3DP200CMQ` `3DP200JQ` `3DP200H` `3DP200CMH` `3DP200JH` `3DP200KH` |
| `0x01000200` | Rodin P, China (ESUN) | `3DP200C` `3DP200CQ` |
| `0x01000400` | Rodin P, Stanley Model 1 | `ST3DP1` `ST3DP1Q` |
| `0x01000800` | Rodin P, Leon 3D (Spain) | `LEON3D` `LEON3DQ` |
| `0x02000100` | **Rodin E**: DP201, DP202 | `3DP201` `3DP201K` `3DP201A` `3DP201CM` `3DP202` `3DP201J` `3DP201Q` `3DP201KQ` `3DP201AQ` `3DP201CMQ` `3DP202Q` `3DP201JQ` `ORAL3DQ`; any ID starting `RDPL` or `3DPL` |
| `0x02000200` | Rodin E, China | `3DP201C` `3DP201CQ` |
| `0x80000100` | **Rodin EH**: DP203 (Korea) | `3DP203KQ` |
| `0x02000100` | **any other ID** ("Unknown TLI!!! Set to Default!!!") | |

Bit tests in the program: `engine_ifRodinE` = bit 25 (`0x02000000`);
`engine_ifRodinEH` = bit 31 (`0x80000000`, the DP203 only);
`engine_ifRodinYangpan` bit 26; `engine_ifRodinU` bit 27 (the 3DWOX 1's
`RODIN_SUB=U`). The 3DWOX 1 IDs (`3D1...`), `3DP101`, `3DP103` and
`3DF1ECOKQ` appear in `karas_pinetree_util.sh` (region and time zone)
but not in this table: those printers run other firmware lines.

## What the program does differently on a Rodin E (DP201)

Unit conversions are ours (X/Y 80 steps/mm, Z 3200 steps/mm, as on the
DP200).

- **No heated bed:** at every start it sets
  `CONF_ENGINE_SPMODE.ifBedNotUsed = 1` (a column it adds with default
  0), except on `3DP203KQ`. So a DP201's database says so itself.
- **Nozzle fan:** `CONF_ENGINE_SPMODE.ifNotUseNozzleFan = 1`;
  `CONF_ENGINE_PWM.FAN_COOLING_PRINT = 100`; the cooling-fan routines
  test the family bit too.
- **Z travel 6 mm shorter:** Z max 194.6 mm (623,744 steps) against the
  DP200's 200.6 mm (641,920); the Z "bottom" position 192.1 mm (614,720)
  against 198.42 mm (634,944); the print file height limit 189 mm
  against 195 mm.
- **Leveling points** (stock frame): X 82.1, -5.6, 169.8, 169.8 mm and
  Y 200, 34.9, 34.9, 200 mm; `L_bedDown` 384 steps (0.12 mm),
  `Z_lvFastCheck` -24,000 steps (-7.5 mm), `Z1_lvPos` 19,520 steps.
- Also its own: filament unload temperatures, automatic filament
  retraction, XY jerk, extruder heater PID gains, the pause/resume
  distance, nozzle cleaning moves, resume and photo positions, and the
  factory jig ("[JIG] this machine is Rodin-E").
- A Rodin P keeps its defaults ("(INIT) This machine is RODIN-P, No
  Adjust.").
- Naming in the log: the DP201 branch prints "This machine is RODIN-L",
  the DP203's "RODIN-EH".

## The DP203 ("Rodin EH", `3DP203KQ`)

Korea only. Read from the same program, the DP203 is the DP201's head
and frame with the DP200's bed and leveling:

| | DP200 (P) | DP201 (E) | DP203 (EH) |
|---|---|---|---|
| Heated bed | yes | no (`ifBedNotUsed = 1`) | **yes** (the flag is not set, and the DP201 branch skips it for `3DP203KQ` by name) |
| Z max, Z bottom, print height | 200.6, 198.42, 195 mm | 194.6, 192.1, 189 mm | **as the DP201** (every "E or EH" test) |
| Nozzle fan flag, print fan 100, unload temperatures, filament retraction, jerk, nozzle heater gains, pause/resume distance | stock defaults | DP201 values | **the DP201 values** |
| Nozzle cleaning moves, resume, ready and photo positions, deceleration | | own | **as the DP201** |
| Leveling | 3 points, Z corrected in software | 4 points, turns of the two screws shown | **as the DP200** (the DP201's leveling points and routine are tested on bit 25 only) |
| Cooling-fan routines, factory jig | | own | as the DP200 (bit 25 only) |

Both leveling routines switch the same level sensor between print and
level mode, so all three models have the touch sensor (`(LEVEL) Sensor
is PrintMode` / `LevelMode`).

## For the Klipper port

- The installer can tell the families apart by `MachineTLI` with the
  table above; `ifBedNotUsed` is a second check on a DP201.
- A DP201 config needs: no `heater_bed` (and no bed heating in the
  print start and the screen), Z about 6 mm shorter, its own leveling
  points, and a check of the nozzle fan.
