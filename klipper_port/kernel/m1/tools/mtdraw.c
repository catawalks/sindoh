// SPDX-License-Identifier: GPL-2.0
/*
 * mtdraw: read an MTD character device in raw mode (no ECC), to stdout.
 *
 *   mtdraw /dev/mtdN [offset [length]]
 *
 * Sets MTDFILEMODE to MTD_FILE_MODE_RAW, so each page's data area comes
 * back as stored, without ECC correction (or miscorrection), the way
 * `nanddump --noecc` reads it. Read-only: opens the device O_RDONLY and
 * issues no other ioctl.
 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

/* <mtd/mtd-abi.h> */
#define MTDFILEMODE		_IO('M', 19)
#define MTD_FILE_MODE_RAW	3

int main(int argc, char **argv)
{
	static char buf[65536];
	long long off = 0, len = -1;
	int fd;

	if (argc < 2 || argc > 4) {
		fprintf(stderr, "usage: mtdraw /dev/mtdN [offset [length]]\n");
		return 2;
	}
	if (argc > 2)
		off = strtoll(argv[2], NULL, 0);
	if (argc > 3)
		len = strtoll(argv[3], NULL, 0);

	fd = open(argv[1], O_RDONLY);
	if (fd < 0) {
		fprintf(stderr, "mtdraw: %s: %s\n", argv[1], strerror(errno));
		return 1;
	}
	if (ioctl(fd, MTDFILEMODE, MTD_FILE_MODE_RAW) < 0) {
		fprintf(stderr, "mtdraw: MTDFILEMODE raw: %s\n", strerror(errno));
		return 1;
	}
	if (lseek(fd, off, SEEK_SET) < 0) {
		fprintf(stderr, "mtdraw: seek: %s\n", strerror(errno));
		return 1;
	}
	while (len != 0) {
		size_t want = sizeof(buf);
		ssize_t n;

		if (len > 0 && (long long)want > len)
			want = len;
		n = read(fd, buf, want);
		if (n < 0) {
			fprintf(stderr, "mtdraw: read at %lld: %s\n", off,
				strerror(errno));
			return 1;
		}
		if (n == 0)
			break;
		if (write(1, buf, n) != n)
			return 1;
		off += n;
		if (len > 0)
			len -= n;
	}
	return 0;
}
