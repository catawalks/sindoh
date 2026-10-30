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
