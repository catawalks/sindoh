/* Linker script for the UPC cores: code + constants in ITCM, data in the
 * core's slice of the shared DTCM (see upc_ipc.h for the DTCM map). */

#include "autoconf.h"

#if CONFIG_UPC_CORE_FM
#define UPC_DATA_BASE   0x04020000
#define UPC_STACK_BASE  0x04038000
#else
#define UPC_DATA_BASE   0x04028000
#define UPC_STACK_BASE  0x04030000
#endif

OUTPUT_FORMAT("elf32-littlearm")
ENTRY(_start)

MEMORY
{
  itcm  (rx) : ORIGIN = 0x00000000,     LENGTH = CONFIG_UPC_ITCM_SIZE
  dram  (rw) : ORIGIN = UPC_DATA_BASE,  LENGTH = 0x8000
  stack (rw) : ORIGIN = UPC_STACK_BASE, LENGTH = 0x8000
}

SECTIONS
{
  .text : {
    KEEP(*(.text.vectors))
    *(.text .text.*)
    *(.rodata .rodata.*)
    . = ALIGN(4);
  } > itcm

  .data : {
    __data_start = .;
    *(.data .data.*)
    . = ALIGN(4);
    __data_end = .;
  } > dram AT > itcm
  __data_load = LOADADDR(.data);

  .bss (NOLOAD) : {
    __bss_start = .;
    *(.bss .bss.* COMMON)
    . = ALIGN(4);
    __bss_end = .;
  } > dram

  __stack_irq_top = ORIGIN(stack) + 0x400;
  __stack_abt_top = ORIGIN(stack) + 0x800;
  __stack_und_top = ORIGIN(stack) + 0xc00;
  __stack_top     = ORIGIN(stack) + LENGTH(stack);

  /DISCARD/ : {
    *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*)
    *(.compile_time_request)
  }
}
