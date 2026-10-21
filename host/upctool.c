// upctool - load, stop, probe and bridge the Sindoh DP200 UPC cores.
//
// Runs on the printer's Linux (kernel 3.2, armhf). Build statically so it
// works both on the stock BusyBox userland and inside a Debian chroot:
//   make -C host            (see host/Makefile)
//
// Subcommands:
//   upctool info                     show addresses, core states
//   upctool safe                     heaters/fans/clutch off, stepper drivers off
//   upctool stop                     hold both UPC cores in reset, then 'safe'
//   upctool load IO.bin|- FM.bin|-   stop, load images ('-' = park), start
//   upctool probe [seconds]          print probe firmware reports + counter rates
//   upctool bridge [-f PATH] [-i PATH] [-p POLL_US]
//                                    expose the cores' DTCM rings as ptys
//   upctool dump OFFSET LEN          hex dump of DTCM
//
// Global options (before the subcommand):
//   --dtcm ADDR    physical DTCM base (default: auto-detect + verify)
//   --force        allow running while the stock printer app is running
//
// Copyright (C) 2026  This file may be distributed under the terms of the
// GNU GPLv3 license.

#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#include "../common/upc_hw.h"
#include "../common/upc_ipc.h"

// upc.ko ioctls (decoded from upc_ioctl in upc.ko)
#define UPC_IOC_RUN          0xc0017521u  // CPUSoftReset = 1 (both cores run)
#define UPC_IOC_HOLD         0xc0017522u  // CPUSoftReset = 0 (both cores held)
#define UPC_IOC_SEL_ITCM     0x00007523u  // following write() goes to ITCM
#define UPC_IOC_SEL_DTCM     0xc0047524u  // arg (by value) = DTCM offset
#define UPC_DEV_IO           "/dev/upc0"
#define UPC_DEV_FM           "/dev/upc1"

#define DTCM_MAP_SIZE        UPC_DTCM_SIZE
#define VERIFY_OFFSET        (IPC_SHARED_OFFSET + 0xffc)

static int opt_force;
static unsigned long opt_dtcm;
static volatile uint8_t *dtcm;
static volatile uint8_t *pwm_regs, *smot_regs;
static volatile int stop_requested;

/****************************************************************
 * Helpers
 ****************************************************************/

static void
die(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "upctool: ");
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fputc('\n', stderr);
    exit(1);
}

static void
barrier_full(void)
{
    __sync_synchronize();
}

static double
now_sec(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

static volatile uint8_t *
map_phys(unsigned long addr, size_t len)
{
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0)
        die("open /dev/mem: %s", strerror(errno));
    void *p = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_SHARED, fd, addr);
    close(fd);
    if (p == MAP_FAILED)
        die("mmap %#lx: %s", addr, strerror(errno));
    return p;
}

static uint32_t
rd32(volatile uint8_t *base, uint32_t off)
{
    return *(volatile uint32_t *)(base + off);
}

static void
wr32(volatile uint8_t *base, uint32_t off, uint32_t val)
{
    *(volatile uint32_t *)(base + off) = val;
}

static int
upc_open(const char *dev)
{
    for (int i = 0; i < 50; i++) {
        int fd = open(dev, O_RDWR);
        if (fd >= 0)
            return fd;
        if (errno != EBUSY && errno != EINTR)
            die("open %s: %s (is upc.ko loaded?)", dev, strerror(errno));
        usleep(20000);
    }
    die("open %s: busy", dev);
    return -1;
}

static void
upc_ioctl(const char *dev, unsigned long req, unsigned long arg)
{
    int fd = upc_open(dev);
    if (ioctl(fd, req, arg) < 0)
        die("ioctl %#lx on %s: %s", req, dev, strerror(errno));
    close(fd);
}

static void
write_all(int fd, const void *buf, size_t len, const char *what)
{
    const uint8_t *p = buf;
    while (len) {
        ssize_t r = write(fd, p, len);
        if (r < 0 && errno == EINTR)
            continue;
        if (r <= 0)
            die("write %s: %s", what, r < 0 ? strerror(errno) : "short");
        p += r;
        len -= r;
    }
}

