# Touch controller (ROHM BU21029GUL): mainline bu21029_ts vs vendor rohm_ts

For the user's OK before the mainline touchscreen driver is enabled. Today
`m1-full` only sets the touch pins at boot (approved, touch-pins test):
- GPIO 67 high: the reset/enable line;
- GPIO 66 an input: the interrupt;
- both pin selects at their stock values.

The chip answers at I2C bus 2, address 0x40. No touchscreen driver is
built, so nothing is written to the chip yet.

Every BU21029 access is a command byte = register address << 3 (bit 7 =
"command"), followed by a data byte for writes.

## What each driver writes

| Reg (addr) | Cmd byte | Reset value | vendor rohm_ts (stock 3.2, probe) | mainline bu21029_ts (input open) |
|---|---|---|---|---|
| CFR0 (0x00) | 0x00 | 0x20 | **0x20** (CALIB = 1: use the calibration) | 0x00 |
| CFR1 (0x01) | 0x08 | 0xa6 | 0xa6 | 0xa6 |
| CFR2 (0x02) | 0x10 | 0x04 | **0x59** | 0xc9 |
| 0x03 | 0x18 | ? | **0xad** (calibration X?) | not written |
| 0x04 | 0x20 | ? | **0x74** (calibration Y?) | not written |
| 0x05 | 0x28 | ? | **0x50** | not written |
| 0x09 | 0x48 | ? | **0x0f** | not written |
| 0x0a | 0x50 | ? | **0x0f** | not written |
| CFR3 (0x0b) | 0x58 | 0x72 | 0x72 (the reset value) | 0x42 (PU90K off, dual touch off) |
| LDO (0x0c) | 0x60 | 0x00 | 0x00 | 0x77 (PVDD/AVDD 2.0 V) |
| 0x15 | 0xa8 | ? | **0x00** | not written |
| AUTOSCAN | 0x80 | - | write_byte_data(0x80, 0x00), after 5 delays | write_byte(0x80) |

The vendor also touches two GPIOs:
- GPIO 66 (gpio_request, then output 1, msleep, then input, msleep) before the first write, then requests its IRQ on it;
- GPIO 67 (the reset), which board code already drives high.

Mainline reads the HW ID first (0x0229 at command 0x70) and refuses other chips. It also drives an optional `reset-gpios` and a `vdd` regulator.

## Differences that matter

1. **LDO 0x77 vs 0x00:** mainline sets the panel and analog regulators to
   2.0 V. Stock leaves the register at reset, with the regulators off,
   probably because the board supplies those rails. Writing it changes a
   power setting of the touch panel's supply, so it needs the user's OK.
   To match stock, the mainline driver would need a patch keeping LDO at
   0x00.
2. **Calibration:** stock writes calibration-looking registers (0x03-0x05,
   0x09, 0x0a, 0x15) and sets CFR0 CALIB. Mainline doesn't, so its
   coordinates will be raw (12-bit). The X/Y ranges stock uses are
   0xbe..0xf5a and 0x186..0xe7e (rohm_ts input_set_abs_params). They can be
   set in the DT as `touchscreen-min-x`/`-size-x` and so on, or the
   vendor's calibration registers can be written.
3. **CFR2 (timing) and CFR3 (pull-up):** they differ in value, but only
   change scan timing and detection sensitivity.

## Also needed: an interrupt

bu21029_ts requires an IRQ; the vendor uses GPIO 66's interrupt (IRQ 275).
Our gpio-mv61x0 has no interrupt support yet. The vendor GPIO banks have
interrupts 38-45 (one per bank), so bank 2 is IRQ 40, GIC SPI 8. The
registers must be reversed from gogin_gpio_* before that works: a read-only
study, no hardware writes.

## Proposal

Option A (recommended): a small mainline patch so that bu21029_ts writes
exactly the stock values and leaves LDO at 0x00, plus GPIO interrupt support
for bank 2. Each piece comes for the user's OK before the first boot that
loads it.
