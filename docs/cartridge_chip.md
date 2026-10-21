# DP200 filament cartridge chip

Status 2026-10-21: chip identified and fully read (read-only) from one
**empty** cartridge. The field meanings below are hypotheses; a second
cartridge (full, or another colour or material) will confirm them.

## Hardware path

```
/dev/i2c-3 (DesignWare I²C, kernel name "Smart-IC" at 3-0030)
  -> DS2465 (I²C 7-bit address 0x18): 1-Wire master + SHA-256 coprocessor,
     holds Sindoh's master secret in its protected EEPROM
  -> pogo pins in the cartridge bay
  -> DS28E22 in the cartridge (1-Wire, OVERDRIVE SPEED ONLY)
```

- **Overdrive only.** A standard-speed reset gives "short detected"
  (the chip's early presence pulse lands on the bridge's 8 µs short
  sample). Put the bridge in overdrive first: device configuration 67h,
  low nibble 1WS|APU = 0x9.
- **Release latch** = the solenoid, dec_pwm block 8 (`[output_pin solenoid]`).
  A 4 s pulse lets the cartridge be pulled out; 1.5 s is too short.
- The cartridge lever sensor (`!xena46`) reads "not detected" with this
  cartridge inserted.
- Reader tool: `tools/cartridge_probe.py --addr 0x18 --od --apu --dump`
  (read-only).

## Chip contents (empty cartridge, 2026-10-21)

ROM `48 9d 6a 29 00 00 00 82`: family 0x48 = **DS28E22**, serial
000000296a9d. Personality PB1=02 PB2=03, manufacturer ID 008a.

| Block (pages) | Status | Meaning |
|---|---|---|
| 0 (0–1) | 10 | authenticated writes only |
| 1 (2–3) | 12 | authenticated writes only |
| 2 (4–5) | 14 | authenticated writes only |
| 3 (6–7) | 36 | authenticated writes + **EPROM mode** (bits only 1 → 0) |

No page is read-protected.

```
page 0: 33 44 50 32 30 30 50 42 4c 2d 52 51 62 99 77 6b 01 00 00 00 05 ff 6d 15 01 00 00 00 e8 00 00 00  |3DP200PBL-RQb.wk......m.........|
page 1: 00 x 32
page 2: 00 00 00 00 df 61 01 00 00 ...
page 3: 0a 00 00 00 0a 00 00 00 07 00 00 00 06 00 00 00 24 00 00 00 19 00 00 00 00 00 00 00 00 00 00 00
page 4: 00 x 32
page 5: 00 x 32
page 6: 00 ff ff ... ff
page 7: ff x 32
```

## Decoded from the stock app (2026-10-21, tools/elfdis.py)

How the stock app (`marvell_lspsdk_3dp_gemstone-debug_stripped.elf`, symbols in .dynsym) uses the chip:

- **Startup** (`init_smart_ic` → static helper 0x17c824):
  1. `DS2465_detect`;
  2. sets the bridge's 1-Wire timings (`OWConfigureTMSP`, `TW0L`, `TREC0`,
     `TW1L_Overdrive`), then `OWPowerUp` and `OWSpeed` (overdrive);
  3. `OWReadROM`, `CalculateNextSecret256`, `ReadStatus`.

  Page reads go through **`readAuthVerify`**: each page is read with a
  DS2465-checked MAC, so the printer rejects data that didn't come from a
  chip holding the right secret.
- **Parsing:** helper 0x17c0a4 copies the raw memory (page 0 onwards,
  contiguous: page N = raw bytes N×32…) into the parsed structure at
  0x3d2514:

  | Raw bytes | Parsed field | This cartridge | Meaning (stock log strings) |
  |---|---|---|---|
  | p0 0–11 | +0x00 | `3DP200PBL-RQ` | product / material code |
  | p0 12–15 | +0x10 | 0x6b779962 | ? (date or lot) |
  | p0 16–19 | +0x14 | 1 | ? (material: 1 = PLA, per `MaterialChk 1:PLA 2:ABS`) |
  | p0 20–23 | +0x18 | 0x156dff05 | ? (colour?) |
  | p0 24–27 | +0x1c | 1 | ? |
  | p0 28–31 | +0x20 | **232** | **TotalFilament, metres** |
  | p2 0–3 | +0x24 | 0 | ? |
  | p2 4–7 | +0x28 | **90 591** | **Used ePulse** |
  | p2 8–11 | +0x7c | 0 | "Over Clk" |
  | p2 12–15 | +0x80 | 0 | "Over Clk" / ifFinished |
  | p3 0–23 | +0x2c…+0x40 | 10, 10, 7, 6, 36, 25 | six parameters (still unknown) |