// Write a buffer into a core's ITCM through upc.ko (as the stock app does)
static void
itcm_write(const char *dev, const void *buf, size_t len)
{
    if (len > UPC_ITCM_SIZE)
        die("image for %s is %zu bytes, ITCM holds %u", dev, len, UPC_ITCM_SIZE);
    int fd = upc_open(dev);
    if (ioctl(fd, UPC_IOC_SEL_ITCM, 0) < 0)
        die("select ITCM: %s", strerror(errno));
    write_all(fd, buf, len, dev);
    close(fd);
}

// Write into DTCM through upc.ko (used only to verify the /dev/mem mapping)
static void
dtcm_write_drv(uint32_t offset, const void *buf, size_t len)
{
    int fd = upc_open(UPC_DEV_IO);
    if (ioctl(fd, UPC_IOC_SEL_DTCM, (unsigned long)offset) < 0)
        die("select DTCM: %s", strerror(errno));
    write_all(fd, buf, len, "DTCM");
    close(fd);
}

static void
check_stock_app(void)
{
    if (opt_force)
        return;
    DIR *d = opendir("/proc");
    if (!d)
        return;
    struct dirent *de;
    while ((de = readdir(d))) {
        char path[64], comm[64] = "";
        if (de->d_name[0] < '0' || de->d_name[0] > '9')
            continue;
        snprintf(path, sizeof(path), "/proc/%s/comm", de->d_name);
        FILE *f = fopen(path, "r");
        if (!f)
            continue;
        if (fgets(comm, sizeof(comm), f) && strstr(comm, "marvell_lspsdk"))
            die("stock printer app is running (pid %s); stop it or use --force",
                de->d_name);
        fclose(f);
    }
    closedir(d);
}

/****************************************************************
 * DTCM address discovery
 ****************************************************************/

// Collect start addresses of /proc/iomem entries that look like upc.ko's
// resources, plus known fallbacks.
static int
dtcm_candidates(unsigned long *out, int max)
{
    int n = 0;
    FILE *f = fopen("/proc/iomem", "r");
    if (f) {
        char line[256];
        while (fgets(line, sizeof(line), f) && n < max - 2) {
            unsigned long start, end;
            if (!strcasestr(line, "upc"))
                continue;
            if (sscanf(line, " %lx-%lx", &start, &end) == 2)
                out[n++] = start + 0x70000;
        }
        fclose(f);
    }
    // Fallbacks derived from the reported ITCM addresses (UNVERIFIED)
    out[n++] = 0xf9270000;
    out[n++] = 0xf9280000;
    return n;
}

static void
dtcm_attach(void)
{
    if (dtcm)
        return;
    unsigned long cand[16];
    int n = opt_dtcm ? (cand[0] = opt_dtcm, 1) : dtcm_candidates(cand, 16);
    // Write a nonce through the driver, look for it through /dev/mem
    uint32_t nonce = 0x55c00000u ^ (uint32_t)getpid() ^ (uint32_t)time(NULL);
    dtcm_write_drv(VERIFY_OFFSET, &nonce, sizeof(nonce));
    for (int i = 0; i < n; i++) {
        volatile uint8_t *p = map_phys(cand[i], DTCM_MAP_SIZE);
        if (rd32(p, VERIFY_OFFSET) == nonce) {
            dtcm = p;
            opt_dtcm = cand[i];
            uint32_t zero = 0;
            dtcm_write_drv(VERIFY_OFFSET, &zero, sizeof(zero));
            return;
        }
        munmap((void *)p, DTCM_MAP_SIZE);
    }
    die("could not locate DTCM via /dev/mem (tried %d candidates); "
        "check /proc/iomem and pass --dtcm ADDR", n);
}

static struct ipc_header *
ipc_block(int fm)
{
    return (struct ipc_header *)(dtcm + (fm ? IPC_FM_OFFSET : IPC_IO_OFFSET));
}

