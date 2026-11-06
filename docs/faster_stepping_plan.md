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

### Phase 2b: constant-rate blocks as engine moves (`CONFIG_UPC_STEP_BATCH`)

Fork branch `fast-stepping` (8a93c354, f05f998e, e358e96b), default off;
selects UPC_STEP_SINGLE. FM image 12,404 bytes.

- A queue_step block with add == 0 and >= 8 steps (UPC_STEP_BATCH_MIN)
  runs as one engine move: edge period = interval / 4 engine ticks (the
  engine clock is half the timer's), started half an interval before the
  first step so each rising edge falls on its step time.
- interval & 3 makes each step up to 3 ticks early: a block is split into
  parts whose accumulated error stays under UPC_STEP_BATCH_ERR (400 ticks,
  1 us); each part starts on the exact schedule. Max 32,767 steps a part.
- After an engine move the next constant block starts at once if that is
  at most UPC_STEP_BATCH_LATE (800) ticks after its ideal start; after a
  one-step pulse it waits out the pulse (4 x the half period) or steps.
- `stepper_get_position` mid-move and `stepper_stop` (trsync, shutdown) use
  the edge counter: read, ABORT, read again (whether ABORT resets it is
  unknown), then the per-step period is restored.
- Accelerating blocks (add != 0) are stepped as before (UPC_STEP_SINGLE).

### Phase 3b: emulator, engine model (tools/kemu.py)

kemu now models the engines as measured: edge count x period x divider at
half the timer clock, busy/done bits, the 24-bit edge counter, ABORT. Step
times are the rising edges; each test compares them with Klipper's own
schedule for the queued blocks (gcc builds from the printer, e358e96b):

| Test | off | single | batch |
|---|---|---|---|
| 25 constant steps: engine STARTs, step time - schedule | 25, +840 | 25, +840 | **1, +40** |
| step events (toggle calls) for those 25 | 51 | 26 | **1** |
| 40 accelerating steps after a dir change | +840..860, pos ok | same | same (stepped) |
| mixed: 50 const, 30 accel, 60 const (4130), 20 accel | 160 STARTs | 160 | **52**, -54..+875 |
| back-to-back const 40 + 40 + 400 (interval 4003: split) | 480 STARTs, +840..879 | 480 | **6**, +60..+757 |
| position read mid-move | exact (lag 1-2 = the reply's own time) | same | same |
| trsync stop mid-move | stops, 0 steps after, position exact | same | same (engine aborted) |
| engine STARTs while busy | 0 | 0 | 0 |

### Phase 4 at the printer (2026-11-03, owner present, bed empty)

ABORT check first (driver disabled, no motion, `tools/engabort.sh`): ABORT
stops a running move at once (busy clears, no more edges) and **resets
+0x78 to 0**; gpio_step_burst_stop uses the value read just before the
abort then (at most one edge between: a stop is exact to 1 step).

Then the test run `p4.py` (scratchpad) per build, gcc builds of e358e96b:

| | UPC_STEP_SINGLE | UPC_STEP_BATCH |
|---|---|---|
| G28 all | 10.2 s | 12.7 s |
| X homing x10 at 208 mm/s (trigger by slow creep) | 215.980 -> 215.960 | 216.020 -> 215.980 |
| Y homing x10 at 208 mm/s | 5.500 -> 5.500 | 5.500 -> 5.500 |
| X 30 / 100 mm/s zig-zags x50, 208 mm/s 20-200 x20 | 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 |
| Y same, 20-180 | -0.020 / 0.000 / 0.000 | 0.000 / -0.040 / 0.000 |
| busy hits (X/Y/Z, ~1.2-1.5 M pulses each) | 0 / 0 / 0 | 0 / 0 / 0 |
| probe x5 at X95 Y130 | 2.4672 ... 2.4525 (0.015) | 2.4898 ... 2.4620 (0.028) |

- No lost steps, no crash, no busy hits in either build; batched homing
  seeks stopped at the switch as they should. The creep measurement steps
  0.02 mm; the X readings right after a firmware restart were off by one
  or two of those before as well (11-02: 0.06 at 150 mm/s), and the Y
  readings wander 5.44-5.48 without a trend over the 208 mm/s travels
  that follow (no accumulating loss).
- **Open: the probe.** Both builds read lower on each of the 5 touches
  (single 2.467 -> 2.453, batch 2.490 -> 2.462) and more spread than the
  0.0006 mm of 10-19. Same trend in both, so probably the probe or the bed
  rather than the stepping; to check: the same 5 probes on the gcc build
  (option off), then the batch build again.
- The printer is back on the gcc build (option off).

**Probe comparison (2026-11-03 morning, `p5.py`):** home, then 2 x 5
probes at X95 Y130:

| | round 1 (right after G28) | round 2 |
|---|---|---|
| gcc build (option off) | 2.4375 -> 2.4189, spread 0.019, mean 2.4243 | spread 0.007, mean 2.4157 |
| UPC_STEP_BATCH | 2.4309 -> 2.4105, spread 0.021, mean 2.4170 | spread 0.007, mean 2.4158 |

Same on both: the first touches after homing read ~0.015-0.02 mm high and
settle; after that both repeat to 0.007 mm and agree to 0.0001 mm. So
probing is unaffected; the settling is the probe/bed, not the stepping
(worth a look for BED_MESH after G28: e.g. a few untimed touches first).

**Cube with UPC_STEP_BATCH (2026-11-03 afternoon):**
xyzCalibration_cube_zhop.gcode completed in 1,507 s (1,502 s on the gcc
build, 10-28), no pause or error, busy hits 0 on X/Y/Z/E (2.2 / 2.0 / 1.7 /
2.9 M pulses), kernel log clean. Owner's measurements: **X 20.0, Y 19.9,
Z 20.3 mm** (gcc build 10-28: 20.1 / 20.0 / 20.2): X/Y within caliper and
print variation; Z +0.1 vs then, a first-layer/Z-offset matter (Z stepping
matched the gcc build to 0.0001 mm in the probe test). Printer back on the
gcc build afterwards.

**FM load measurement: not possible with klippy's stats.** A fixed motion
pattern (diagonals, print-speed zig-zags, 208 mm/s travels; tools/fast_stepping_load.py,
run) gave mcu_awake 0.0008 moving vs 0.0010 idle on the gcc build:
klippy's mcu_awake / task_avg only time the main-loop tasks, and on the UPC
the step timers aren't in that span. A real load figure needs an idle-loop
counter in our firmware (e.g. loop iterations per second reported by
upc_step_stats). The emulator's event counts stay the load evidence.

**Adopted 2026-11-03** (owner: surfaces as before): fork branch merged
into sindoh-dp200, `CONFIG_UPC_STEP_BATCH=y` in config/dp200_fm.config
(f035bdbc, mirrored to klipper/configs/). The test printer runs it from
/opt/dp200/fm.bin (the previous build kept as fm_gcc.bin); the USB payload
is rebuilt with it.

### Bug found on the work printer (2026-11-05/06) and fixed

A PrusaSlicer print shut the FM MCU down ~19 min in, on the first-layer
solid infill: `Stepper too far in past`. At 20 mm/s the extruder steps at
~425 steps/s (~2.3 ms per step); a batched block's engine move kept the
STEP line high for half an interval (~1.2 ms) after its last rising edge,
and only then did the next block load - its first step was then >1 ms in
the past. The kemu tests had no slow block followed by a faster one.
**Fix (fork 8d4fb4d8):** an engine move never includes the block's last
step; that step is a normal one-step pulse at its time, and the next block
loads as with stepping. The chaining shortcut (UPC_STEP_BATCH_LATE) went
with it. New kemu test "slow then fast" (920000 x 9, then 40000 x 30):
the old build shuts down, the new one runs it with every step on time.
Side effect: a constant block right after a block must start its engine
half an interval before its first step, after the previous one-step pulse
has ended (4 x the half period + latency): below ~5,000-tick intervals
(~80k steps/s) such blocks are stepped. Our fastest real case is 16.7k
steps/s (X/Y at 208 mm/s).

### Next

- Idle-loop counter in upc_step_stats for an on-printer load figure.
- Original phase 4 list: first UPC_STEP_SINGLE,
  then UPC_STEP_BATCH: homing repeatability (as on 11-02, 208 mm/s), the
  drift test at 30/100/208 mm/s, probing, then a cube. The engine's
  first-edge delay (assumed one edge time after START) and the ABORT
  counter behaviour are only measured there.
