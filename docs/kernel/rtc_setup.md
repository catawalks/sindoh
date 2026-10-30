# RTC (gogin-rtc): read-only driver now, setup sequence as a proposal

Vendor driver: gogin_rtc_* in the 3.2 kernel. Resources:
- registers at 0xf8100000-0xf810002f;
- the APB configuration block at 0xf8000000-0xf80002ff;
- IRQ 64, which is GIC SPI 32.

## Registers (from gogin_rtc_read_time / set_time / rtc_setup_alarm)

| Offset | Use |
|---|---|
| +0x00 | control; the probe's setup ends by writing 3 |
| +0x0c | time: a seconds counter. Read for the time; written twice, 1 ms apart (udelay), to set it |
| +0x10 | alarm, in seconds (the alarm code loops until +0x0c is stable around the write) |
| +0x04, +0x08, +0x14, +0x1c, +0x20 | written by the probe (see below) |

## What mainline does now (rtc-mv61x0, in the `full` variant)

- **Reads:**
  - the probe logs the control word, and the counter twice, 2.1 s apart, to show whether it is counting;
  - `read_time` returns the counter as seconds since 1970.
- **Writes:** only the vendor setup below, and only with `marvell,vendor-setup` in the DT. No `set_time`, no alarm, no interrupt.
- **Time:** stock sets the clock to 1970 at every boot, so there is probably no backup battery, and NTP is the real time source.

## The vendor probe's setup (corrected 2026-10-30)

**Correction.** The first version of this list said +0x20 = 3. That was wrong:
the `3` in gogin_rtc_probe is a retry counter. With +0x20 = 3 (the approved
run) the counter moved 0x100 per second with its low byte stuck at 0xff. The
vendor writes, in order, with up to 3 attempts:

1. **APB 0xf8000200:** clear bit 30 (stock 0x80000080, U-Boot 0xc0000080). Approved and run.
2. **+0x20 = 0x0008ac1c**, then 125 us.
3. **+0x1c = 0**, then 500 ms.
4. **+0x04 = 0, +0x10 = 0, +0x08 = 0, +0x14 = 0**, each then 125 us.
5. **+0x00 = 3.**
6. **Verify:** +0x00 = 0xfc, +0x10 = 0, +0x04 = 0xc0, +0x14 = 0, +0x08 = 0xc0, +0x1c = 0. If not, the next attempt starts at step 2.
7. **+0x20 = 0x00ffffff.**

The read path is one 32-bit read of +0x0c (gogin_rtc_read_time), with no latch
and no double read. So the wrong reads came from the wrong +0x20 value, not
from the read path.

rtc-mv61x0 runs exactly this sequence when the DT node has
`marvell,vendor-setup`:
- **`m1-full`:** without it. The driver only reads.
- **`m1-full-rtcsetup`:** with it. Same kernel. **Needs the user's OK for the corrected +0x20 values (0x0008ac1c, then 0x00ffffff)**, because they differ from the approved list.

None of these registers drives a pin. The RTC is internal to the SoC.
