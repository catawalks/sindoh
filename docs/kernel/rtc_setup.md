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

- **Reads only:**
  - the probe logs the control word, and the counter twice, 1.1 s apart, to show whether it is counting;
  - `read_time` returns the counter as seconds since 1970.
- **No writes:** no `set_time`, no alarm, no interrupt, nothing written.
- **Time:** stock sets the clock to 1970 at every boot, so there is probably no backup battery, and NTP is the real time source.

## Proposal: the vendor probe's setup (needs the user's OK)

Order as in gogin_rtc_probe; the values are as written there.

1. **APB config:** 0xf8000200 &= ~mask. The mask is in the vendor platform data, probably an RTC clock/reset gate; to be read out of the vendor data first.
2. **+0x20 = 3**, then a short delay.
3. **+0x1c = 0**, then a delay and 500 ms of sleep.
4. **Clear +0x04, +0x10 (alarm), +0x08 and +0x14** to 0, each followed by a short delay.
5. **+0x00 = 3** (enable).

None of these registers drives a pin, so nothing outside the SoC is affected; the RTC is internal. Still, they are new register writes, so they need the user's OK. They only matter if the read-only probe shows the counter is not running. Setting the time (+0x0c twice) is a separate step after that.
