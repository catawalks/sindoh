// Called from ARM code: switches to Thumb, returns 0x7b in r0.
// If the core has no Thumb support the BX raises an undefined
// instruction exception, which the probe's fault handler skips.

    .syntax unified
    .arm
    .section .text.thumb_test, "ax"
    .global thumb_test
    .type thumb_test, %function
thumb_test:
    mov     r0, #0
    adr     r12, 1f + 1
    bx      r12
    .thumb
    .align  1
1:  movs    r0, #0x7b
    bx      lr
