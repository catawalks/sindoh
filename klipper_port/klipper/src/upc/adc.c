// dec_adc support (IO core) - thermistor inputs
//
// Copyright (C) 2026  This file may be distributed under the terms of the
// GNU GPLv3 license.
//
// The register sequence is replayed from the stock IO firmware (functions
// io_2764, io_2870, io_28fc, io_2944 and io_0680). The stock code selects
// one input per timer tick and reads the 10-entry FIFO on the next tick;
// we do the same with a configurable settle time. A reading is the stock
// "drop min and max, average 8" of the 10 FIFO samples, in raw 10-bit
// units, so ADC_MAX = 1023 and the draft thermistor tables (code/2048 of
// the stock 11-bit value) map 1:1 to raw/1023.

#include "autoconf.h" // CONFIG_UPC_ADC_SETTLE_US
#include "board/misc.h" // timer_read_time
#include "command.h" // shutdown
#include "gpio.h" // gpio_adc_setup
#include "internal.h" // reg_write
#include "sched.h" // sched_shutdown

DECL_CONSTANT("ADC_MAX", ADC_RAW_MAX);

enum { ADC_IDLE, ADC_SETTLING, ADC_SETTLED };
static uint8_t adc_inited, adc_state, adc_cur_sel = 0xff;
static uint32_t adc_ready_time;

static void
adc_hw_init(void)
{
    // io_2764: reset sequencer state
    reg_write(ADC_BASE + 0x0c0, 0);
    reg_write(ADC_BASE + 0x0d4, 0);
    for (uint32_t a = 0x020; a <= 0x090; a += 8)
        reg_write(ADC_BASE + a, reg_read(ADC_BASE + a) & 0xf9ffffff);
    for (uint32_t a = 0x280; a <= 0x2bc; a += 4)
        reg_write(ADC_BASE + a, 0);
    adc_inited = 1;
}

static void
adc_select(uint8_t sel)
{
    uint32_t ctrl = reg_read(ADC_CTRL);
    reg_write(ADC_CTRL, ctrl | 1);
    reg_write(ADC_CTRL, (ctrl & 0x27f8) | ADC_CTRL_RUN);
    reg_write(ADC_CFG1, ADC_CFG1_VAL);
    reg_write(ADC_CFG2, (reg_read(ADC_CFG2) & 0xf0000000) | 0x19);
    uint32_t word = ADC_MUX_WORD(sel);
    for (int i = 0; i < 9; i++)
        reg_write(ADC_MUX(i), word);
    reg_write(ADC_MUX_LAST, word & ~0x10000u);
    reg_write(ADC_SEQ, (reg_read(ADC_SEQ) & 0xffffff0f) | 0x8000000f);
}

struct gpio_adc
gpio_adc_setup(uint8_t pin)
{
    if (pin < PIN_ADC_BASE || pin >= PIN_ADC_BASE + PIN_ADC_COUNT)
        shutdown("Not a valid ADC pin");
    if (!adc_inited)
        adc_hw_init();
    return (struct gpio_adc){ .sel = pin - PIN_ADC_BASE };
}

// Try to sample a value. Returns zero if sample ready, otherwise
// returns the number of clock ticks the caller should wait before
// retrying this function.
//
// Selecting an input costs one settle period; further samples of the
// same input are read back-to-back from the FIFO. Klipper samples one
// sensor sample_count times in a row, so each report needs only one
// settle per sensor.
uint32_t
gpio_adc_sample(struct gpio_adc g)
{
    uint32_t now = timer_read_time();
    if (adc_cur_sel == g.sel) {
        if (adc_state == ADC_SETTLED)
            return 0;
        if (adc_state == ADC_SETTLING) {
            int32_t diff = adc_ready_time - now;
            if (diff > 0)
                return diff;
            adc_state = ADC_SETTLED;
            return 0;
        }
    } else if (adc_state == ADC_SETTLING) {
        // Another input is settling - try again shortly
        return timer_from_us(500);
    }
    adc_select(g.sel);
    adc_cur_sel = g.sel;
    adc_state = ADC_SETTLING;
    uint32_t wait = timer_from_us(CONFIG_UPC_ADC_SETTLE_US);
    adc_ready_time = now + wait;
    return wait;
}

// Read a value; use only after gpio_adc_sample() returns zero
uint16_t
gpio_adc_read(struct gpio_adc g)
{
    uint32_t sum = 0, lo = 0xffff, hi = 0;
    for (int i = 0; i < ADC_FIFO_LEN; i++) {
        uint32_t v = reg_read(ADC_FIFO(i)) & 0x3fff;
        if (v > ADC_RAW_MAX)
            v = ADC_RAW_MAX;
        sum += v;
        if (v < lo)
            lo = v;
        if (v > hi)
            hi = v;
    }
    return (sum - lo - hi + 4) / 8;
}

// Cancel a sample that may have been started with gpio_adc_sample()
void
gpio_adc_cancel_sample(struct gpio_adc g)
{
    if (adc_cur_sel == g.sel && adc_state == ADC_SETTLING) {
        adc_state = ADC_IDLE;
        adc_cur_sel = 0xff;
    }
}
