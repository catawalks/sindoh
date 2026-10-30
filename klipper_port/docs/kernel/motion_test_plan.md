# Motion test plan for mainline (for the user's approval, 2026-10-30)

Nothing here runs without the user present and their OK for each step. No heat
in any step.

## Where we start

- Motion already worked on the **stock** kernel (2026-10-17/18,
  docs/hardware_notes.md):
  - **Extruder:** 460 steps forward and back.
  - **Axes:** 2 mm moves on X, Y and Z at 4 mm/s.
  - **Homing:** Z homing stopped on its switch.
  - **Tools:** tools/ktest_motion.py, tools/ktest_xyz.py and tools/ktest_zhome.py, with Klipper firmware on the UPC cores and klippy talking over the TCP bridge.
- **Mainline today (m1-upc):**
  - The UPC driver holds the cores, forces the outputs off, and has proven reboot and panic paths (tests 1/2).
  - The XENA inputs work: X, Y and the cartridge lever (test 2c; bank 5 pins 20-24).
  - **No output pads are routed yet.** The stepper step/dir/enable pads and the PWM pads (heaters, fans, motor current REF) are still plain GPIO inputs, so mainline cannot move anything yet. The first step below changes that.

## Machine facts (docs/hardware_notes.md, klipper/config/dp200_printer.cfg)

| Axis | Engine | Steps/mm | DIR 0 / DIR 1 | Endstop | Home |
|---|---|---|---|---|---|
| X | smot 0 | 80 (16 x 200 / 40) | carriage left / right (+X) | xena42, XIRD1 bit 10, 1 = hit | MAX end (216), approach +X |
| Y | smot 1 | 80 | bed back / forward | xena43, bit 11, active-high | 5.5, approach -Y |
| Z | smot 2 | 3200 (rotation 1 mm) | bed up / bed down (+Z) | xena44, bit 12, active-high, at the TOP | bed moves UP to home |
| E | smot 3 | 458.83 | feed / retract | (cartridge lever xena46 = filament presence) | - |

- **Motor current:** the hardware PWM REF, dec_pwm block 0x1f at 75 % (what the stock app uses; proven under Klipper).
- **Drivers:** A4982. Driver enable = stepper CFG bit 0 cleared; bit 0 set = driver off.
- **Never home Z with anything on the bed.** Z homes upward and crushes whatever is on the plate.

## Steps (each needs the user's OK; a power-switch hand ready)

### M0. Route the output pads (new pin writes: needs its own approval)

`kernel/m1/initramfs/upc/upc-pinmux.sh.proposed`, stage `all`: the rest of
the stock UPC pad set. Exact stock values:
- bank 4 pins 24 and 26;
- bank 5 pins 0-3, 6-14, 16-19 and 25-31 (20-24 are already done);
- bank 6 pins 0 and 2-4.

The script writes nothing unless the cores are held, no PWM block has run or level set, and every stepper CFG has bit 0 set. It re-checks afterwards.

- **Expected:** nothing moves, nothing heats, the fans stay off. XIRD may come alive (stock reads 0x3c040000).
- **Check:** `sh /etc/m1-variant.sh` shows "PWM blocks ... none" and every stepper CFG with bit 0 set. `xena-dump` follows.
- **If anything moves or a fan spins:** power off. The pad map would then be wrong.
- **Later:** if accepted, move the writes into the driver probe like the input pads, with the same precondition.

### M1. Klipper firmware, no motion

1. Run `upctool load klipper_io.bin klipper_fm.bin`, the same prebuilt images as the stock-kernel runs.
2. Run `upctool bridge -f tcp:9100 -i tcp:9101` on the printer, over Ethernet.
3. On the PC, klippy with `dp200_printer.cfg`, heaters disabled (`max_power: 0` or no heater sections). Alternatively, tools/khost.py for identify only.

- **Checks:**
  - identify and get_config succeed;
  - clocks are about 396 MHz (FM) and 395 MHz (IO);
  - `QUERY_ENDSTOPS` follows hand presses on X and Y;
  - the cartridge lever follows.
- **Abort paths** (proven in test 2, repeated here once with Klipper running): `upctool stop`, `reboot -f`, the sysrq panic. Each must log "cores held, outputs off".

### M2. One tiny move per axis, no homing

Start with the carriage near the middle and the bed clear. In each move, the motor enables, moves, and the driver is disabled again afterwards (`M84`).

| Move | Command | Distance | Speed | Expect |
|---|---|---|---|---|
| E | `FORCE_MOVE STEPPER=extruder DISTANCE=1 VELOCITY=2`, then `-1` | 1 mm | 2 mm/s | the drive gear turns a little each way (no filament loaded) |
| X | `FORCE_MOVE STEPPER=stepper_x DISTANCE=-1 VELOCITY=2`, then `+1` | 1 mm | 2 mm/s | carriage 1 mm left, then back |
| Y | `FORCE_MOVE STEPPER=stepper_y DISTANCE=1 VELOCITY=2`, then `-1` | 1 mm | 2 mm/s | bed 1 mm, then back |
| Z | `FORCE_MOVE STEPPER=stepper_z DISTANCE=1 VELOCITY=1`, then `-1` | 1 mm | 1 mm/s | bed **down** 1 mm first (+Z = down), then back up |

- **Order:** E first (no load, nothing to hit), then X, then Y, then Z.
- **On a wrong direction, a noise or a stall:** stop (`M112` or `upctool stop`) and compare with the table above before going on.

### M3. Homing, one axis at a time

1. `G28 X` (to the MAX end, at 10 then 5 mm/s), then `G28 Y`.
2. **Z only with the bed visibly empty:** `G28 Z` (bed up to the top switch, at 5 then 2 mm/s).

- **Before each homing:** `QUERY_ENDSTOPS` reads "open" for that axis.
- **Expected:** each stops on its switch. Klipper's `homing_retract_dist` backs off afterwards.

### M4. Small moves in coordinates

Run `G1 X100 Y100 F1200`, then `G1 Z10 F300`, all inside the soft limits
(X -21..233.6, Y -1.75..201.5, Z -2..194).

## Out of scope for this plan

These are a separate plan with the user watching:
- heaters and fans;
- PID;
- printing.

The nozzle heater was proven on stock at a 30 % cap (hardware_notes.md).
