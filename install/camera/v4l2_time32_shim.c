// LD_PRELOAD shim: run time64 V4L2 programs (Debian trixie armel builds:
// ustreamer, v4l2-ctl --stream-*) on the DP200's vendor kernel 3.2.
//
// Debian 13 builds 32-bit packages with 64-bit time_t. struct v4l2_buffer
// embeds a struct timeval, so in those programs it is 80 bytes and the
// VIDIOC_{QUERYBUF,QBUF,DQBUF,PREPARE_BUF} ioctl numbers encode size 80.
// Kernel 3.2 only knows the 68-byte time32 layout and answers EINVAL.
// Kernels >= 5.6 convert between the two internally; this shim does the
// same in user space: intercept, convert to time32, call the kernel,
// convert back. glibc routes time64 programs through __ioctl_time64, so
// both that symbol and ioctl are interposed.
//
//   gcc -O2 -Wall -shared -fPIC -o v4l2_time32_shim.so v4l2_time32_shim.c -ldl
//   LD_PRELOAD=/usr/local/lib/v4l2_time32_shim.so ustreamer ...
//
// Copyright (C) 2026  This file may be distributed under the terms of the
// GNU GPLv3 license.

//
// It also REPAIRS the MJPEG frames of the DP200 camera (Sonix 0c45:6341):
// the camera never sends the JPEG end marker and ends each frame with a few
// junk bytes. When those look like a marker (FF xx), decoders fail on the
// last rows: browsers show grey/white bottom rows (a bar on the right after
// Mainsail's 270 degree rotation) or drop the frame (black flash). Measured:
// ~22 % of frames. On VIDIOC_DQBUF the frame is cut at the first illegal
// marker in the scan data (or after a real EOI) and FF D9 is appended. To
// find the frame data, MAP_SHARED mmap()s are recorded (fd, offset -> addr).

#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdarg.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

// <sys/mman.h> is NOT included: with Debian's default _FILE_OFFSET_BITS=64 it
// redirects mmap to mmap64, which would clash with the two wrappers below.
#define MAP_SHARED 0x01
#define MAP_FAILED ((void *)-1)
#define V4L2_MEMORY_MMAP 1

struct v4l2_timecode_compat {
    uint32_t type, flags;
    uint8_t frames, seconds, minutes, hours, userbits[4];
};

// What the time64 program passes (80 bytes on 32-bit ARM)
struct buf_time64 {
    uint32_t index, type, bytesused, flags, field;
    int64_t tv_sec, tv_usec;
    struct v4l2_timecode_compat timecode;
    uint32_t sequence, memory;
    uint32_t m;                 // offset / userptr / planes / fd (4 bytes)
    uint32_t length, reserved2, request_fd;
};

// What kernel 3.2 expects (68 bytes)
struct buf_time32 {
    uint32_t index, type, bytesused, flags, field;
    int32_t tv_sec, tv_usec;
    struct v4l2_timecode_compat timecode;
    uint32_t sequence, memory;
    uint32_t m;
    uint32_t length, reserved2, request_fd;
};

_Static_assert(sizeof(struct buf_time64) == 80, "time64 v4l2_buffer layout");
_Static_assert(sizeof(struct buf_time32) == 68, "time32 v4l2_buffer layout");

#define IOC_RW(nr, size) ((3UL << 30) | ((unsigned long)(size) << 16) | ('V' << 8) | (nr))
#define IOC_NR(req) ((req) & 0xff)

static int (*real_ioctl)(int, unsigned long, ...);

/****************************************************************
 * mmap tracking (to reach the frame data on DQBUF)
 ****************************************************************/

#define MAX_MAPS 32
static struct { int fd; uint32_t offset; void *addr; size_t len; } maps[MAX_MAPS];
static void *(*real_mmap)(void *, size_t, int, int, int, long);
static void *(*real_mmap64)(void *, size_t, int, int, int, int64_t);
static int (*real_munmap)(void *, size_t);

static void
map_add(int fd, int64_t off, void *addr, size_t len)
{
    if (addr == MAP_FAILED || fd < 0)
        return;
    for (int i = 0; i < MAX_MAPS; i++)
        if (!maps[i].addr) {
            maps[i].fd = fd;
            maps[i].offset = (uint32_t)off;
            maps[i].addr = addr;
            maps[i].len = len;
            return;
        }
}

void *
mmap(void *a, size_t len, int prot, int flags, int fd, long off)
{
    if (!real_mmap)
        real_mmap = dlsym(RTLD_NEXT, "mmap");
    void *r = real_mmap(a, len, prot, flags, fd, off);
    if (flags & MAP_SHARED)
        map_add(fd, off, r, len);
    return r;
}

void *
mmap64(void *a, size_t len, int prot, int flags, int fd, int64_t off)
{
    if (!real_mmap64)
        real_mmap64 = dlsym(RTLD_NEXT, "mmap64");
    void *r = real_mmap64(a, len, prot, flags, fd, off);
    if (flags & MAP_SHARED)
        map_add(fd, off, r, len);
    return r;
}

int
munmap(void *a, size_t len)
{
    if (!real_munmap)
        real_munmap = dlsym(RTLD_NEXT, "munmap");
    for (int i = 0; i < MAX_MAPS; i++)
        if (maps[i].addr == a)
            maps[i].addr = NULL;
    return real_munmap(a, len);
}

