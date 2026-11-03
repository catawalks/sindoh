# Faster stepping in the UPC firmware (plan, 2026-11-02, for review)

PROJECTS.md #5. Nothing here is started; the owner reviews this first.

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
