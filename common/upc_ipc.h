// Shared-memory layout between Linux (upctool) and our UPC firmware.
//
// Everything lives in the 256 KiB DTCM, which both UPC cores and Linux
// (via /dev/mem) can access while the cores run. Offsets are relative to
// the DTCM base; the UPC sees DTCM at 0x04000000.
//
// DTCM use:
//   0x00000-0x0ffff  free (stock firmware tables lived here; unused by us)
//   0x10000-0x13fff  IPC block for the FM core (upc1)
//   0x14000-0x17fff  IPC block for the IO core (upc0)
//   0x18000-0x18fff  cross-core shared state (locks)
//   0x20000-0x27fff  FM core .data/.bss/heap
//   0x28000-0x2ffff  IO core .data/.bss/heap
//   0x30000-0x37fff  IO core stacks
//   0x38000-0x3ffff  FM core stacks
//
// Rings are single-producer/single-consumer with free-running 32-bit
// indices; the producer writes data, then a barrier, then its index.

#ifndef __UPC_IPC_H
#define __UPC_IPC_H

#include <stdint.h>

#define IPC_MAGIC           0x50554c4bu   // "KLUP"
#define IPC_VERSION         1u
#define IPC_FM_OFFSET       0x10000u
#define IPC_IO_OFFSET       0x14000u
#define IPC_BLOCK_SIZE      0x4000u
#define IPC_SHARED_OFFSET   0x18000u
#define IPC_RING_SIZE       0x1000u       // power of two
#define IPC_PROBE_OFFSET    0x2100u       // probe report inside an IPC block

enum {
    IPC_STATE_BOOT = 0, IPC_STATE_RUNNING = 1, IPC_STATE_SHUTDOWN = 2,
    IPC_STATE_PARKED = 3, IPC_STATE_FAULT = 0xdeadu,
};

struct ipc_header {
    uint32_t magic;          // written last by firmware once initialized
    uint32_t version;
    uint32_t state;          // IPC_STATE_*
    uint32_t heartbeat;      // incremented by firmware main loop
    uint32_t fault_type;     // exception vector number when state == FAULT
    uint32_t fault_lr;
    uint32_t fault_spsr;
    uint32_t fault_count;
    uint32_t fw_id;          // firmware identification ('PRB1', 'KLP1', ...)
    uint32_t reserved[7];
    // host -> UPC ring
    volatile uint32_t rx_head;   // written by host
    volatile uint32_t rx_tail;   // written by UPC
    uint32_t pad0[2];
    // UPC -> host ring
    volatile uint32_t tx_head;   // written by UPC
    volatile uint32_t tx_tail;   // written by host
    uint32_t pad1[2];
    uint32_t pad2[(0x100 - 0x60) / 4];
    uint8_t rx[IPC_RING_SIZE];   // at +0x100
    uint8_t tx[IPC_RING_SIZE];   // at +0x1100
};

// Two-core Peterson lock (no atomic instructions needed) protecting
// read-modify-write of shared peripheral registers such as PWM_GLOBAL_EN.
struct ipc_shared {
    volatile uint32_t flag[2];   // [0] = IO core, [1] = FM core
    volatile uint32_t turn;
    // Shared timebase (see klipper/src/upc/timer.c): XENA Timer1 is a
    // one-shot down-counter; the FM core reloads it and accumulates the
    // elapsed ticks here. Odd timer_seq = update in progress.
    volatile uint32_t timer_seq;
    volatile uint32_t timer_acc;
    uint32_t reserved[11];
};

// ---------------------------------------------------------------------
// Probe firmware report (fw_id 'PRB1'), at IPC block + IPC_PROBE_OFFSET
// ---------------------------------------------------------------------
#define PROBE_NUM_COUNTERS  16
#define PROBE_NUM_TCM_TESTS 8

struct probe_counter {
    uint32_t addr;
    uint32_t first;          // value at start
    uint32_t last;           // latest value
    uint32_t changes;        // number of loop iterations where it changed
    uint32_t increases;      // ... and the new value was larger
    uint32_t decreases;      // ... and the new value was smaller
};

struct probe_report {
    uint32_t magic;          // IPC_MAGIC once filled
    uint32_t loops;          // main loop iterations
    uint32_t core;           // 0 = IO core, 1 = FM core
    uint32_t cpsr;
    uint32_t cp15_id;        // CP15 c0 main ID register
    uint32_t cp15_ctrl;      // CP15 c1 control register
    uint32_t cp15_tcm;       // CP15 c0 TCM status (ARM946/966 style)
    uint32_t thumb_ok;       // 0x7b = Thumb call returned correctly
    uint32_t dtcm_exec_ok;   // 0xe1 = code copied to DTCM executed
    uint32_t aborts;         // data/prefetch aborts taken during probing
    uint32_t xird, xird1;    // live input pins
    uint32_t xird_or, xird1_or;      // OR of all samples since start
    uint32_t xird_and, xird1_and;    // AND of all samples since start
    uint32_t adc_enabled;    // 1 if ADC sampling ran (IO core only)
    uint32_t adc_fifo[2][10];// raw FIFO for mux select 0 / 1
    uint32_t adc_code[2];    // stock-style averaged 11-bit code
    uint32_t tcm_probe_addr[PROBE_NUM_TCM_TESTS];
    uint32_t tcm_probe_result[PROBE_NUM_TCM_TESTS]; // 1 ok, 2 abort, 3 mismatch
    struct probe_counter ctr[PROBE_NUM_COUNTERS];
};

#endif // upc_ipc.h
