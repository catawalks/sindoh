# Faster stepping in the UPC firmware (plan 2026-11-02; phases 1-3 approved)

PROJECTS.md #5. Results so far are at the end.

## Today

Klipper's stepper code runs on the FM core as on any MCU: the host sends
`queue_step interval count add` blocks, a timer fires once per step, and
our "step pin" (`src/upc/gpio.c`, `smot_pulse`) starts a **one-step move**
on the hardware pulse engine (clear done, write CMD = 2 edges, START).

- Cost per step: the timer interrupt + Klipper's step bookkeeping + 3 engine
  register writes + a done-bit check (`smot_wait_idle`: waits if the engine
  is still busy from the previous step; counted as busy_hits).
- Measured: clean up to 32k steps/s on one axis (Z, 2026-10-19; busy_hits 0).
  Today's highest need: X/Y homing at 208 mm/s = 16.7k steps/s; prints
  at 150-210 mm/s travel are similar. Two axes at once plus E stay below
  ~40k steps/s in total.
- So the current ceiling is **not limiting the stock speeds**. The gains
  would be: headroom for higher accelerations and speeds after input
  shaping, less FM CPU load (more room for e.g. the 2X's second extruder
  later), and smoother high-speed steps.

## The idea

The engines can run multi-step moves by themselves: CMD = (edges << 16) |
mode, a fixed period (+0x58, 200 MHz ticks per edge) and a ramp mode (0x2,
+0x54) - the stock firmware's long jumps are built that way (5000 steps in
one command, docs/homing_speed_plan.md).

Klipper's step blocks map onto that well when `add == 0`: `count` steps at
a constant `interval`, e.g. cruise phases. Those become **one engine move**
instead of `count` interrupts. Blocks with `add != 0` (acceleration) keep
the per-step path at first.

## Plan

**Phase 1 - research (no motion; emulator and read-only register reads)**
1. Clock ratio: the engines run at 198.01 MHz = half of Timer1 (hardware
   notes). Confirm it's exactly half (same PLL), so a move's end time is
   predictable in MCU clock ticks without drift.
