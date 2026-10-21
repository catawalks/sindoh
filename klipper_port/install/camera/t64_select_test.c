// Probe how time64 glibc calls behave on kernel 3.2 (build with and without
// -D_TIME_BITS=64 -D_FILE_OFFSET_BITS=64 and compare).
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <sys/select.h>
#include <time.h>
#include <unistd.h>

static void
report(const char *what, int r)
{
    printf("%-34s r=%d %s\n", what, r, r < 0 ? strerror(errno) : "");
}

int
main(void)
{
    printf("sizeof(time_t)=%zu sizeof(struct timeval)=%zu\n", sizeof(time_t), sizeof(struct timeval));
    struct timeval tv = { 0, 100000 };
    report("select(0, 100 ms)", select(0, NULL, NULL, NULL, &tv));
    int fd = open("/dev/video0", O_RDWR | O_NONBLOCK);
    report("open /dev/video0", fd);
    if (fd >= 0) {
        fd_set rf;
        FD_ZERO(&rf);
        FD_SET(fd, &rf);
        tv.tv_sec = 0;
        tv.tv_usec = 100000;
        report("select(video0, 100 ms)", select(fd + 1, &rf, NULL, NULL, &tv));
        struct pollfd p = { fd, POLLIN, 0 };
        report("poll(video0, 100 ms)", poll(&p, 1, 100));
        struct timespec ts = { 0, 100000000 };
        report("ppoll(video0, 100 ms)", ppoll(&p, 1, &ts, NULL));
        close(fd);
    }
    struct timespec now;
    report("clock_gettime(MONOTONIC)", clock_gettime(CLOCK_MONOTONIC, &now));
    return 0;
}
