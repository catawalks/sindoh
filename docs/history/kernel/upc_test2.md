# UPC test 2 (2026-10-29): passive probe firmware under mainline

m1-upc (d6733179), through the Ethernet fast path. The user approved it and watched.
Firmware: /lib/firmware/upc/probe_io.bin (96cddffd) and probe_fm.bin (1ec429d5),
the same images that ran under stock on 2026-10-17. No heat and no motion.

| Check | Result |
|---|---|
| `upctool load` | "cores started"; both cores print "[UPC probe] ... core alive" and step tokens on ttyS0 |
| Heartbeat | FM ~913,000 loops/s, IO ~954,000 loops/s; thumb OK, aborts 0 |
| CP15 ID | FM 0x56051012, IO 0x56151012 |
| Free-running counter | 0x1e1e0001 counting up at 395,999,559 Hz (0x08001144 counts down at the same rate) |
| ADC (IO core) | sel 0 (nozzle) raw ~982, sel 1 (bed) raw ~828, steady to ±1. Under stock, the same probe read nozzle ~973 and bed ~771 while cooling, so these are plausible room-temperature values |
| Outputs while running | CPUSoftReset 1, no PWM block 1-32 with run/level set, all stepper CFG bit 0 = 1 (drivers off) |
| **Inputs** | **XIRD = 0, XIRD1 = 0 (seen-high 0) on both cores, even with the Y endstop held by hand. Under stock, XIRD reads 0x10140000 at rest and the endstop bits are live (xena42/43/44, filament xena46).** The XENA input path isn't set up under mainline yet (a pin mux or clock is likely missing). To investigate before Klipper homing |
| `upctool stop` | CPUSoftReset 0, heartbeats 0/s, outputs still off |
| `reboot -f` while running | "mv61x0-upc f9200000.upc: reboot: cores held, outputs off", then the reset |
| sysrq panic while running | "mv61x0-upc: panic: cores held, outputs off", "Rebooting in 10 seconds..", reset to stock on its own |

Every safety path works with firmware running. One gap remains before Klipper
can home under mainline: the endstop and filament inputs read 0.

## Test 2b (2026-10-29): bank-4 input pins at stock values, still no inputs

The user approved the 13 bank-4 writes from xena-pinmux.sh.proposed (GPIO 129-131 and 138-147
select = 0x00000000), applied by hand with the probe firmware running. They read
back 0x00000000 (dir is still 0x10000000). XIRD and XIRD1 still read 0 on both
cores (seen-high 0). Not the cause.

Next hypothesis: under stock, the probe ran after Sindoh's UPC firmware, which
probably configured the XENA input sampler, so the probe inherited that state.
Under mainline nothing has ever run on the cores before the probe. To check,
compare a read-only dump of the XENA register block under stock (with
upc.ko and its firmware running) and under mainline, and find the stock firmware
code that writes it.

## XENA dump on stock (2026-10-29, read-only)

Stock 3.2 from the 2 GB card: no Sindoh app, upc.ko loaded, CPUSoftReset = 0
(cores held, no Sindoh firmware running). XIIC[0..63] = 0 and XIRW = 0, but
XIRD = 0x3C040000 and XIRD1 = 0x00004000 (xena46 filament = 1, empty). So the
inputs are live with no firmware init at all: the firmware-init hypothesis
(xena-init.sh.proposed) is refuted. The gap is on the Linux side; the stock pin
functions on banks 4/5 are the main suspect. Raw dump: xena_dump_stock.txt.

## Test 2c (2026-10-29): endstop inputs fixed with 5 pad functions

Pad map (read-only, cores held, the user blocking the optical sensors; GPIO
bank 5 input register 0xf8045000): X sensor = bank 5 pin 20, Y = pin 21
(both 0 -> 1 when blocked), cartridge sensor = pin 23 (1 -> 0 when lifted).
Pin 22 is almost certainly Z (couldn't be reached past the bed). The bank 1/2
bits flicker constantly from Ethernet/LCD traffic.

The user approved: bank 5 pins 20-24 select 0x000C1000 -> 0x00001003 (the stock function 3),
written only after the safety check (CPUSoftReset 0, PWM run/level 0, stepper
CFG bit 0 = 1), and the check passed again afterwards. Direction register untouched
(0x80000000).

Result, with the cores held and no firmware: XIRD1 = 0x00004000 at rest (= stock).
X blocked -> 0x00004400 (bit 10, xena42), Y blocked -> 0x00004800 (bit 11,
xena43), cartridge lifted -> 0x00000000 (bit 14, xena46). These match the stock
mapping in docs/hardware_notes.md. XIRD stays 0 (stock 0x3c040000: other
inputs on other pads, not needed for homing).

Next: make these 5 writes part of the m1-upc boot (driver or init script),
check the Z pad when the bed is out of the way, and then decide on the
remaining stock pad functions one group at a time.
