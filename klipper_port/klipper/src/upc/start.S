// Reset/exception entry for the Marvell UPC cores (ARMv5TE, ARM mode).
//
// The core starts at address 0 (ITCM) with interrupts masked when Linux
// releases CPUSoftReset. We never enable interrupts: Klipper runs fully
// polled, like the AR100 port. Exceptions are reported through the IPC
// header by upc_fault(), which also forces outputs off.

    .syntax unified
    .arm
    .section .text.vectors, "ax"
    .global _start
_start:
    b       reset
    b       undef_entry
    b       swi_entry
    b       pabort_entry
    b       dabort_entry
    b       .
    b       irq_entry
    b       fiq_entry

reset:
    msr     cpsr_c, #0xd2           // IRQ mode, IRQ+FIQ masked
    ldr     sp, =__stack_irq_top
    msr     cpsr_c, #0xd1           // FIQ mode
    ldr     sp, =__stack_irq_top
    msr     cpsr_c, #0xd7           // ABT mode
    ldr     sp, =__stack_abt_top
    msr     cpsr_c, #0xdb           // UND mode
    ldr     sp, =__stack_und_top
    msr     cpsr_c, #0xd3           // SVC mode - we run here
    ldr     sp, =__stack_top

    // Copy .data from ITCM to DTCM, clear .bss
    ldr     r0, =__data_load
    ldr     r1, =__data_start
    ldr     r2, =__data_end
1:  cmp     r1, r2
    ldrlo   r3, [r0], #4
    strlo   r3, [r1], #4
    blo     1b
    ldr     r1, =__bss_start
    ldr     r2, =__bss_end
    mov     r3, #0
2:  cmp     r1, r2
    strlo   r3, [r1], #4
    blo     2b

    bl      upc_main
3:  b       3b

// Exception entries. Each pushes r0-r3,r12 and the resume address, sets
// r0 = vector number and r1 = faulting instruction, then calls
// int upc_fault(uint32_t vector, uint32_t addr, uint32_t spsr,
//               uint32_t *frame)
// frame[0..4] = saved r0-r3,r12, frame[5] = resume address. A nonzero
// return resumes at frame[5] (the probe firmware uses this to survive
// reads of unmapped addresses); Klipper never resumes.

undef_entry:                        // lr = faulting + 4 = resume address
    stmfd   sp!, {r0-r3, r12, lr}
    mov     r0, #1
    sub     r1, lr, #4
    b       fault_common
swi_entry:
    stmfd   sp!, {r0-r3, r12, lr}
    mov     r0, #2
    sub     r1, lr, #4
    b       fault_common
pabort_entry:                       // lr = faulting + 4; never resumable
    stmfd   sp!, {r0-r3, r12, lr}
    mov     r0, #3
    sub     r1, lr, #4
    b       fault_common
dabort_entry:                       // lr = faulting + 8
    sub     lr, lr, #4              // resume at the next instruction
    stmfd   sp!, {r0-r3, r12, lr}
    mov     r0, #4
    sub     r1, lr, #4
    b       fault_common
irq_entry:                          // should never happen (IRQs masked)
    sub     lr, lr, #4
    stmfd   sp!, {r0-r3, r12, lr}
    mov     r0, #6
    mov     r1, lr
    b       fault_common
fiq_entry:
    sub     lr, lr, #4
    stmfd   sp!, {r0-r3, r12, lr}
    mov     r0, #7
    mov     r1, lr
    b       fault_common

fault_common:
    mrs     r2, spsr
    mov     r3, sp
    bl      upc_fault
    cmp     r0, #0
4:  beq     4b
    ldmfd   sp!, {r0-r3, r12, pc}^

    .ltorg

// int setjmp(jmp_buf env) / void longjmp(jmp_buf env, int val)
// Used by Klipper's sched.c for shutdown handling.
    .section .text.setjmp, "ax"
    .global setjmp
    .type setjmp, %function
setjmp:
    mov     r2, sp
    stmia   r0, {r4-r11}
    str     r2, [r0, #32]
    str     lr, [r0, #36]
    mov     r0, #0
    bx      lr

    .global longjmp
    .type longjmp, %function
longjmp:
    ldmia   r0, {r4-r11}
    ldr     sp, [r0, #32]
    ldr     lr, [r0, #36]
    movs    r0, r1
    moveq   r0, #1
    bx      lr