static uint8_t *
map_find(int fd, uint32_t off, size_t *len)
{
    for (int i = 0; i < MAX_MAPS; i++)
        if (maps[i].addr && maps[i].fd == fd && maps[i].offset == off) {
            *len = maps[i].len;
            return maps[i].addr;
        }
    return NULL;
}

/****************************************************************
 * MJPEG tail repair
 ****************************************************************/

// Returns the repaired frame length (<= cap)
static uint32_t
mjpeg_repair(uint8_t *d, uint32_t used, uint32_t cap)
{
    if (used < 4 || d[0] != 0xff || d[1] != 0xd8)
        return used;                        // not a JPEG frame: leave alone
    // find the start of scan and skip its header
    uint32_t i = 2;
    while (i + 4 < used) {
        if (d[i] != 0xff) {
            i++;
            continue;
        }
        uint8_t m = d[i + 1];
        if (m == 0xda)
            break;
        if (m == 0xd8 || m == 0x01 || (m >= 0xd0 && m <= 0xd7) || m == 0xff) {
            i += 1;
            continue;
        }
        i += 2 + ((d[i + 2] << 8) | d[i + 3]);   // skip a marker segment
    }
    if (i + 4 >= used)
        return used;
    i += 2 + ((d[i + 2] << 8) | d[i + 3]);
    // scan data: only FF00, FFD0-D7 and FFD9 are legal
    uint32_t end = used;
    while (i + 1 < used) {
        uint8_t *p = memchr(d + i, 0xff, used - i - 1);
        if (!p)
            break;
        i = p - d;
        uint8_t m = d[i + 1];
        if (m == 0x00 || (m >= 0xd0 && m <= 0xd7)) {
            i += 2;
            continue;
        }
        if (m == 0xff) {                    // fill byte
            i += 1;
            continue;
        }
        if (m == 0xd9)
            return i + 2;                   // proper end: drop what follows
        end = i;                            // junk marker: cut here
        break;
    }
    if (end + 2 > cap)
        return used;
    d[end] = 0xff;
    d[end + 1] = 0xd9;
    return end + 2;
}

static int
is_buf_ioctl64(unsigned long req)
{
    switch (req) {
    case IOC_RW(9, 80):    // VIDIOC_QUERYBUF
    case IOC_RW(15, 80):   // VIDIOC_QBUF
    case IOC_RW(17, 80):   // VIDIOC_DQBUF
    case IOC_RW(93, 80):   // VIDIOC_PREPARE_BUF
        return 1;
    }
    return 0;
}

static int
shim_ioctl(int fd, unsigned long req, void *arg)
{
    if (!real_ioctl)
        real_ioctl = dlsym(RTLD_NEXT, "ioctl");
    if (!is_buf_ioctl64(req) || !arg)
        return real_ioctl(fd, req, arg);

    struct buf_time64 *b64 = arg;
    struct buf_time32 b32;
    memset(&b32, 0, sizeof(b32));
    b32.index = b64->index;
    b32.type = b64->type;
    b32.bytesused = b64->bytesused;
    b32.flags = b64->flags;
    b32.field = b64->field;
    b32.tv_sec = (int32_t)b64->tv_sec;
    b32.tv_usec = (int32_t)b64->tv_usec;
    b32.timecode = b64->timecode;
    b32.sequence = b64->sequence;
    b32.memory = b64->memory;
    b32.m = b64->m;
    b32.length = b64->length;
    b32.reserved2 = b64->reserved2;
    b32.request_fd = b64->request_fd;

    int ret = real_ioctl(fd, IOC_RW(IOC_NR(req), sizeof(b32)), &b32);

    // VIDIOC_DQBUF of an mmap'ed capture buffer: repair the MJPEG frame
    if (ret == 0 && IOC_NR(req) == 17 && b32.memory == V4L2_MEMORY_MMAP) {
        size_t len;
        uint8_t *d = map_find(fd, b32.m, &len);
        if (d && b32.bytesused <= len)
            b32.bytesused = mjpeg_repair(d, b32.bytesused, len < b32.length ? len : b32.length);
    }

    b64->index = b32.index;
    b64->type = b32.type;
    b64->bytesused = b32.bytesused;
    b64->flags = b32.flags;
    b64->field = b32.field;
    b64->tv_sec = b32.tv_sec;
    b64->tv_usec = b32.tv_usec;
    b64->timecode = b32.timecode;
    b64->sequence = b32.sequence;
    b64->memory = b32.memory;
    b64->m = b32.m;
    b64->length = b32.length;
    b64->reserved2 = b32.reserved2;
    b64->request_fd = b32.request_fd;
    return ret;
}

int
__ioctl_time64(int fd, unsigned long req, ...)
{
    va_list ap;
    va_start(ap, req);
    void *arg = va_arg(ap, void *);
    va_end(ap);
    return shim_ioctl(fd, req, arg);
}

int
ioctl(int fd, unsigned long req, ...)
{
    va_list ap;
    va_start(ap, req);
    void *arg = va_arg(ap, void *);
    va_end(ap);
    return shim_ioctl(fd, req, arg);
}
