#ifndef __UPC_INTERNAL_H
#define __UPC_INTERNAL_H

#include <stdint.h>
#include "autoconf.h" // CONFIG_UPC_CORE_FM
#include "upc_hw.h"
#include "upc_ipc.h"

#if CONFIG_UPC_CORE_FM
 #define UPC_CORE_ID 1
 #define UPC_IPC_OFFSET IPC_FM_OFFSET
#else
 #define UPC_CORE_ID 0
 #define UPC_IPC_OFFSET IPC_IO_OFFSET
#endif

#define UPC_IPC ((struct ipc_header *)(UPC_DTCM_BASE + UPC_IPC_OFFSET))
#define UPC_SHARED ((struct ipc_shared *)(UPC_DTCM_BASE + IPC_SHARED_OFFSET))

static inline uint32_t reg_read(uint32_t addr)
{
    return *(volatile uint32_t *)addr;
}

static inline void reg_write(uint32_t addr, uint32_t val)
{
    *(volatile uint32_t *)addr = val;
}

// Peterson lock between the two UPC cores (main.c)
void upc_lock(void);
void upc_unlock(void);

// main.c
void console_poll(void);
void upc_outputs_off(void);

// timer.c
void timer_boot(void);
uint8_t timer_pending(void);
void timer_clear_pending(void);
void timer_set(uint32_t next);

// gpio.c
void gpio_all_off(void);

#endif // internal.h
