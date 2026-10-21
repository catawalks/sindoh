#ifndef __UPC_GPIO_H
#define __UPC_GPIO_H

#include <stdint.h> // uint8_t

// Pin numbering (names are declared in gpio.c):
//   0..63    xena0..xena63      XENA input pins (endstops, sensors)
//   65..96   pwm1..pwm32        dec_pwm blocks (static level or hard PWM)
//   100..104 smot_step0..4      hardware stepper engine: one pulse per step
//   105..109 smot_dir0..4       engine direction bit
//   110..114 smot_en0..4        engine driver-disable bit (1 = disabled)
//   120..127 adc0..adc7         dec_adc mux select (0 nozzle, 1 bed)
//   128..159 dsens0..dsens31    dec_sensor +0x210 status bits (dsens8 = LV
//                               bed-levelling sensor)
enum {
    PIN_XENA_BASE = 0, PIN_XENA_COUNT = 64,
    PIN_PWM_BASE = 64, PIN_PWM_FIRST = 65, PIN_PWM_COUNT = 32,
    PIN_STEP_BASE = 100, PIN_DIR_BASE = 105, PIN_EN_BASE = 110,
    PIN_ADC_BASE = 120, PIN_ADC_COUNT = 8,
    PIN_DSENS_BASE = 128, PIN_DSENS_COUNT = 32,
};

struct gpio_out {
    uint8_t pin;
};
struct gpio_out gpio_out_setup(uint8_t pin, uint8_t val);
void gpio_out_reset(struct gpio_out g, uint8_t val);
void gpio_out_toggle_noirq(struct gpio_out g);
void gpio_out_toggle(struct gpio_out g);
void gpio_out_write(struct gpio_out g, uint8_t val);

struct gpio_in {
    uint8_t pin;
};
struct gpio_in gpio_in_setup(uint8_t pin, int8_t pull_up);
void gpio_in_reset(struct gpio_in g, int8_t pull_up);
uint8_t gpio_in_read(struct gpio_in g);

struct gpio_pwm {
    uint8_t block;
    uint16_t period;
};
struct gpio_pwm gpio_pwm_setup(uint8_t pin, uint32_t cycle_time, uint32_t val);
void gpio_pwm_write(struct gpio_pwm g, uint32_t val);

struct gpio_adc {
    uint8_t sel;
};
struct gpio_adc gpio_adc_setup(uint8_t pin);
uint32_t gpio_adc_sample(struct gpio_adc g);
uint16_t gpio_adc_read(struct gpio_adc g);
void gpio_adc_cancel_sample(struct gpio_adc g);

#endif // gpio.h