/****************************************************************
 * Safe state
 ****************************************************************/

static void
periph_attach(void)
{
    if (!pwm_regs)
        pwm_regs = map_phys(PWM_BASE, 0x3000);
    if (!smot_regs)
        smot_regs = map_phys(SMOT_BASE(0), 0x1000 * SMOT_COUNT);
}

// Force every PWM block to a static low level and disable/abort all
// stepper engines. Works whether or not the UPC cores are running, but
// a running core may re-enable outputs afterwards.
static void
do_safe(void)
{
    periph_attach();
    for (int n = PWM_FIRST_BLOCK; n <= PWM_NUM_BLOCKS; n++) {
        uint32_t off = 0x100 * n + PWM_CTRL;
        uint32_t c = rd32(pwm_regs, off);
        wr32(pwm_regs, off, c & ~PWM_CTRL_LEVEL);
        wr32(pwm_regs, off, c & ~(PWM_CTRL_LEVEL | PWM_CTRL_RUN));
    }
    for (int n = 0; n < SMOT_COUNT; n++) {
        uint32_t b = 0x1000 * n;
        wr32(smot_regs, b + SMOT_ABORT, SMOT_DONE_BIT);
        wr32(smot_regs, b + SMOT_CFG, rd32(smot_regs, b + SMOT_CFG) | 1);
    }
    barrier_full();
}

static void
do_stop(void)
{
    check_stock_app();
    upc_ioctl(UPC_DEV_IO, UPC_IOC_HOLD, 0);
    do_safe();
}

/****************************************************************
 * Loading
 ****************************************************************/

// Park image: "1: wfi; b 1b" (ARM). Keeps an unused core idle.
static const uint32_t park_image[] = { 0xee070f90, 0xeafffffd };

static uint8_t *
read_image(const char *path, size_t *len)
{
    if (!strcmp(path, "-")) {
        uint8_t *p = malloc(sizeof(park_image));
        memcpy(p, park_image, sizeof(park_image));
        *len = sizeof(park_image);
        return p;
    }
    int fd = open(path, O_RDONLY);
    if (fd < 0)
        die("open %s: %s", path, strerror(errno));
    struct stat st;
    fstat(fd, &st);
    if (st.st_size <= 0 || st.st_size > UPC_ITCM_SIZE)
        die("%s: size %ld does not fit the %u byte ITCM", path,
            (long)st.st_size, UPC_ITCM_SIZE);
    uint8_t *p = malloc(st.st_size);
    if (read(fd, p, st.st_size) != st.st_size)
        die("read %s failed", path);
    close(fd);
    *len = st.st_size;
    return p;
}

static void
do_load(const char *io_path, const char *fm_path)
{
    size_t io_len, fm_len;
    uint8_t *io_img = read_image(io_path, &io_len);
    uint8_t *fm_img = read_image(fm_path, &fm_len);

    do_stop();
    dtcm_attach();
    printf("DTCM at %#lx\n", opt_dtcm);

    // Clear ITCMs, then our part of DTCM (IPC blocks, data, stacks)
    uint8_t *zero = calloc(1, UPC_ITCM_SIZE);
    itcm_write(UPC_DEV_IO, zero, UPC_ITCM_SIZE);
    itcm_write(UPC_DEV_FM, zero, UPC_ITCM_SIZE);
    free(zero);
    for (uint32_t off = IPC_FM_OFFSET; off < UPC_DTCM_SIZE; off += 4)
        wr32(dtcm, off, 0);
    barrier_full();

    itcm_write(UPC_DEV_IO, io_img, io_len);
    itcm_write(UPC_DEV_FM, fm_img, fm_len);
    printf("loaded IO core: %s (%zu bytes), FM core: %s (%zu bytes)\n",
           io_path, io_len, fm_path, fm_len);

    upc_ioctl(UPC_DEV_IO, UPC_IOC_RUN, 0);

    // Wait for firmware that uses the IPC protocol to report in
    int want_io = strcmp(io_path, "-"), want_fm = strcmp(fm_path, "-");
    double end = now_sec() + 2.0;
    while (now_sec() < end) {
        int io_ok = !want_io || ipc_block(0)->magic == IPC_MAGIC;
        int fm_ok = !want_fm || ipc_block(1)->magic == IPC_MAGIC;
        if (io_ok && fm_ok) {
            printf("cores started\n");
            return;
        }
        usleep(20000);
    }
    for (int fm = 0; fm < 2; fm++) {
        struct ipc_header *h = ipc_block(fm);
        if ((fm ? want_fm : want_io) && h->magic != IPC_MAGIC)
            printf("warning: %s core did not report (state %#x fault %u lr %#x)\n",
                   fm ? "FM" : "IO", h->state, h->fault_type, h->fault_lr);
    }
}

