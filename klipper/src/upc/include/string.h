#ifndef __UPC_STRING_H
#define __UPC_STRING_H
// The few string functions Klipper's core uses (implemented in main.c).
// The UPC build is freestanding and does not link a C library.

#include <stddef.h> // size_t

void *memcpy(void *dst, const void *src, size_t n);
void *memmove(void *dst, const void *src, size_t n);
void *memset(void *dst, int c, size_t n);
int memcmp(const void *a, const void *b, size_t n);
void *memchr(const void *s, int c, size_t n);
int strcmp(const char *a, const char *b);

#endif // string.h
