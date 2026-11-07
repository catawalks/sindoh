/*
 * dp200-hold: wait for a deliberate press-and-hold on the touchscreen, for
 * the nandboot initramfs's "recover?" prompt (initramfs/nandboot/init).
 *
 *   dp200-hold DEVICE WINDOW_S HOLD_S
 *
 * Exit 0 when a finger goes down within WINDOW_S seconds and stays down
 * HOLD_S seconds; 1 when the window ends first; 2 on an error.
 *
 * Only a fresh press counts (2026-11-07: the old prompt read any queued
 * event as a touch and started a revert unasked). Everything already queued
 * when the device is opened is thrown away, and so is everything in the
 * first half second, and a press only counts once the screen has been
 * quiet for 0.3 s after that (a controller streaming phantom samples never
 * arms it). The touch rule is the screen app's (dp200_screen.py
 * Touch): a finger is down while SYN frames carry a position (ABS_MT_X/Y
 * or ABS_X/Y), two such frames make a press, and an empty frame, 0.3 s
 * without one, or BTN_TOUCH 0 is a release, which starts over. Progress
 * goes to stdout ("down", "up", "held").
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

#define DRAIN_S 0.5
#define SILENCE_S 0.3

static double now(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec + t.tv_nsec / 1e9;
}

int main(int argc, char **argv)
{
	struct input_event ev;
	struct pollfd p;
	double window, hold, t0, end, down = 0, last = 0, any = 0;
	int frames = 0, pos = 0, armed = 0;
	ssize_t n;
	int fd;

	if (argc != 4) {
		fprintf(stderr, "usage: %s DEVICE WINDOW_S HOLD_S\n", argv[0]);
		return 2;
	}
	window = atof(argv[2]);
	hold = atof(argv[3]);
	fd = open(argv[1], O_RDONLY | O_NONBLOCK);
	if (fd < 0) {
		perror(argv[1]);
		return 2;
	}
	t0 = now();
	end = t0 + DRAIN_S + window;
	p.fd = fd;
	p.events = POLLIN;
	for (;;) {
		double t = now();

		if (down && t - down >= hold) {
			puts("held");
			return 0;
		}
		if (frames && t - last > SILENCE_S) {	/* silence: lifted */
			if (down)
				puts("up");
			down = 0;
			frames = 0;
			fflush(stdout);
		}
		if (!armed && t - t0 >= DRAIN_S && t - any > SILENCE_S)
			armed = 1;
		if (t >= end && !down)
			return 1;
		if (poll(&p, 1, 50) < 0 && errno != EINTR) {
			perror("poll");
			return 2;
		}
		while ((n = read(fd, &ev, sizeof(ev))) == sizeof(ev)) {
			t = now();
			if (ev.type == EV_SYN && pos)
				any = t;
			if (t - t0 < DRAIN_S || !armed) {
				pos = ev.type == EV_SYN ? 0 : pos || (ev.type == EV_ABS &&
				      (ev.code == ABS_MT_POSITION_X || ev.code == ABS_MT_POSITION_Y ||
				       ev.code == ABS_X || ev.code == ABS_Y));
				continue;	/* queued, too early or not armed yet */
			}
			if (ev.type == EV_ABS && (ev.code == ABS_MT_POSITION_X ||
			    ev.code == ABS_MT_POSITION_Y || ev.code == ABS_X || ev.code == ABS_Y)) {
				pos = 1;
			} else if (ev.type == EV_SYN && ev.code == SYN_REPORT) {
				if (pos) {
					last = t;
					if (++frames == 2 && t < end) {
						down = t;
						puts("down");
					}
				} else if (frames) {	/* empty frame: lifted */
					if (down)
						puts("up");
					down = 0;
					frames = 0;
				}
				pos = 0;
			} else if (ev.type == EV_KEY && ev.code == BTN_TOUCH && ev.value == 0 && frames) {
				if (down)
					puts("up");
				down = 0;
				frames = 0;
			}
			fflush(stdout);
		}
		if (n < 0 && errno != EAGAIN && errno != EINTR) {
			perror("read");
			return 2;
		}
		if (n == 0)		/* no writer (a FIFO in the test): wait */
			usleep(20000);
	}
}
