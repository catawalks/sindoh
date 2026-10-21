// GPIO, hardware PWM and stepper-engine "pins" for the UPC cores
//
// Copyright (C) 2026  This file may be distributed under the terms of the
// GNU GPLv3 license.
//
// The DP200 has no plain GPIOs reachable from the UPC for its motors and
// heaters. Instead:
//  - inputs (endstops etc.) are XENA input pins, read from XIRD/XIRD1;
//  - heater/fan/clutch/solenoid/motor-current outputs are dec_pwm blocks,
//    used either at a static level (digital out, Klipper soft PWM) or as
//    real hardware PWM;
//  - STEP lines come from the "Gogin" stepper engines. A virtual step pin
//    issues a one-pulse hardware move on each idle->active transition, so
//    Klipper's normal step/unstep toggling produces exactly one pulse per
//    step. DIR and driver-enable are bits in the engine registers.

#include "autoconf.h" // CONFIG_UPC_STEP_HALF_TICKS
#include "board/irq.h" // irq_save
#include "command.h" // shutdown
#include "gpio.h" // gpio_out_setup
#include "internal.h" // reg_write
#include "sched.h" // sched_shutdown

DECL_ENUMERATION_RANGE("pin", "xena0", PIN_XENA_BASE, PIN_XENA_COUNT);
DECL_ENUMERATION_RANGE("pin", "pwm1", PIN_PWM_FIRST, PIN_PWM_COUNT);
DECL_ENUMERATION_RANGE("pin", "smot_step0", PIN_STEP_BASE, SMOT_COUNT);
DECL_ENUMERATION_RANGE("pin", "smot_dir0", PIN_DIR_BASE, SMOT_COUNT);
DECL_ENUMERATION_RANGE("pin", "smot_en0", PIN_EN_BASE, SMOT_COUNT);
DECL_ENUMERATION_RANGE("pin", "adc0", PIN_ADC_BASE, PIN_ADC_COUNT);
DECL_ENUMERATION_RANGE("pin", "dsens0", PIN_DSENS_BASE, PIN_DSENS_COUNT);

static uint8_t step_level[SMOT_COUNT], step_idle[SMOT_COUNT];
static uint8_t dir_level[SMOT_COUNT], en_level[SMOT_COUNT];
static uint8_t pwm_level[PIN_PWM_COUNT + 1];
static uint32_t pwm_owned, smot_owned;

static int
pin_in(uint8_t pin, uint8_t base, uint8_t count)
{
    return pin >= base && pin < base + count;
}


/****************************************************************
 * dec_pwm blocks
 ****************************************************************/

// Per-block configuration bits (everything except RUN and LEVEL), as left
// by the stock firmware (dumped from the printer with devmem after a stock
// boot). Without the stock app nobody else sets them.
static uint32_t
pwm_config_bits(uint8_t block)
{
    switch (block) {
    case 6:  return 0x5a;   // clutch: FM microcode writes 0x5a off / 0x5e on
    case 7:  return 0x18;
    case 8:  return 0x2a;   // solenoid: FM microcode writes 0x2a off / 0x2e on
    case 0x1b: case 0x1c: case 0x1d: case 0x1e: case 0x1f:
        return 0x0a;        // A4982 REF current
    default: return 0x28;   // fans, heaters (stock IO init: 0x20 | 0x08)
    }
}

static void
pwm_claim(uint8_t block)
{
    if (pwm_owned & (1u << (block - 1)))
        return;
    pwm_owned |= 1u << (block - 1);
    uint32_t b = PWM_BLOCK(block);
    // Output low and stopped, with the stock configuration bits
    uint32_t c = pwm_config_bits(block) & ~(PWM_CTRL_LEVEL | PWM_CTRL_RUN);
    reg_write(b + PWM_CTRL, c);
    upc_lock();
    reg_write(PWM_GLOBAL_EN, reg_read(PWM_GLOBAL_EN) | (1u << (block - 1)));
    upc_unlock();
}

static void
pwm_static(uint8_t block, uint8_t val)
{
    uint32_t b = PWM_BLOCK(block), c = reg_read(b + PWM_CTRL);
    c = val ? c | PWM_CTRL_LEVEL : c & ~PWM_CTRL_LEVEL;
    reg_write(b + PWM_CTRL, c);
    reg_write(b + PWM_CTRL, c & ~PWM_CTRL_RUN);
    pwm_level[block] = !!val;
}

DECL_CONSTANT("PWM_MAX", 255);

// Default periods (in PWM clock ticks) used by the stock firmware
static uint16_t
pwm_default_period(uint8_t block)
{
    if (block >= 1 && block <= 4)
        return 100;                 // fans
    if (block == 5 || block == 0x18)
        return 1000;                // nozzle / bed heater
    if (block >= 0x1b && block <= 0x1f)
        return 200;                 // A4982 REF current
    return 100;
}

