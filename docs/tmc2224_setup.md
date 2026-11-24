# TMC2224 driver set-up in Sindoh's motion programs

Read 2026-11-24 from the motion programs (disassembled on the PC, never
run): the 3DWOX 1's (`RODUP_220111_1`), the owner's 1X copy, the 2X's and
the 7X's. Nothing was sent to a driver.

## Which printers have which drivers

- **DP200 line:** Allegro A4982 only. The program carries the TMC2224
  functions (shared source) but none of the select pins or the board
  check, so nothing calls them on a DP200.
- **3DWOX 1:** two boards. At start-up the program reads the
  board-select pin `gp_pcb_select` (GPIO bank 2 pin 0). Read 1: "New
  Board (Trinamic)!!!", TMC2224 drivers, set up as below, and all five
  motor current offsets set to 99. Read 0: the A4982 board (no set-up;
  the database offsets as stored) and the model code gets bit
  `0x00800000` ("Machine Revision").
- **1X, 2X, 7X:** TMC2224 drivers (no board check), set up as below.
- **No other driver chip** appears in any program we have: no TMC2208,
  2209, 2130, 5160, DRV88xx or other Allegro part.

The A4982 needs nothing written: its current is the VREF pin (the
filtered PWM the Klipper port already drives) and its microsteps are the
MS pins.

## The link

- **Port:** Linux `/dev/ttyS2`, 115200 baud, 8N1, raw (`c_iflag`
  IGNPAR, `c_cflag` B115200 | CS8 | CREAD | CLOCAL, `VMIN` 1).
  **(our note)** On the DP200 board `ttyS2` is the power-management MCU's
  link at 9600 (sindoh-klipper `docs/hardware_notes.md`); on the TMC
  boards the same port carries the driver bus. Each board wires it its own way.
- **Which driver:** a decoder (enable `gp_motor_dec_en` /
  `gp_motor_decoder`) and three select lines put one driver's PDN_UART
  pin on the port. `UART_motorSelect(n)`: decoder enable 1, short wait,
  enable 0, then the select lines to n (select_0 = bit 0, select_1 =
  bit 1, select_2 = bit 2).

  | | Enable | select_0 | select_1 | select_2 |
  |---|---|---|---|---|
  | 3DWOX 1 | bank 3 pin 23 | bank 3 pin 29 | bank 3 pin 30 | bank 3 pin 31 |
  | 1X (Linux GPIO numbers, [1x.md](1x.md)) | 152 | 146 | 147 | 149 |

- **Write datagram** (`tmc2224_writeRegister`): the TMC22xx UART format,
  8 bytes: `05` (sync), `00` (slave address), register | `0x80`, the
  32-bit value high byte first, CRC8 (`swuart_calcCRC`, TMC's CRC over
  the first 7 bytes). The program then reads the 8 echoed bytes back
  (single-wire bus).
- **Read** (`tmc2224_readRegister`): the same, without data and the
  `0x80` bit; the driver answers with 8 bytes. The debug commands
  `settrinamic [motor] [reg] [data]` and `gettrinamic [motor] [reg]` use
  these.

## What it writes, per driver (`engine_motor_config`)

| Register | 3DWOX 1 (drivers 0-3) | 1X (drivers 0-7) | Meaning (TMC2224 datasheet; our reading) |
|---|---|---|---|
| `0x00` GCONF | `0x141` on all | `0x145` on drivers 4 and 5, `0x141` on the rest | `I_scale_analog` (VREF sets the current scale), `pdn_disable` (UART on the PDN pin), `multistep_filt`; `0x145` adds `en_spreadCycle` |
| `0x10` IHOLD_IRUN | `0x1F1F` | `0x1F1F` | run and hold current at 31/31 (full scale of VREF), IHOLDDELAY 0 |
| `0x70` PWMCONF | `0xC80C0E24` | `0xC80C0E24` | StealthChop: PWM_OFS 36, PWM_GRAD 14, autoscale and autograd on, PWM_REG 8, PWM_LIM 12 |
| `0x13` TPWMTHRS | 38, 38, 47, 75 | 44, 44, 44, 58, 75, 75, 75, 75 | StealthChop to SpreadCycle switch speed |

Not written: CHOPCONF (GCONF's `mstep_reg_select` is 0, so the
microsteps come from the MS pins, which the program sets) and the
current itself (VREF, from the motor current PWM and the database
offsets).

On the 1X, driver 3 is Z: `engine_motor_z_TPWMTHRS` re-selects driver 3
and writes TPWMTHRS 58 again. Which driver is which motor otherwise
(drivers 4 and 5 in SpreadCycle look like the two extruders) is our
reading, not checked.

## For the Klipper port

- **Klipper started after the stock program** (the 1X today, the warm
  takeover): the drivers are already set up; nothing to do.
- **Klipper started without it** (the DP200-style NAND install on a
  3DWOX 1 TMC board, the 1X cold start): the drivers stay at their
  power-on defaults (no `pdn_disable`, `I_scale_analog` as the OTP
  sets it, StealthChop thresholds unset). A start-up tool has to write
  the four registers to each driver before Klipper runs: select pins
  by sysfs GPIO, the datagrams above on `/dev/ttyS2`, the echo checked,
  then a read of IFCNT (`0x02`) to confirm each write counted.
- On a 3DWOX 1, read the board-select pin first: write nothing on an
  A4982 board.
