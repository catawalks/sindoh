// Polled timer for the UPC cores
//
// Copyright (C) 2026  This file may be distributed under the terms of the
// GNU GPLv3 license.
//
// No interrupts are used: irq_poll() (main.c) checks timer_pending() and
// runs timer_dispatch_many_polling(), exactly like the AR100 port.
//
// Timebase (measured on the printer with the probe firmware): the UPC has
// no free-running counter. XENA Timer1 is a 32-bit one-shot down-counter
// at ~395.8 MHz (2 x the dithered 198 MHz bus clock); loaded with
// 0xffffffff it runs ~10.8 s and stops at 0. The FM core reloads it before
// it runs out and adds the elapsed ticks to a shared accumulator in DTCM;
// both cores compute time = acc + (RELOAD - Timer1) under a seqlock, so
// the two Klipper MCUs share one continuous clock. The IO core never
// writes the timer. The FM core must be running for the IO core's clock
// to advance past one Timer1 period.

#include "autoconf.h" // CONFIG_UPC_TIMER_ADDR
#include "board/misc.h" // timer_read_time
#include "internal.h" // reg_read
#include "sched.h" // DECL_INIT

#define TIMER_RELOAD 0xffffffffu
#define TIMER_RELOAD_BELOW 0x40000000u  // ~8 s of headroom

static uint32_t timer_compare, timer_boot_offset;
static uint8_t timer_armed;

// Shared Timer1-based count (same on both cores)
static uint32_t
shared_time(void)
{
    struct ipc_shared *sh = UPC_SHARED;
#if CONFIG_UPC_CORE_FM
    uint32_t raw = reg_read(CONFIG_UPC_TIMER_ADDR);
    if (unlikely(raw < TIMER_RELOAD_BELOW)) {
        sh->timer_seq++;
        barrier();
        sh->timer_acc += TIMER_RELOAD - raw;
        reg_write(CONFIG_UPC_TIMER_ADDR, TIMER_RELOAD);
        // The write may take a few cycles to land; a read in between would
        // still see the old small value and reload (double count) again.
        while (reg_read(CONFIG_UPC_TIMER_ADDR) < TIMER_RELOAD_BELOW)
            ;
        barrier();
        sh->timer_seq++;
        raw = TIMER_RELOAD;
    }
    return sh->timer_acc + (TIMER_RELOAD - raw);
#else
    for (;;) {
        uint32_t seq = sh->timer_seq;
        barrier();
        if (seq & 1)
            continue;
        uint32_t acc = sh->timer_acc;
        uint32_t raw = reg_read(CONFIG_UPC_TIMER_ADDR);
        barrier();
        if (sh->timer_seq == seq)
            return acc + (TIMER_RELOAD - raw);
    }
#endif
}

// Return the current time (in absolute clock ticks). Klipper assumes the
// clock starts near zero at boot (sched.c's periodic_timer starts at 0 and
// advances 100 ms per run), so each core counts from its own boot.
uint32_t
timer_read_time(void)
{
    return shared_time() - timer_boot_offset;
}

// Called from upc_main() before any Klipper code runs (and again after a
// "reset" command, which restarts at the reset vector).
void
timer_boot(void)
{
    timer_boot_offset = shared_time();
}

uint8_t
timer_pending(void)
{
    return timer_armed && !timer_is_before(timer_read_time(), timer_compare);
}

void
timer_clear_pending(void)
{
    timer_armed = 0;
}

// Set the next timer wake up time
void
timer_set(uint32_t next)
{
    timer_compare = next;
    timer_armed = 1;
}

// Activate timer dispatch as soon as possible
void
timer_kick(void)
{
    timer_set(timer_read_time() + 50);
}

void
timer_init(void)
{
    // On the FM core the first timer_read_time() starts a stopped Timer1
    timer_kick();
}
DECL_INIT(timer_init);
