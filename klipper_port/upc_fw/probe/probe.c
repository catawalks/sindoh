// UPC hardware probe firmware ("hello world" + measurements)
//
// Copyright (C) 2026  This file may be distributed under the terms of the
// GNU GPLv3 license.
//
// Loaded with 'upctool load probe_io.bin probe_fm.bin', read back with
// 'upctool probe'. It answers the questions the Klipper port depends on:
//   - which XENA register is a free-running counter, its direction and
//     frequency (rate is measured on the Linux side against
//     CLOCK_MONOTONIC);
//   - whether the core executes Thumb code and code placed in DTCM;
//   - CP15 identification and how large the ITCM really is;
//   - live state of all XENA input pins (toggle endstops by hand);
//   - raw ADC FIFO contents for mux select 0 (nozzle) and 1 (bed).
// It is passive: it forces heaters/fans/clutch off and stepper drivers
// disabled, and never enables any output.

#include <stdint.h>
#include "upc_hw.h"
#include "upc_ipc.h"

#ifndef PROBE_TCM
 #define PROBE_TCM 0
#endif
#ifndef PROBE_DTCM_EXEC
 #define PROBE_DTCM_EXEC 0
#endif

#if PROBE_CORE_FM
 #define IPC_OFF IPC_FM_OFFSET
 #define CORE_NAME "FM"
#else
 #define IPC_OFF IPC_IO_OFFSET
 #define CORE_NAME "IO"
#endif

#define IPC ((struct ipc_header *)(UPC_DTCM_BASE + IPC_OFF))
#define REPORT ((struct probe_report *)(UPC_DTCM_BASE + IPC_OFF + IPC_PROBE_OFFSET))

static inline uint32_t rd(uint32_t a) { return *(volatile uint32_t *)a; }
static inline void wr(uint32_t a, uint32_t v) { *(volatile uint32_t *)a = v; }
#define barrier() __asm__ __volatile__("" : : : "memory")

/****************************************************************
 * Fault recovery: while 'probing' is set, exceptions are counted and
 * execution resumes (after the faulting instruction, or at
 * 'recover_addr' for prefetch aborts).
 ****************************************************************/

static volatile uint32_t probing, recover_addr, fault_seen;

int __attribute__((used))
upc_fault(uint32_t vector, uint32_t addr, uint32_t spsr, uint32_t *frame)
{
    if (probing) {
        REPORT->aborts++;
        fault_seen = vector;
        if (vector == 3 && recover_addr)
            frame[5] = recover_addr;    // prefetch abort: return to caller
        return 1;
    }
    IPC->fault_type = vector;
    IPC->fault_lr = addr;
    IPC->fault_spsr = spsr;
    IPC->fault_count++;
    IPC->state = IPC_STATE_FAULT;
    for (;;)
        ;
    return 0;
}

/****************************************************************
 * UART "hello world" (ttyS0 is also the Linux console)
 ****************************************************************/

static void
uart_putc(char c)
{
    for (uint32_t i = 0; i < 100000; i++)
        if (rd(UART_LSR) & UART_LSR_THRE)
            break;
    wr(UART_THR, c);
}

static void
uart_puts(const char *s)
{
    while (*s)
        uart_putc(*s++);
}

// Progress marker before each test: "F3 " (FM core) / "i3 " (IO core).
// Short tokens stay readable when both cores print at the same time, and
// show where a core stopped if a test hangs the bus.
static void
step(char n)
{
    uart_putc(PROBE_CORE_FM ? 'F' : 'i');
    uart_putc(n);
    uart_putc(' ');
}

/****************************************************************
 * Safe state
 ****************************************************************/

static void
outputs_off(void)
{
#if !PROBE_CORE_FM
    for (uint32_t n = PWM_FIRST_BLOCK; n <= PWM_NUM_BLOCKS; n++) {
        uint32_t b = PWM_BLOCK(n), c = rd(b + PWM_CTRL);
        wr(b + PWM_CTRL, c & ~PWM_CTRL_LEVEL);
        wr(b + PWM_CTRL, c & ~(PWM_CTRL_LEVEL | PWM_CTRL_RUN));
    }
#else
    for (uint32_t n = 0; n < SMOT_COUNT; n++) {
        wr(SMOT_BASE(n) + SMOT_ABORT, SMOT_DONE_BIT);
        wr(SMOT_BASE(n) + SMOT_CFG, rd(SMOT_BASE(n) + SMOT_CFG) | 1);
    }
#endif
}

/****************************************************************
 * Capability tests
 ****************************************************************/

static uint32_t __attribute__((noinline))
cp15_read(int which)
{
    uint32_t v = 0xffffffff;
    probing = 1;
    if (which == 0)
        __asm__ __volatile__("mrc p15, 0, %0, c0, c0, 0" : "+r"(v));
    else if (which == 1)
        __asm__ __volatile__("mrc p15, 0, %0, c1, c0, 0" : "+r"(v));
    else
        __asm__ __volatile__("mrc p15, 0, %0, c0, c0, 2" : "+r"(v));
    probing = 0;
    return v;
}

