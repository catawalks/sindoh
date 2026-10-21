# Stock DP200 routines (decoded 2026-10-18)

How the stock firmware loads and unloads filament, cleans the nozzle and
uses the levelling sensor. Klipper equivalents are in
`klipper/config/dp200_macros.cfg`.

Sources:
- main program functions `engine_filaUnload`, `engine_filaLoad`,
  `engine_Cleaning_withoutObject`, `engine_cleaningXYMove`,
  `engine_changelvsensor*` and `engine_initLevelCheck`;
- FM microcode, emulated with the real parameter blocks (`tools/fmseq.py`);
- `app/nvram/karas.db`.

## Parameter source

- `db_get_var()` reads **row `NO=4`** of every `CONF_*` table
  (`SELECT col FROM table WHERE NO=4`). Rows 1–3 are older defaults.
- `engine_loadDBValue()` copies the columns into globals. Two contiguous
  runs of those globals are written into DTCM for the FM core:
  - `UpcSetInsertParam` writes globals **0x36187c**.. (0x74 bytes) to DTCM **0x93f0**;
  - `UpcSetRejectParam` writes globals **0x3618f0**.. (0xa4 bytes) to DTCM **0x9464**.

  The bases were derived from how the FM code uses the fields, and verified
  by emulation.
- `tools/stockparams.py` prints every column with its global address.

## Units

- Positions: engine pulses (X/Y 80 per mm, Z 3200, E 458.83).
- Speeds ("SPD"): stepper-engine half-period in **198.01 MHz** ticks. The
  stock code itself prints mm/s = 198010000 / (2·SPD·steps_per_mm).
  The engine clock is half of the UPC Timer1 (396 MHz).
- Engine status: `+0x64` bit 8 = busy, `+0x88` bit 8 = done.

| SPD | E mm/s | X/Y mm/s |
|---|---|---|
| 5394 | 40.0 | |
| 8631 | 25.0 | |
| 21579 | 10.0 | |
| 71951 | 3.0 | |
| 15469 | | 80.0 |
| 123756 | | 10.0 |

## Unload (`engine_filaUnload` + FM cmd 0x13; 0x2d when the cartridge is under 30 %)

1. Clean the nozzle first if `retractionStatus != 2`. Fans to their print defaults.
2. Clutch off. Park at X 229.0 / Y 0 / Z 23.1 (101_02). Heat to 230 °C PLA /
   250 °C ABS and wait for ≥ 210 / 230 °C.
3. FM 0x13: clutch on (dec_pwm block 6 ctrl `0x5e`), then repeated 4 mm
   retracts (E DIR 1). The first 50 mm (103_04_PRE_PULSE) run at 10 mm/s
   (PRE_SPD), the rest at 25 mm/s (103_04_SPD). It stops when:
   - the filament sensor (xena46) has read *empty* for 50 mm (offset +0x80), or
   - the filament encoder has not moved for 180 mm (+0x84; the under-30 %
     variant uses +0x94/+0x98).

   It fails with status 0x1a6 ("UNLOAD FAIL", error 422) after 420 mm
   (SC422_thresPULSE). Clutch off (`0x5a`).
4. Reset the filament encoder.

## Load (`engine_filaLoad` + FM cmds 0x0f, 0x10/0x2c, 0x11)

1. Home Z (optional), Y (RodinH only) and X. Park at X 229.0 / Y 0 / Z 23.1 (001_3).
2. FM 0x0f Insert_1: clutch on, feed (E DIR 0) at 40 mm/s one step at a
   time. Once the filament sensor reports *present*, stop as soon as the
   filament **encoder** has moved 3–4 counts (the filament has reached the
   extruder). Clutch off. Fails with error 411 after 1000 mm, or 412.
3. Wait for temperature (threshold × 1000 m°C).
4. FM 0x10 Insert_1_5: feed 42.5 mm at 3.0 mm/s (purge). The 0x2c variant
   uses 003_02_PULSE_ALTER = 50.5 mm.
5. Wait 1000 ms (003_3_DELAY).
6. FM 0x11 Insert_2: clutch on, retract 15 mm at 40 mm/s, clutch off.
7. Wait 3 s (003_5_DELAY).

## Nozzle cleaning / purge bin (`engine_Cleaning_withoutObject`, `engine_cleaningXYMove`)

1. Home Z, then Z 10.0 mm (CleaningPositionZ 32000); Y 5.5 mm (0x1b8 pulses).
2. Home X, then X 231.2 mm (PositionX1 18496), over the bin.
3. Heat and wait; purge 20 mm at 10 mm/s; retract 15 mm at 40 mm/s; wait 3 s.
4. `trashCanCount` += 1 (20 for a colour change). The user is asked to empty
   the bin after 15.
5. Wipe twice: X 209.0 ↔ 231.2 mm at 80 mm/s ("Warigari"; skipped on RodinH).

## LV levelling sensor

- State: `dec_sensor` (0xf9301000) **+0x210 bit 8**, copied by the IO core
  to status +0x18. Klipper pin: `dsens8`.
- The block is initialised by the stock IO firmware: +0x70..0x8c encoder
  channel configs, +0x200 = 0x180. `+0x204` is probably the filament
  encoder count (TBC).
- **Probe** (FM cmd 0x2a): step Z one step at a time until bit 8 = 1, up to
  a parameter limit, then return the step count.
- **Deploy/stow toggle** (`engine_changelvsensor`):
  1. X → X_lvModeSet_1 = −10 mm;
  2. relative move to X_lvModeSet_2 = −20 mm at 10 mm/s with no limit check
     (pushes a lever);
  3. back out to X2_lvPos = −5.6 mm.

  It retries up to 3 times until bit 8 flips; failure is error 0x137.
- Levelling points (X, Y mm): (82.1, 200.0), (−5.6, 34.9), (169.8, 34.9),
  (169.8, 200.0). Z check −10 mm (fast −7.5 mm); tolerance 0.1 mm
  (ZErrorRange 320); bed-down 0.12 mm.

## Other stock settings (row 4)

- **Heater PI:** nozzle P 20 / I 240 (max 1000); bed P 80 / I 40.
- **Motor-current offsets:** X −15, Y +20, Z +30, E +50, C +10.
- **Fans:** nozzle-fan print 100 %, cooling print 100 %, `FAN_EX` 50 %
  (dec_pwm block 3 was left at 50 %, though nothing is connected to it).
  LED1/LED2 PWM 100 % with 300 s timeouts.
- **SPMODE:** `ifBedNotUsed = 1`, `ifNotUseNozzleFan = 1` (meaning TBC).
- **FILACHECK:** run-out detection needs a minimum of 20000 steps and 2 encoder counts.
