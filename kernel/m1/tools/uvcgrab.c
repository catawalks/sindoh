// SPDX-License-Identifier: GPL-2.0
/*
 * uvcgrab: save one MJPEG frame from a V4L2 capture device.
 *
 *   uvcgrab [/dev/video0] [out.jpg] [width height]
 *
 * Asks for MJPEG at 640x480 by default, skips the first frames while the
 * camera adjusts its exposure, and writes one frame.
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#define NBUF	4
#define SKIP	8

static int xioctl(int fd, unsigned long req, void *arg)
{
	int r;

	do
		r = ioctl(fd, req, arg);
	while (r < 0 && errno == EINTR);
	return r;
}

static void die(const char *what)
{
	perror(what);
	exit(1);
}

int main(int argc, char **argv)
{
	const char *dev = argc > 1 ? argv[1] : "/dev/video0";
	const char *out = argc > 2 ? argv[2] : "/tmp/frame.jpg";
	unsigned int w = argc > 4 ? atoi(argv[3]) : 640;
	unsigned int h = argc > 4 ? atoi(argv[4]) : 480;
	struct v4l2_requestbuffers req = { 0 };
	struct v4l2_format fmt = { 0 };
	struct v4l2_buffer buf;
	void *mem[NBUF];
	enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	unsigned int i;
	FILE *f;
	int fd;

	fd = open(dev, O_RDWR);
	if (fd < 0)
		die(dev);

	fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	fmt.fmt.pix.width = w;
	fmt.fmt.pix.height = h;
	fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_MJPEG;
	fmt.fmt.pix.field = V4L2_FIELD_ANY;
	if (xioctl(fd, VIDIOC_S_FMT, &fmt) < 0)
		die("VIDIOC_S_FMT");
	printf("format %.4s %ux%u\n", (char *)&fmt.fmt.pix.pixelformat,
	       fmt.fmt.pix.width, fmt.fmt.pix.height);

	req.count = NBUF;
	req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	req.memory = V4L2_MEMORY_MMAP;
	if (xioctl(fd, VIDIOC_REQBUFS, &req) < 0 || req.count < 1)
		die("VIDIOC_REQBUFS");

	for (i = 0; i < req.count; i++) {
		memset(&buf, 0, sizeof(buf));
		buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
		buf.memory = V4L2_MEMORY_MMAP;
		buf.index = i;
		if (xioctl(fd, VIDIOC_QUERYBUF, &buf) < 0)
			die("VIDIOC_QUERYBUF");
		mem[i] = mmap(NULL, buf.length, PROT_READ | PROT_WRITE,
			      MAP_SHARED, fd, buf.m.offset);
		if (mem[i] == MAP_FAILED)
			die("mmap");
		if (xioctl(fd, VIDIOC_QBUF, &buf) < 0)
			die("VIDIOC_QBUF");
	}

	if (xioctl(fd, VIDIOC_STREAMON, &type) < 0)
		die("VIDIOC_STREAMON");

	for (i = 0; i <= SKIP; i++) {
		memset(&buf, 0, sizeof(buf));
		buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
		buf.memory = V4L2_MEMORY_MMAP;
		if (xioctl(fd, VIDIOC_DQBUF, &buf) < 0)
			die("VIDIOC_DQBUF");
		if (i < SKIP && xioctl(fd, VIDIOC_QBUF, &buf) < 0)
			die("VIDIOC_QBUF");
	}

	f = fopen(out, "wb");
	if (!f)
		die(out);
	fwrite(mem[buf.index], 1, buf.bytesused, f);
	fclose(f);
	printf("%s: %u bytes\n", out, buf.bytesused);

	xioctl(fd, VIDIOC_STREAMOFF, &type);
	close(fd);
	return 0;
}
