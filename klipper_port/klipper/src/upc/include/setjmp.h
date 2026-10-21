#ifndef __UPC_SETJMP_H
#define __UPC_SETJMP_H
// Minimal setjmp for the freestanding UPC build (implemented in start.S).
// Saves r4-r11, sp and lr.

typedef int jmp_buf[10];

int setjmp(jmp_buf env) __attribute__((returns_twice));
void longjmp(jmp_buf env, int val) __attribute__((noreturn));

#endif // setjmp.h