2. Find an engine register that counts the steps done so far (candidates:
   +0x64 STATUS's other bits, +0x68..+0x84; the stock FM code and the 3DWOX
   driver's register names COM_STP / STEP_INT hint at one). Method: run the
   stock FM microcode in the emulator and log its reads during a move;
   then, on the idle printer, start nothing and only read registers.
   If none exists: the step count of an aborted move is computed from the
   elapsed time (works only with an exact clock ratio).
3. What the ramp mode (0x2, +0x54) does exactly, from the stock ramp tables
   (10..110 steps per stage). Not needed for phase 2.

**Phase 2 - firmware, behind a build option (default off)**
4. `CONFIG_UPC_STEP_BATCH`: in the stepper code, a block with add == 0 and
   count >= N (e.g. 8) and an interval the engine can express is started as
   one engine move at its first step time; the rest stays per-step.
   The next block is queued so the engine starts it on time (start-time
   handling is the hard part: either poll done + start from the timer, or
   chain moves if the engine supports it).
5. Stops: trsync (homing, probing) and shutdown abort the engine (+0x04);
   the stepper's position = steps issued before the move + the steps the
   move made (from step 2). `stepper_get_position` and the homing math stay
   exact.
6. Direction changes only between moves (DIR is a bit in +0x44).
7. UPC_STEP_STATS extended: batched moves, steps per move, aborts.

**Phase 3 - checks without the printer**
8. Emulator regression (tools/kemu.py) with a timing model of the engine:
   the step times of a recorded print's step blocks must match the
   per-step build to within one engine tick.

**Phase 4 - on the printer, owner present, bed empty**
9. Drift test (scratchpad drift_test.py) at 30 / 100 / 208 mm/s: 0.000 mm.
10. Homing repeatability (as on 11-02): 0.000 spread at 208 mm/s.
11. Step-rate sweep on X/Y (not Z: torque limits it, see the 11-02 stall)
    above today's 32k steps/s, until steps are lost; set the safe limit.
12. FM load (mcu_awake / task_avg in klippy's stats) before/after at the
    same print.
13. A test print (cube) with the option on; then default on.

## Done means

- Option on: drift and homing at 0.000 mm, no lost steps at the speeds we
  use, FM load clearly lower; option off: exactly today's behaviour.
- Results in hardware_notes; the option documented in PROJECTS.md.

## Risks

- A wrong position after an aborted move would make homing or probing
  wrong (crash risk): phase 2 step 5 must be proven in the emulator
  first, and phase 4 starts with homing at low speed.
- Clock drift between engine and timer: phase 1 step 1 settles it.
- Time: phases 1-3 are a few sessions without the printer; phase 4 needs
  the owner for about an hour.

## Results (2026-11-02/03)

### Phase 1: engine registers (emulator + read-only dump)

- The stock FM microcode reads only +0x58 (period), +0x64 (status) and
  +0x88 (done) of the engines (all 60 commands emulated, `ENGREADS=1
  tools/fmseq.py`): no step counter is used by stock.
- Read-only dump of all five engines on the idle printer (`busybox devmem`,
  0x00-0xfc; the vendor's own 3DWOX stepper driver dumps the same block in
  dbg_print_reg). With the 3DWOX driver's register names aligned so that
  CMD = +0x5c, every value fits a "next move" set and a "current move"
  (COM_) copy:

  | Offset | Name (3DWOX stepper-mod-b0.ko) | Idle value X/Y/Z | Meaning |
  |---|---|---|---|
  | +0x44 | OUT_MODE | 0x33224 | output mode; bit 4 = direction |
  | +0x48 | STEP_INT | 0 | ? |
  | +0x4c | PWM_T | 1 | ? |
  | +0x50 | PWM_P | 1 | **clock divider** (stock Z back-off and probe: 200) |
  | +0x54 | ACC_INCR | 0 | ramp increment (RAMP_LEN) |
  | +0x58 | PWM_M | 0x190 | period (ticks per edge) |
  | +0x5c | CMD | 0x20001 | (edges << 16) / mode |
  | +0x60 | - | 0 | START (write 1) |
  | +0x64 | COM_STAT | 7 | status (bit 8 = busy) |
  | +0x68 | COM_PWM_P | 1 | = PWM_P of the running/last move |
  | +0x6c | COM_ACC_INCR | 0 | = ACC_INCR |
  | +0x70 | COM_PWM_M | 0x190 | = PWM_M |
  | +0x74 | COM_CMD | 0x20001 | = CMD |
  | **+0x78** | **COM_STP** | 0 | **steps of the running move (candidate)** |
  | +0x7c | COM_TVT | 1 | |
  | +0x80 | COM_SEQ | 3 | |
  | +0x84 | I_EN | 0 | interrupt enable |
  | +0x88 | I_PEND | 8 / 0x100 | done (bit 8) |
  | +0x8c | SMC_TRIG | 0 | we write 0x100 to clear done |

  Engine 4 (unused) fits too: PWM_P 0 and COM_PWM_P 0, PWM_M 1 and
  COM_PWM_M 1. The COM_ copies suggest the engine latches a command at
  START, so the next one could be written while a move runs.
- **Engine run, 2026-11-03 (owner's OK; `tools/engtest.sh`):** one move of
  60,000 edges (30,000 steps) at period 13,333 on X with the driver
  disabled (+0x0c = 0x11 in every sample: no motor current, nothing
  moved), sampled 35 times against /proc/uptime; the touched registers
  were saved and restored, kernel log clean, Klipper ready after.
  - **+0x78 counts edges, down, 24 bits:** 0x000000 -> 0xFF15A0 at the end,
    and 0x1000000 - 0xFF15A0 = 60,000 exactly. It keeps its value after the
    move (CLEAR does not reset it); Klipper's engine setup (ABORT at
    config) leaves it at 0. So steps done in a running move =
    ((value at START - value now) & 0xFFFFFF) / 2.
  - **Clock:** 59,212 edges in 3.99 s = 14,840 edges/s at 13,333 ticks per
    edge -> engine clock **197.9 MHz +-0.5 %** (10 ms uptime resolution),
    i.e. half the FM timer (Klipper measures 395.9 MHz). With the counter,
    stops don't need the exact ratio.
  - **Status:** +0x64 = 0x106 while running (bit 8 busy), 7 idle; +0x88
    bit 8 set at the end.

### Phase 2a: one timer event per step (`CONFIG_UPC_STEP_SINGLE`)

A smaller first step than batching: Klipper's step/unstep path runs two
timer events per step, and on the UPC the unstep event does nothing (the
engine makes the whole pulse). With the option (fork branch
`fast-stepping`, commit 9ade7319, default off) the steppers run
single-scheduled and every step-pin toggle starts one engine pulse; the
host's step times are unchanged. FM image 11,844 bytes (off: 11,840).

### Phase 3a: emulator regression (tools/kemu.py, gcc builds from the printer)

| Check | Option off | Option on |
|---|---|---|
| 25 steps, interval 4000 | 25 pulses, gaps 4000 | same |
| 40 steps with add -20 after a dir change | 40 pulses, gaps 5200-6000, position -15 | same |
| Step events for those 40 steps (calls of gpio_out_toggle_noirq, `HOOK=`) | **81** | **41** |
| Position read mid-move | lags the pulses by 2 | same |
| trsync stop mid-move (homing) | 103 of 300 pulses, none after, position exact | 101 of 300, none after, exact |

So the option halves the step interrupts with identical pulses and
positions in the emulator. Next for it: phase 4 on the printer (drift and
homing tests, owner present) before it becomes the default.

### Next

- Phase 2b: multi-step engine moves for constant-speed blocks, with the
  stop position from +0x78. Needs an engine model in kemu first (multi-edge
  timing, busy, abort, the counter) so it can be checked like phase 2a.
- Phase 4 for UPC_STEP_SINGLE at the printer (owner present).