/****************************************************************
 * Info / probe / dump
 ****************************************************************/

static const char *
state_name(uint32_t s)
{
    switch (s) {
    case IPC_STATE_BOOT: return "boot";
    case IPC_STATE_RUNNING: return "running";
    case IPC_STATE_SHUTDOWN: return "shutdown";
    case IPC_STATE_PARKED: return "parked";
    case IPC_STATE_FAULT: return "FAULT";
    }
    return "?";
}

static void
do_info(void)
{
    dtcm_attach();
    printf("DTCM physical base: %#lx\n", opt_dtcm);
    for (int fm = 1; fm >= 0; fm--) {
        struct ipc_header *h = ipc_block(fm);
        printf("%s core: magic %s, fw %.4s, state %s, heartbeat %u",
               fm ? "FM" : "IO", h->magic == IPC_MAGIC ? "ok" : "none",
               (char *)&h->fw_id, state_name(h->state), h->heartbeat);
        if (h->state == IPC_STATE_FAULT)
            printf(", fault vector %u lr %#x spsr %#x", h->fault_type,
                   h->fault_lr, h->fault_spsr);
        printf("\n");
    }
}

static void
print_probe(int fm, struct probe_report *a, struct probe_report *b, double dt)
{
    printf("==== %s core probe ====\n", fm ? "FM" : "IO");
    if (b->magic != IPC_MAGIC) {
        printf("  no report\n");
        return;
    }
    printf("  loops %u (%.0f/s)  cpsr %#x  cp15 id %#x ctrl %#x tcm %#x\n",
           b->loops, (b->loops - a->loops) / dt, b->cpsr, b->cp15_id,
           b->cp15_ctrl, b->cp15_tcm);
    printf("  thumb %s  exec-from-DTCM %s  aborts %u\n",
           b->thumb_ok == 0x7b ? "OK" : "no", b->dtcm_exec_ok == 0xe1 ? "OK" : "no",
           b->aborts);
    printf("  inputs XIRD %08x XIRD1 %08x  (seen-high %08x %08x, seen-low %08x %08x)\n",
           b->xird, b->xird1, b->xird_or, b->xird1_or, ~b->xird_and, ~b->xird1_and);
    for (int i = 0; i < PROBE_NUM_TCM_TESTS; i++)
        if (b->tcm_probe_addr[i])
            printf("  tcm test %#010x: %s\n", b->tcm_probe_addr[i],
                   b->tcm_probe_result[i] == 1 ? "ok" :
                   b->tcm_probe_result[i] == 2 ? "abort" :
                   b->tcm_probe_result[i] == 3 ? "mismatch" : "-");
    if (b->adc_enabled) {
        for (int s = 0; s < 2; s++) {
            printf("  adc sel %d code %4u raw:", s, b->adc_code[s]);
            for (int i = 0; i < 10; i++)
                printf(" %u", b->adc_fifo[s][i] & 0x3fff);
            printf("\n");
        }
    }
    printf("  counter candidates (rate measured against Linux CLOCK_MONOTONIC):\n");
    for (int i = 0; i < PROBE_NUM_COUNTERS; i++) {
        struct probe_counter *ca = &a->ctr[i], *cb = &b->ctr[i];
        if (!cb->addr)
            continue;
        int32_t d = (int32_t)(cb->last - ca->last);
        printf("   %#010x  val %#010x  chg %u up %u down %u  rate %+.0f Hz\n",
               cb->addr, cb->last, cb->changes, cb->increases, cb->decreases,
               d / dt);
    }
}

