// Main entry, console and fault handling for the UPC cores
//
// Copyright (C) 2026  This file may be distributed under the terms of the
// GNU GPLv3 license.
//
// Modelled on the AR100 port: no interrupts, everything is polled from
// irq_poll(). The "serial port" is a pair of byte rings in DTCM that
// 'upctool bridge' on Linux connects to a pty for klippy.

#include <stddef.h> // size_t
#include <string.h> // memcpy
#include "autoconf.h" // CONFIG_MCU
#include "board/irq.h" // irq_disable
#include "board/misc.h" // dynmem_start
#include "command.h" // DECL_CONSTANT_STR
#include "generic/serial_irq.h" // serial_rx_byte
#include "generic/timer_irq.h" // timer_dispatch_many_polling
#include "internal.h" // UPC_IPC
#include "sched.h" // sched_main

DECL_CONSTANT_STR("MCU", CONFIG_MCU);

#define RING_MASK (IPC_RING_SIZE - 1)


/****************************************************************
 * Freestanding C library helpers (gcc may emit calls to these)
 ****************************************************************/

void * __visible
memcpy(void *dst, const void *src, size_t n)
{
    uint8_t *d = dst;
    const uint8_t *s = src;
    while (n--)
        *d++ = *s++;
    return dst;
}

void * __visible
memmove(void *dst, const void *src, size_t n)
{
    uint8_t *d = dst;
    const uint8_t *s = src;
    if (d < s) {
        while (n--)
            *d++ = *s++;
    } else {
        d += n;
        s += n;
        while (n--)
            *--d = *--s;
    }
    return dst;
}

void * __visible
memset(void *dst, int c, size_t n)
{
    uint8_t *d = dst;
    while (n--)
        *d++ = c;
    return dst;
}

int __visible
memcmp(const void *a, const void *b, size_t n)
{
    const uint8_t *x = a, *y = b;
    for (; n--; x++, y++)
        if (*x != *y)
            return *x - *y;
    return 0;
}

int __visible
strcmp(const char *a, const char *b)
{
    while (*a && *a == *b)
        a++, b++;
    return (uint8_t)*a - (uint8_t)*b;
}

void * __visible
memchr(const void *s, int c, size_t n)
{
    const uint8_t *p = s;
    for (; n--; p++)
        if (*p == (uint8_t)c)
            return (void *)p;
    return NULL;
}


/****************************************************************
 * Dynamic memory pool (move queues etc.)
 ****************************************************************/

static uint32_t dynmem_pool[CONFIG_UPC_DYNMEM_SIZE / 4];

void *
dynmem_start(void)
{
    return dynmem_pool;
}

void *
dynmem_end(void)
{
    return &dynmem_pool[ARRAY_SIZE(dynmem_pool)];
}


/****************************************************************
 * Cross-core lock (Peterson's algorithm on uncached DTCM)
 ****************************************************************/

void
upc_lock(void)
{
    struct ipc_shared *s = UPC_SHARED;
    const uint32_t me = UPC_CORE_ID, other = 1 - UPC_CORE_ID;
    s->flag[me] = 1;
    s->turn = other;
    barrier();
    while (s->flag[other] && s->turn == other)
        ;
}

void
upc_unlock(void)
{
    barrier();
    UPC_SHARED->flag[UPC_CORE_ID] = 0;
}


/****************************************************************
 * Console: DTCM rings <-> generic/serial_irq.c
 ****************************************************************/

static uint8_t need_tx;

void
console_poll(void)
{
    struct ipc_header *h = UPC_IPC;
    // Host -> MCU
    uint32_t head = h->rx_head, tail = h->rx_tail;
    if (head != tail) {
        barrier();
        while (tail != head)
            serial_rx_byte(h->rx[tail++ & RING_MASK]);
        barrier();
        h->rx_tail = tail;
    }
    // MCU -> host
    if (need_tx) {
        head = h->tx_head;
        tail = h->tx_tail;
        while (head - tail < IPC_RING_SIZE) {
            uint8_t b;
            if (serial_get_tx_byte(&b) < 0) {
                need_tx = 0;
                break;
            }
            h->tx[head++ & RING_MASK] = b;
        }
        barrier();
        h->tx_head = head;
    }
}

void
serial_enable_tx_irq(void)
{
    need_tx = 1;
    console_poll();
}


/****************************************************************
 * Interrupt / polling glue
 ****************************************************************/

void
irq_disable(void)
{
}

void
irq_enable(void)
{
}

irqstatus_t
irq_save(void)
{
    return 0;
}

void
irq_restore(irqstatus_t flag)
{
}

void
timer_dispatch_irq_poll(void)
{
}

void
timer_dispatch_task_poll(void)
{
    console_poll();
}

void
irq_poll(void)
{
    if (timer_pending()) {
        timer_clear_pending();
        uint32_t next = timer_dispatch_many_polling();
        timer_set(next);
    }
    console_poll();
    UPC_IPC->heartbeat++;
}

void
irq_wait(void)
{
    irq_poll();
}


/****************************************************************
 * Faults, shutdown and reset
 ****************************************************************/

// Called from start.S on any exception. Never resumes in Klipper.
int __visible
upc_fault(uint32_t vector, uint32_t addr, uint32_t spsr, uint32_t *frame)
{
    gpio_all_off();
    struct ipc_header *h = UPC_IPC;
    h->fault_type = vector;
    h->fault_lr = addr;
    h->fault_spsr = spsr;
    h->fault_count++;
    h->state = IPC_STATE_FAULT;
    for (;;)
        ;
    return 0;
}

void
upc_shutdown(void)
{
    UPC_IPC->state = IPC_STATE_SHUTDOWN;
}
DECL_SHUTDOWN(upc_shutdown);

void
command_reset(uint32_t *args)
{
    // Restart from the reset vector: start.S re-copies .data and clears
    // .bss (the ITCM image is untouched). Outputs keep their shutdown state.
    gpio_all_off();
    void (*reset)(void) = (void *)UPC_ITCM_BASE;
    reset();
}
DECL_COMMAND_FLAGS(command_reset, HF_IN_SHUTDOWN, "reset");

static void
ipc_init(void)
{
    struct ipc_header *h = UPC_IPC;
    h->magic = 0;
    h->version = IPC_VERSION;
    h->fw_id = 0x31504c4b;      // "KLP1"
    h->state = IPC_STATE_BOOT;
    // Discard stale data in both directions; each side owns one index
    h->rx_tail = h->rx_head;
    h->tx_head = h->tx_tail;
    barrier();
    h->state = IPC_STATE_RUNNING;
    h->magic = IPC_MAGIC;
}

void __visible __noreturn
upc_main(void)
{
    timer_boot();
    ipc_init();
    sched_main();
    for (;;)
        ;
}