uint32_t thumb_test(void);   // thumb_test.S

static uint32_t
probe_thumb(void)
{
    probing = 1;
    uint32_t r = thumb_test();
    probing = 0;
    return r;
}

static uint32_t dtcm_code[4];

static uint32_t __attribute__((noinline, unused))
probe_dtcm_exec(void)
{
    dtcm_code[0] = 0xe3a000e1;      // mov r0, #0xe1
    dtcm_code[1] = 0xe12fff1e;      // bx lr
    barrier();
    uint32_t (*fn)(void) = (void *)dtcm_code;
    recover_addr = (uint32_t)__builtin_return_address(0);
    probing = 1;
    uint32_t r = fn();
    probing = 0;
    recover_addr = 0;
    return r;
}

// Reads beyond a TCM do NOT raise a data abort on this SoC: on the real
// printer the first probe run (which also read 0x00010000 and
// 0x04040000/0x04080000) froze the whole chip, Linux included. Only
// addresses inside the 64 KiB window Linux maps for each core's ITCM
// (f9200000-f920ffff) and inside the 256 KiB DTCM are read now.
static void __attribute__((unused))
probe_tcm_sizes(struct probe_report *r)
{
    static const uint32_t addrs[PROBE_NUM_TCM_TESTS] = {
        0x00004000, 0x00008000, 0x0000c000, 0x0000fffc,
        0x0403fffc, 0, 0, 0,
    };
    uint32_t base0 = rd(0x0), base1 = rd(0x4);
    for (int i = 0; i < PROBE_NUM_TCM_TESTS; i++) {
        uint32_t a = addrs[i];
        if (!a)
            continue;
        uart_putc('a' + i);
        r->tcm_probe_addr[i] = a;
        fault_seen = 0;
        probing = 1;
        uint32_t v0 = rd(a & ~3u), v1 = (a & 0xffff) < 0xfffc ? rd((a & ~3u) + 4) : 0;
        probing = 0;
        if (fault_seen)
            r->tcm_probe_result[i] = 2;
        else if (a < 0x04000000 && v0 == base0 && v1 == base1)
            r->tcm_probe_result[i] = 3;     // mirrors ITCM start
        else
            r->tcm_probe_result[i] = 1;
    }
}

/****************************************************************
 * Counter candidates
 ****************************************************************/

static const uint32_t counter_addrs[] = {
    XENA_PERFMON0_TIMER, XENA_PERFMON1_TIMER,
    XENA_TIMER(0), XENA_TIMER(1), XENA_TIMER(2), XENA_TIMER(3),
    XENA_PHASE(0), XENA_PHASE(1), XENA_PHASE(2), XENA_PHASE(3),
    XENA_PHASEREF, XENA_ENCPOS, XENA_PSEUDOENCODER, XENA_STATUS,
    XENA_BASE + 0x200, XENA_BASE + 0x260,   // PerfMon FW event regs
};

static void
counters_init(struct probe_report *r)
{
#if PROBE_CORE_FM
    // Timers 1-3 are unused by the stock firmware. Load them so we can
    // see whether a XENA timer runs only after being written.
    wr(XENA_TIMER(1), 0xffffffff);
    wr(XENA_TIMER(2), 0x00000000);
#endif
    for (int i = 0; i < PROBE_NUM_COUNTERS - PROBE_CORE_FM; i++) {
        struct probe_counter *c = &r->ctr[i];
        c->addr = counter_addrs[i];
        probing = 1;
        c->first = c->last = rd(c->addr);
        probing = 0;
    }
}

// XENA Timer1 is a one-shot 32-bit down-counter (measured on hardware:
// loaded with 0xffffffff it reaches 0 after ~10 s, then stops). The FM
// probe reloads it before it runs out and keeps a continuous up-count in
// the last counter slot (label 0x1e1e0001), so 'upctool probe' can measure
// its exact rate. This is the scheme the Klipper timer uses.
#define T1_LABEL 0x1e1e0001
#define T1_RELOAD_BELOW 0x40000000u

static void
timer1_extended(struct probe_report *r)
{
    static uint32_t acc;
    struct probe_counter *c = &r->ctr[PROBE_NUM_COUNTERS - 1];
    uint32_t raw = rd(XENA_TIMER(1));
    if (raw < T1_RELOAD_BELOW) {
        acc += 0xffffffff - raw;
        wr(XENA_TIMER(1), 0xffffffff);
        raw = 0xffffffff;
    }
    uint32_t ext = acc + (0xffffffff - raw);
    c->addr = T1_LABEL;
    if (ext != c->last) {
        c->changes++;
        if ((int32_t)(ext - c->last) > 0)
            c->increases++;
        else
            c->decreases++;
        c->last = ext;
    }
}