static void
do_probe(double secs)
{
    dtcm_attach();
    struct probe_report a[2], b[2];
    for (int fm = 0; fm < 2; fm++)
        memcpy(&a[fm], (void *)((uint8_t *)ipc_block(fm) + IPC_PROBE_OFFSET),
               sizeof(a[fm]));
    double t0 = now_sec();
    usleep((useconds_t)(secs * 1e6));
    for (int fm = 0; fm < 2; fm++)
        memcpy(&b[fm], (void *)((uint8_t *)ipc_block(fm) + IPC_PROBE_OFFSET),
               sizeof(b[fm]));
    double dt = now_sec() - t0;
    print_probe(1, &a[1], &b[1], dt);
    print_probe(0, &a[0], &b[0], dt);
}

static void
do_dump(uint32_t off, uint32_t len)
{
    dtcm_attach();
    if (off >= UPC_DTCM_SIZE || len > UPC_DTCM_SIZE - off)
        die("range outside DTCM");
    for (uint32_t i = 0; i < len; i += 16) {
        printf("%05x:", off + i);
        for (uint32_t j = 0; j < 16 && i + j < len; j += 4)
            printf(" %08x", rd32(dtcm, off + i + j));
        printf("\n");
    }
}

/****************************************************************
 * Bridge: pty <-> DTCM rings
 ****************************************************************/

struct link {
    const char *name, *path;
    struct ipc_header *h;
    int master;
    uint32_t last_heartbeat;
    double heartbeat_time;
    int warned;
    int listen_fd;           // >= 0 for "tcp:PORT" links
};

// "tcp:PORT" link: listen on PORT, one client at a time (for testing the
// firmware from another machine with klippy's msgproto).
static int
tcp_listen(int port)
{
    int fd = socket(AF_INET, SOCK_STREAM, 0), one = 1;
    if (fd < 0)
        die("socket: %s", strerror(errno));
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
    struct sockaddr_in a = { .sin_family = AF_INET, .sin_port = htons(port),
                             .sin_addr.s_addr = htonl(INADDR_ANY) };
    if (bind(fd, (struct sockaddr *)&a, sizeof(a)) < 0 || listen(fd, 1) < 0)
        die("listen on port %d: %s", port, strerror(errno));
    fcntl(fd, F_SETFL, O_NONBLOCK);
    printf("listening on tcp port %d\n", port);
    return fd;
}