- **Units:** `engine_showSmartICInfo` prints `Used ePulse: %d->%d mm` with
  mm = ePulse × 500 × 0.00217948. 0.00217948 = 1/458.83, the extruder's
  steps/mm, so **1 ePulse = 500 extruder steps = 1.0897 mm**. This
  cartridge: 90 591 ePulse ≈ **98.7 m used of 232 m** (≈ 42 %).
- **Derived fields:** `engine_calcFilament` derives used/remaining cm and
  percent, and the fuse count (+0x4c, "Fuse %dp <- 0x%04x") from the pages
  6–7 bitmap.
- **Writing back:** `write_smart_ic` / `inc_smart_ic` ("[SEC] %s-MemW
  Fail") do authenticated writes.

## Field hypotheses (before the disassembly)

Clues come from the stock app's (`marvell_lspsdk_3dp_gemstone-debug_stripped.elf`)
own log strings, listed after each hypothesis. Numbers are little-endian 32-bit.

| Where | Value | Hypothesis |
|---|---|---|
| page 0, 0–11 | `3DP200PBL-RQ` | product code: printer 3DP200, material/colour `PBL` (P = PLA? BL = black/blue?), `RQ` variant. Clue: `MaterialChk->%d (1:PLA, 2:ABS)` |
| page 0, 12–15 | 0x6b779962 (BE 0x6299776b = 2022-06-03) | production date or lot |
| page 0, 16–19 | 1 | ? (material code 1 = PLA?) |
| page 0, 20–23 | `05 ff 6d 15` | ? (colour? checksum?) |
| page 0, 24–27 | 1 | ? |
| page 0, 28–31 | **232** | **total filament in metres**. Clue: `(SMARTIC) TotalFilament: %d meter`. 232 m ≈ 690 g of 1.75 mm PLA |
| page 2, 4–7 | **90 591** | used length (mm = 90.6 m?) or remaining. Clues: `Used ePulse: %d->%d mm`, `Used %d cm / %dp`, `WriteDown Filament Length <- %d` |
| page 3 | 10, 10, 7, 6, 36, 25 | settings (temperatures/speeds/counters?) |
| pages 6–7 | 8 of 512 bits cleared | **"fuses"**: a one-way usage counter. Clues: `SmartIC FuseDiff. %d+%d<%d`, `SmartIC EmptyCheck:0x%04X` |

## Can it be rewritten?

- **Pages 0–5:** yes in principle, with an *authenticated* write. The MAC
  needs the chip's secret, which is derived from the master secret in the
  printer's DS2465. The DS2465 computes the MAC without ever revealing the
  secret (`DS2465_Compute_SSecret`, `DS2465_Compute_WriteMAC`, the same path
  the stock app uses). That needs the DS28E22 / DS2465 authentication
  protocol details, which are in the full (NDA) datasheets but also in
  Maxim's open-source MaximInterface (`gitlab.com/iabenz/MaximInterface`,
  DS28E15_22_25 + DS2465 classes).
- **Pages 6–7 (EPROM):** only more bits can be cleared; a burnt fuse can't
  be restored. If the stock firmware treats those fuses as the authoritative
  "used" counter, a refilled cartridge keeps its count there, and our
  firmware would track usage in pages 2/3 or on the printer instead.
- **Never write before the format is confirmed.** A wrong authenticated
  write is permanent if it lands in EPROM-mode pages.

## Klipper module (drafted 2026-10-21, NOT yet tested on the printer)

`klipper/extras/dp200_cartridge.py`, enabled with an empty `[dp200_cartridge]`
section:
- Reads ROM + pages 0, 2, 3, 6, 7 at start-up and on `CARTRIDGE_READ`
  (refused while printing). The read runs in a background thread, so the
  reactor is never blocked.
- Status: `printer["dp200_cartridge"]` → present, rom_id, product,
  material, total_m, used_m, remaining_m, remaining_percent, fuses_used,
  params, error.
- Read-only by construction: only Read ROM / Read Memory / Read Status are
  sent, and an assert guards the memory-function command.
- Access: `dp200-mounts.sh` now gives the chroot's /dev/i2c-3 to group
  klipper.

The decoding was checked offline against the dump above (232 m total,
98.72 m used, 8 fuses).

To test with the user: deploy the module and mounts helper, add
`[dp200_cartridge]`, restart, check the console message and Mainsail's
object view. The screen UI could then show it.

## Next steps

1. Read a second cartridge (full or partly used, other colour/material),
   then diff the fields.
2. Disassemble the stock app around `read_smart_ic`, `engine_showSmartICInfo`
   and `consumable_get_percent_remaining` (names are in the binary) for exact
   offsets and units.
3. Klipper integration, read-only first: a host module that reads the chip
   (via the DS2465 on /dev/i2c-3) when a cartridge is inserted, and exposes
   material, colour, total and used length to Mainsail and the touch screen.