struct gpio_pwm
gpio_pwm_setup(uint8_t pin, uint32_t cycle_time, uint32_t val)
{
    if (!pin_in(pin, PIN_PWM_FIRST, PIN_PWM_COUNT))
        shutdown("Not a valid PWM pin");
    // cycle_time is in MCU clock ticks; the dec_pwm clock is unknown, so
    // the stock period for each block is used instead.
    struct gpio_pwm g = { .block = pin - PIN_PWM_BASE };
    g.period = pwm_default_period(g.block);
    pwm_claim(g.block);
    gpio_pwm_write(g, val);
    return g;
}

void
gpio_pwm_write(struct gpio_pwm g, uint32_t val)
{
    uint32_t high = (val * g.period) / 255;
    if (!high) {
        pwm_static(g.block, 0);
        return;
    }
    if (high >= g.period) {
        pwm_static(g.block, 1);
        return;
    }
    uint32_t b = PWM_BLOCK(g.block);
    reg_write(b + PWM_HIGH, high);
    reg_write(b + PWM_LOW, g.period - high);
    reg_write(b + PWM_CTRL, reg_read(b + PWM_CTRL) | PWM_CTRL_RUN);
}


/****************************************************************
 * Stepper engines
 ****************************************************************/

static void
smot_claim(uint8_t n)
{
    if (!CONFIG_UPC_CORE_FM)
        shutdown("Stepper engines belong to the FM core");
    if (smot_owned & (1u << n))
        return;
    smot_owned |= 1u << n;
    uint32_t b = SMOT_BASE(n);
    reg_write(b + SMOT_ABORT, SMOT_DONE_BIT);
    reg_write(b + SMOT_CLEAR, SMOT_DONE_BIT);
    reg_write(b + SMOT_ENABLE, 1);
    reg_write(b + SMOT_PERIOD, CONFIG_UPC_STEP_HALF_TICKS);
    reg_write(b + SMOT_CTRL, SMOT_CTRL_STOCK | (dir_level[n] ? SMOT_CTRL_DIR : 0));
}

// Step-rate diagnostics: above ~20k steps/s steps get lost (measured
// 2026-10-18). Count pulses and pulses requested while the engine still
// reports busy (+0x64 bit 8); in that case wait for the running pulse (a
// few us) instead of overwriting it. upc_step_stats reports the counters.
static uint32_t smot_pulses[SMOT_COUNT], smot_busy_hits[SMOT_COUNT];

static inline void
smot_pulse(uint8_t n)
{
    uint32_t b = SMOT_BASE(n);
    smot_pulses[n]++;
    if (reg_read(b + SMOT_STATUS) & SMOT_DONE_BIT) {
        smot_busy_hits[n]++;
        // one pulse is 2 edges of CONFIG_UPC_STEP_HALF_TICKS: bound the wait
        for (uint32_t i = 0; i < 4096; i++)
            if (!(reg_read(b + SMOT_STATUS) & SMOT_DONE_BIT))
                break;
    }
    reg_write(b + SMOT_CLEAR, SMOT_DONE_BIT);
    reg_write(b + SMOT_CMD, (2u << 16) | SMOT_MODE_CONST);
    reg_write(b + SMOT_START, 1);
}

#if CONFIG_UPC_CORE_FM
void
command_upc_step_stats(uint32_t *args)
{
    uint8_t n = args[0];
    if (n >= SMOT_COUNT)
        shutdown("Invalid engine");
    sendf("upc_step_stats_result engine=%c pulses=%u busy_hits=%u"
          , n, smot_pulses[n], smot_busy_hits[n]);
}
DECL_COMMAND(command_upc_step_stats, "upc_step_stats engine=%c");
#endif

static void
smot_set_dir(uint8_t n, uint8_t val)
{
    dir_level[n] = !!val;
    reg_write(SMOT_BASE(n) + SMOT_CTRL
              , SMOT_CTRL_STOCK | (val ? SMOT_CTRL_DIR : 0));
}

static void
smot_set_disable(uint8_t n, uint8_t val)
{
    en_level[n] = !!val;
    uint32_t a = SMOT_BASE(n) + SMOT_CFG, c = reg_read(a);
    reg_write(a, val ? c | 1 : c & ~1u);
}


/****************************************************************
 * Digital outputs
 ****************************************************************/

struct gpio_out
gpio_out_setup(uint8_t pin, uint8_t val)
{
    struct gpio_out g = { .pin = pin };
    if (pin_in(pin, PIN_PWM_FIRST, PIN_PWM_COUNT)) {
        pwm_claim(pin - PIN_PWM_BASE);
    } else if (pin_in(pin, PIN_STEP_BASE, SMOT_COUNT)) {
        uint8_t n = pin - PIN_STEP_BASE;
        smot_claim(n);
        step_idle[n] = step_level[n] = !!val;
        return g;
    } else if (pin_in(pin, PIN_DIR_BASE, SMOT_COUNT)) {
        smot_claim(pin - PIN_DIR_BASE);
    } else if (pin_in(pin, PIN_EN_BASE, SMOT_COUNT)) {
        smot_claim(pin - PIN_EN_BASE);
    } else {
        shutdown("Not an output pin");
    }
    gpio_out_write(g, val);
    return g;
}