static void
tcp_check_accept(struct link *l)
{
    if (l->listen_fd < 0 || l->master >= 0)
        return;
    int c = accept(l->listen_fd, NULL, NULL);
    if (c < 0)
        return;
    int one = 1;
    setsockopt(c, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
    fcntl(c, F_SETFL, O_NONBLOCK);
    l->master = c;
    fprintf(stderr, "upctool: %s core: client connected\n", l->name);
}

static void
tcp_drop(struct link *l)
{
    close(l->master);
    l->master = -1;
    fprintf(stderr, "upctool: %s core: client disconnected\n", l->name);
}

static int
pty_create(const char *link_path)
{
    int m = posix_openpt(O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (m < 0 || grantpt(m) < 0 || unlockpt(m) < 0)
        die("pty: %s", strerror(errno));
    const char *slave = ptsname(m);
    // Raw mode on the slave side, as Klipper expects for a serial device
    int s = open(slave, O_RDWR | O_NOCTTY);
    if (s >= 0) {
        struct termios t;
        tcgetattr(s, &t);
        cfmakeraw(&t);
        tcsetattr(s, TCSANOW, &t);
        close(s);
    }
    unlink(link_path);
    if (symlink(slave, link_path) < 0)
        die("symlink %s -> %s: %s", link_path, slave, strerror(errno));
    // Let members of 'dialout' (the klipper user) open the pty
    struct group *gr = getgrnam("dialout");
    if (gr && chown(slave, -1, gr->gr_gid) < 0)
        fprintf(stderr, "upctool: chown %s: %s\n", slave, strerror(errno));
    chmod(slave, 0660);
    printf("%s -> %s\n", link_path, slave);
    return m;
}

// Host -> UPC: copy what fits from the pty into the rx ring
static int
pump_to_upc(struct link *l)
{
    struct ipc_header *h = l->h;
    if (l->master < 0)
        return 0;
    uint32_t head = h->rx_head, tail = h->rx_tail;
    uint32_t space = IPC_RING_SIZE - (head - tail);
    if (!space)
        return 0;
    uint8_t buf[IPC_RING_SIZE];
    ssize_t r = read(l->master, buf, space);
    if (r == 0 && l->listen_fd >= 0) {
        tcp_drop(l);
        return 0;
    }
    if (r <= 0)
        return 0;
    for (ssize_t i = 0; i < r; i++)
        h->rx[(head + i) & (IPC_RING_SIZE - 1)] = buf[i];
    barrier_full();
    h->rx_head = head + r;
    return r;
}

// UPC -> host: copy pending tx ring data into the pty
static int
pump_from_upc(struct link *l)
{
    struct ipc_header *h = l->h;
    if (l->master < 0)
        return 0;           // TCP link without client: keep data queued
    uint32_t head = h->tx_head, tail = h->tx_tail;
    uint32_t avail = head - tail;
    if (!avail)
        return 0;
    if (avail > IPC_RING_SIZE) {
        // Corrupt indices (firmware restarted) - resynchronize
        h->tx_tail = head;
        return 0;
    }
    barrier_full();
    uint8_t buf[IPC_RING_SIZE];
    for (uint32_t i = 0; i < avail; i++)
        buf[i] = h->tx[(tail + i) & (IPC_RING_SIZE - 1)];
    ssize_t w = write(l->master, buf, avail);
    if (w < 0 && l->listen_fd >= 0) {
        if (errno != EAGAIN)
            tcp_drop(l);
        return 0;
    }
    if (w < 0) {
        if (errno == EAGAIN || errno == EIO)
            // Nobody listening or pty buffer full - drop to avoid stalling
            // the firmware; Klipper retransmits/resyncs as needed.
            w = avail;
        else
            return 0;
    }
    barrier_full();
    h->tx_tail = tail + w;
    return w;
}

static void
check_alive(struct link *l, double now)
{
    uint32_t hb = l->h->heartbeat;
    if (hb != l->last_heartbeat || l->h->magic != IPC_MAGIC) {
        l->last_heartbeat = hb;
        l->heartbeat_time = now;
        l->warned = 0;
    } else if (!l->warned && now - l->heartbeat_time > 2.0) {
        fprintf(stderr, "upctool: %s core heartbeat stopped (state %s)\n",
                l->name, state_name(l->h->state));
        l->warned = 1;
    }
}

static void
on_signal(int sig)
{
    stop_requested = 1;
}

static void
do_bridge(const char *fm_path, const char *io_path, long poll_us)
{
    dtcm_attach();
    struct link links[2];
    int n = 0;
    if (fm_path)
        links[n++] = (struct link){ .name = "FM", .path = fm_path,
                                    .h = ipc_block(1), .master = -1,
                                    .listen_fd = -1 };
    if (io_path)
        links[n++] = (struct link){ .name = "IO", .path = io_path,
                                    .h = ipc_block(0), .master = -1,
                                    .listen_fd = -1 };
    for (int i = 0; i < n; i++) {
        if (links[i].h->magic != IPC_MAGIC)
            fprintf(stderr, "upctool: warning: %s core firmware not running yet\n",
                    links[i].name);
        if (!strncmp(links[i].path, "tcp:", 4))
            links[i].listen_fd = tcp_listen(atoi(links[i].path + 4));
        else
            links[i].master = pty_create(links[i].path);
    }
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    signal(SIGPIPE, SIG_IGN);
    fflush(stdout);

    // The vendor kernel has HZ=100 and no high resolution timers, so any
    // sleep lasts at least 10 ms. After traffic, keep spinning (with
    // sched_yield) for a short while to cut latency during bursts.
    double busy_until = 0;
    while (!stop_requested) {
        int moved = 0;
        double now = now_sec();
        for (int i = 0; i < n; i++) {
            tcp_check_accept(&links[i]);
            moved += pump_to_upc(&links[i]);
            moved += pump_from_upc(&links[i]);
            check_alive(&links[i], now);
        }
        if (moved)
            busy_until = now + 0.005;
        if (now < busy_until || poll_us == 0) {
            sched_yield();
            continue;
        }
        struct pollfd pfd[2];
        for (int i = 0; i < n; i++)
            pfd[i] = (struct pollfd){ .fd = links[i].master, .events = POLLIN };
        int ms = poll_us / 1000;
        if (poll(pfd, n, ms > 0 ? ms : 1) > 0) {
            for (int i = 0; i < n; i++)
                if (pfd[i].revents & POLLHUP)
                    // Slave closed (klippy restarting) - avoid a hot loop
                    usleep(poll_us);
        }
    }
    for (int i = 0; i < n; i++)
        if (links[i].listen_fd < 0)
            unlink(links[i].path);
}

/****************************************************************
 * main
 ****************************************************************/

static void
usage(void)
{
    fprintf(stderr,
        "usage: upctool [--dtcm ADDR] [--force] COMMAND ...\n"
        "  info | safe | stop | load IO.bin|- FM.bin|- | probe [secs]\n"
        "  bridge [-f FM_PTY|tcp:PORT] [-i IO_PTY|tcp:PORT] [-p POLL_US]\n"
        "  dump OFF LEN\n");
    exit(2);
}

int
main(int argc, char **argv)
{
    int i = 1;
    for (; i < argc && !strncmp(argv[i], "--", 2); i++) {
        if (!strcmp(argv[i], "--force"))
            opt_force = 1;
        else if (!strcmp(argv[i], "--dtcm") && i + 1 < argc)
            opt_dtcm = strtoul(argv[++i], NULL, 0);
        else
            usage();
    }
    if (i >= argc)
        usage();
    const char *cmd = argv[i++];
    if (!strcmp(cmd, "info")) {
        do_info();
    } else if (!strcmp(cmd, "safe")) {
        do_safe();
    } else if (!strcmp(cmd, "stop")) {
        do_stop();
    } else if (!strcmp(cmd, "load") && argc - i == 2) {
        do_load(argv[i], argv[i + 1]);
    } else if (!strcmp(cmd, "probe")) {
        do_probe(i < argc ? atof(argv[i]) : 1.0);
    } else if (!strcmp(cmd, "dump") && argc - i == 2) {
        do_dump(strtoul(argv[i], NULL, 0), strtoul(argv[i + 1], NULL, 0));
    } else if (!strcmp(cmd, "bridge")) {
        const char *fm = NULL, *io = NULL;
        long poll_us = 2000;
        for (; i < argc; i++) {
            if (!strcmp(argv[i], "-f") && i + 1 < argc)
                fm = argv[++i];
            else if (!strcmp(argv[i], "-i") && i + 1 < argc)
                io = argv[++i];
            else if (!strcmp(argv[i], "-p") && i + 1 < argc)
                poll_us = atol(argv[++i]);
            else
                usage();
        }
        if (!fm && !io)
            fm = "/tmp/klipper_upc_fm", io = "/tmp/klipper_upc_io";
        do_bridge(fm, io, poll_us);
    } else {
        usage();
    }
    return 0;
}