static void
counters_poll(struct probe_report *r)
{
#if PROBE_CORE_FM
    timer1_extended(r);
#endif
    for (int i = 0; i < PROBE_NUM_COUNTERS - PROBE_CORE_FM; i++) {
        struct probe_counter *c = &r->ctr[i];
        uint32_t v = rd(c->addr);
        if (v != c->last) {
            c->changes++;
            if ((int32_t)(v - c->last) > 0)
                c->increases++;
            else
                c->decreases++;
            c->last = v;
        }
    }
}

/****************************************************************
 * ADC (IO core): same register sequence as the Klipper port
 ****************************************************************/

#if !PROBE_CORE_FM
static void
adc_init(void)
{
    wr(ADC_BASE + 0x0c0, 0);
    wr(ADC_BASE + 0x0d4, 0);
    for (uint32_t a = 0x020; a <= 0x090; a += 8)
        wr(ADC_BASE + a, rd(ADC_BASE + a) & 0xf9ffffff);
    for (uint32_t a = 0x280; a <= 0x2bc; a += 4)
        wr(ADC_BASE + a, 0);
}

static void
adc_select(uint32_t sel)
{
    uint32_t ctrl = rd(ADC_CTRL);
    wr(ADC_CTRL, ctrl | 1);
    wr(ADC_CTRL, (ctrl & 0x27f8) | ADC_CTRL_RUN);
    wr(ADC_CFG1, ADC_CFG1_VAL);
    wr(ADC_CFG2, (rd(ADC_CFG2) & 0xf0000000) | 0x19);
    uint32_t word = ADC_MUX_WORD(sel);
    for (int i = 0; i < 9; i++)
        wr(ADC_MUX(i), word);
    wr(ADC_MUX_LAST, word & ~0x10000u);
    wr(ADC_SEQ, (rd(ADC_SEQ) & 0xffffff0f) | 0x8000000f);
}

static void
adc_capture(struct probe_report *r, uint32_t sel)
{
    uint32_t sum = 0, lo = 0xffff, hi = 0;
    for (int i = 0; i < ADC_FIFO_LEN; i++) {
        uint32_t raw = rd(ADC_FIFO(i));
        r->adc_fifo[sel][i] = raw;
        uint32_t v = (raw & 0x3fff) * 2048 / 1023;    // stock 11-bit code
        sum += v;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
    }
    r->adc_code[sel] = (sum - lo - hi + 4) >> 3;
}
#endif

/****************************************************************
 * Main
 ****************************************************************/

int __attribute__((used, noreturn))
upc_main(void)
{
    struct ipc_header *h = IPC;
    struct probe_report *r = REPORT;
    outputs_off();
    h->magic = 0;
    h->version = IPC_VERSION;
    h->fw_id = 0x31425250;      // "PRB1"
    h->state = IPC_STATE_BOOT;
    uart_puts("\r\n[UPC probe] " CORE_NAME " core alive\r\n");

    uint32_t cpsr;
    __asm__ __volatile__("mrs %0, cpsr" : "=r"(cpsr));
    r->core = PROBE_CORE_FM;
    r->cpsr = cpsr;
    step('1');
    r->cp15_id = cp15_read(0);
    r->cp15_ctrl = cp15_read(1);
    r->cp15_tcm = cp15_read(2);
    step('2');
    r->thumb_ok = probe_thumb();
    step('3');
#if PROBE_DTCM_EXEC
    // Off by default: on the real printer an instruction fetch from DTCM
    // stalls the core forever (no prefetch abort is raised).
    r->dtcm_exec_ok = probe_dtcm_exec();
#endif
    step('4');
#if PROBE_TCM
    probe_tcm_sizes(r);     // off by default: see comment at probe_tcm_sizes
#endif
    step('5');
    counters_init(r);
    r->xird_and = r->xird1_and = 0xffffffff;
#if !PROBE_CORE_FM
    step('6');
    adc_init();
    adc_select(0);
    r->adc_enabled = 1;
    uint32_t adc_sel = 0;
#endif
    step('L');
    uart_puts("\r\n");
    r->magic = IPC_MAGIC;
    h->state = IPC_STATE_RUNNING;
    h->magic = IPC_MAGIC;

    for (;;) {
        r->loops++;
        h->heartbeat++;
        counters_poll(r);
        uint32_t x0 = rd(XENA_XIRD), x1 = rd(XENA_XIRD1);
        r->xird = x0;
        r->xird1 = x1;
        r->xird_or |= x0;
        r->xird1_or |= x1;
        r->xird_and &= x0;
        r->xird1_and &= x1;
#if !PROBE_CORE_FM
        // Switch input every 4096 loops; capture just before switching
        if ((r->loops & 0xfff) == 0) {
            adc_capture(r, adc_sel);
            adc_sel ^= 1;
            adc_select(adc_sel);
        }
#endif
    }
}