void
gpio_out_reset(struct gpio_out g, uint8_t val)
{
    if (pin_in(g.pin, PIN_STEP_BASE, SMOT_COUNT)) {
        uint8_t n = g.pin - PIN_STEP_BASE;
        step_idle[n] = step_level[n] = !!val;
        return;
    }
    gpio_out_write(g, val);
}

void
gpio_out_write(struct gpio_out g, uint8_t val)
{
    uint8_t pin = g.pin;
    if (pin_in(pin, PIN_PWM_FIRST, PIN_PWM_COUNT)) {
        pwm_static(pin - PIN_PWM_BASE, val);
    } else if (pin_in(pin, PIN_STEP_BASE, SMOT_COUNT)) {
        uint8_t n = pin - PIN_STEP_BASE;
        val = !!val;
        if (val != step_level[n]) {
            step_level[n] = val;
            if (val != step_idle[n])
                smot_pulse(n);
        }
    } else if (pin_in(pin, PIN_DIR_BASE, SMOT_COUNT)) {
        smot_set_dir(pin - PIN_DIR_BASE, val);
    } else if (pin_in(pin, PIN_EN_BASE, SMOT_COUNT)) {
        smot_set_disable(pin - PIN_EN_BASE, val);
    }
}

void
gpio_out_toggle_noirq(struct gpio_out g)
{
    uint8_t pin = g.pin;
    if (pin_in(pin, PIN_STEP_BASE, SMOT_COUNT)) {
        uint8_t n = pin - PIN_STEP_BASE;
        uint8_t val = step_level[n] ^ 1;
        step_level[n] = val;
        if (val != step_idle[n])
            smot_pulse(n);
    } else if (pin_in(pin, PIN_DIR_BASE, SMOT_COUNT)) {
        uint8_t n = pin - PIN_DIR_BASE;
        smot_set_dir(n, !dir_level[n]);
    } else if (pin_in(pin, PIN_EN_BASE, SMOT_COUNT)) {
        uint8_t n = pin - PIN_EN_BASE;
        smot_set_disable(n, !en_level[n]);
    } else if (pin_in(pin, PIN_PWM_FIRST, PIN_PWM_COUNT)) {
        uint8_t block = pin - PIN_PWM_BASE;
        pwm_static(block, !pwm_level[block]);
    }
}

void
gpio_out_toggle(struct gpio_out g)
{
    irqstatus_t flag = irq_save();
    gpio_out_toggle_noirq(g);
    irq_restore(flag);
}


/****************************************************************
 * Digital inputs
 ****************************************************************/

// dec_sensor block (0xf9301000): +0x210 is a sensor status word. Bit 8 is
// the stock "LV" bed-levelling sensor (FM probing command 0x2a stops when
// it sets). The stock IO firmware configures the block at boot; do the
// same if nobody has (values from the stock init trace).
static void
dsens_init(void)
{
    if (reg_read(DEC_SENSOR_BASE + 0x200) == 0x180)
        return;
    static const uint32_t init[][2] = {
        { 0x070, 0x340 }, { 0x074, 0xa }, { 0x078, 0xc80001 }, { 0x07c, 0x100c8 },
        { 0x080, 0x340 }, { 0x084, 0xa }, { 0x088, 0xc80001 }, { 0x08c, 0x100c8 },
        { 0x200, 0x180 },
    };
    for (uint32_t i = 0; i < ARRAY_SIZE(init); i++)
        reg_write(DEC_SENSOR_BASE + init[i][0], init[i][1]);
}

struct gpio_in
gpio_in_setup(uint8_t pin, int8_t pull_up)
{
    if (pin_in(pin, PIN_DSENS_BASE, PIN_DSENS_COUNT))
        dsens_init();
    else if (!pin_in(pin, PIN_XENA_BASE, PIN_XENA_COUNT))
        shutdown("Not an input pin");
    // Pull resistors are fixed on the board; pull_up is ignored.
    return (struct gpio_in){ .pin = pin };
}

void
gpio_in_reset(struct gpio_in g, int8_t pull_up)
{
}

uint8_t
gpio_in_read(struct gpio_in g)
{
    uint32_t v;
    if (g.pin >= PIN_DSENS_BASE)
        v = reg_read(DEC_SENSOR_BASE + 0x210);
    else
        v = reg_read(g.pin < 32 ? XENA_XIRD : XENA_XIRD1);
    return (v >> (g.pin & 31)) & 1;
}


/****************************************************************
 * Emergency off (fault handler / firmware shutdown)
 ****************************************************************/

void
gpio_all_off(void)
{
    for (uint8_t block = 1; block <= PIN_PWM_COUNT; block++)
        if (pwm_owned & (1u << (block - 1)))
            pwm_static(block, 0);
    for (uint8_t n = 0; n < SMOT_COUNT; n++)
        if (smot_owned & (1u << n)) {
            reg_write(SMOT_BASE(n) + SMOT_ABORT, SMOT_DONE_BIT);
            smot_set_disable(n, 1);
        }
}
