# JTAG on CN3 with the JTAGulator: preparation

Goal: find where the boot ROM stops when it tries to boot from SD in mode 6
(docs/sd_boot_plan.md), and learn the 88PA6170's debug access.

## What's ready

- **JTAGulator** on the PC's **COM4**, firmware **1.12**. Menus checked:
  JTAG (J), UART (U), GPIO (G), SWD (S). The JTAG menu has the combined,
  IDCODE and BYPASS scans, RTCK, device IDs, IR/DR discovery, pin mapper
  and an **OpenOCD interface (O)**.
- `tools/jtagulator.py`: send menu commands from scripts and print the
  replies. For example `python tools/jtagulator.py --port COM4 J H`, or with
  no commands for an interactive session.
- **OpenOCD 0.12 (xPack, Windows)** in `D:\DP200\backup\tools_ext\openocd\`.
  Its Windows build has **no Bus Pirate driver**, which the JTAGulator's
  OpenOCD mode needs, so OpenOCD has to run on Linux to drive it: WSL (not
  installed on this PC) or any Linux box with `apt install openocd`.
- JTAGulator source, for reference: `D:\DP200\backup\tools_ext\jtagulator_src\`.

## Wiring (printer OFF while connecting)

CN3 is a 2×10 header labelled JTAG, probably the standard ARM 20-pin
layout:

| Pin | ARM-20 signal | Pin | Signal |
|---|---|---|---|
| 1 | VTref (I/O voltage) | 2 | NC / Vsupply |
| 3 | nTRST | 4 | GND |
| 5 | TDI | 6 | GND |
| 7 | TMS | 8 | GND |
| 9 | TCK | 10 | GND |
| 11 | RTCK | 12 | GND |
| 13 | TDO | 14 | GND |
| 15 | nSRST | 16 | GND |
| 17, 19 | NC | 18, 20 | GND |

1. Before connecting anything, with the printer on, **measure pin 1 against
   a GND pin** (and check that pins 4–20 even are ground). Expect 3.3 V or
   1.8 V. The JTAGulator's V setting must match it.
2. Printer off. Connect JTAGulator **GND → pin 4**, then channels
   **CH0 → pin 3, CH1 → 5, CH2 → 7, CH3 → 9, CH4 → 11, CH5 → 13,
   CH6 → 15**. Leave pin 1 unconnected to the channels.

## First session (no OpenOCD needed)

1. Printer on (normal NAND boot is fine for the first scan).
2. `python tools/jtagulator.py --port COM4`, then:
   - `V`, then the measured voltage (e.g. 3.3);
   - `J`, `I`: IDCODE scan, channels 0–6. It reports TDO/TCK/TMS and the
     IDCODE(s);
   - `B`: BYPASS scan, to also find TDI (and the number of devices);
   - `D`: device IDs with the found pinout.
3. Record the pinout and IDCODEs here. The expected chain: Marvell PJ4B-MP
   (ARMv7) cores behind an ARM debug port. The IDCODE tells which OpenOCD
   target config to start from.
4. Then repeat with the DIP switches on SD (mode 6) and 2GB-SD inserted.
   The ROM hangs there; with OpenOCD (on Linux, via the JTAGulator's O mode
   and `interface/buspirate.cfg`) halt the core and read the PC. Compare it
   with the ROM dump (`D:\DP200\backup\bootrom\rom_f9f00000.bin`, base
   0xF9F00000) to see which SD init step it is stuck in.
