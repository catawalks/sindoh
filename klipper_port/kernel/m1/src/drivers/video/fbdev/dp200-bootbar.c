// SPDX-License-Identifier: GPL-2.0
/*
 * Sindoh DP200: the boot progress bar over U-Boot's boot logo, as the vendor
 * kernel's panel driver draws it (mv61tft rodin_progress_bar, from the 3.2
 * kernel image: docs/kernel/debian_root_boot.md).
 *
 * In the 800x480 RGB565 buffer (the panel is mounted in portrait, so this
 * is a horizontal bar on screen): a rounded outline at columns 306-319, rows
 * 90-369, then filled one row at a time from row 92 to 367 over boot_time
 * seconds. The fill stays when it is done. White for bar_color=0, black for
 * 1. Both come from the U-Boot environment (read-only, MTD "u-boot-env"),
 * as the vendor kernel got them from U-Boot's bootargs (mv61tft.boot_time,
 * mv61tft.bar_color). Defaults: 17 s, white.
 *
 * On screen (portrait, 480x800, the buffer turned 90 degrees clockwise, as
 * the screen app does): a buffer row is the screen x, and buffer column c is
 * screen y = 799 - c. The vendor's bar spans screen x 90-369 (90 px left,
 * 110 px right: not centered) and y 480-493. The bar is moved by
 * bar_shift_x (right) and bar_shift_y (down) screen pixels, both from the
 * U-Boot env (the boot-logo app sets them). Defaults: x 10 (centered), y 0.
 * 0/0 is the stock spot; the stock kernel itself ignores them.
 *
 * It only writes into the framebuffer memory of the simple-framebuffer node
 * (/chosen), no hardware registers. Writing 1 to the "stop" parameter
 * (/sys/module/dp200_bootbar/parameters/stop) ends it and waits for the
 * thread, so nothing is drawn after the screen app takes over.
 */
#include <linux/crc32.h>
#include <linux/delay.h>
#include <linux/err.h>
#include <linux/init.h>
#include <linux/io.h>
#include <linux/kthread.h>
#include <linux/module.h>
#include <linux/mtd/mtd.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/unaligned.h>
#include <linux/vmalloc.h>

/* geometry of rodin_progress_bar, in buffer pixels */
#define BAR_X0		306	/* outline columns 306 and 319 */
#define BAR_X1		319
#define BAR_Y0		90	/* outline rows 90 and 369 */
#define BAR_Y1		369
#define FILL_Y0		92	/* filled rows 92..367 */
#define FILL_Y1		368
#define STEPS		279	/* the vendor's time divisor */

#define ENV_PART	"u-boot-env"
#define ENV_MAX		0x20000

static int bar_color = -1;	/* -1: from the U-Boot env */
module_param(bar_color, int, 0444);
MODULE_PARM_DESC(bar_color, "0 white bar, 1 black bar (default: U-Boot env bar_color)");
static int boot_time = -1;	/* -1: from the U-Boot env */
module_param(boot_time, int, 0444);
MODULE_PARM_DESC(boot_time, "seconds to fill the bar (default: U-Boot env boot_time)");
#define SHIFT_UNSET	INT_MIN
static int shift_x = SHIFT_UNSET;
module_param(shift_x, int, 0444);
MODULE_PARM_DESC(shift_x, "screen pixels right (default: U-Boot env bar_shift_x, else 10 = centered)");
static int shift_y = SHIFT_UNSET;
module_param(shift_y, int, 0444);
MODULE_PARM_DESC(shift_y, "screen pixels down (default: U-Boot env bar_shift_y, else 0)");

static DEFINE_MUTEX(bar_lock);
static struct task_struct *bar_task;
static void __iomem *fb;
static u32 stride;

/* vendor coordinates: x = buffer column, y = buffer row */
static void px(int x, int y, u16 c)
{
	writew(c, fb + (y + shift_x) * stride + (x - shift_y) * 2);
}

static void hline(int y, int x0, int x1, u16 c)	/* x1 exclusive */
{
	for (; x0 < x1; x0++)
		px(x0, y, c);
}

static void vline(int x, int y0, int y1, u16 c)	/* y1 exclusive */
{
	for (; y0 < y1; y0++)
		px(x, y0, c);
}

/* "name=value" from the env data (after the CRC word); def if absent */
static int env_int(const char *env, size_t len, const char *name, int def)
{
	size_t n = strlen(name), i = 0;
	int v;

	while (i < len && env[i]) {
		const char *e = env + i;
		size_t l = strnlen(e, len - i);

		if (l > n && !strncmp(e, name, n) && e[n] == '=' &&
		    !kstrtoint(e + n + 1, 10, &v))
			return v;
		i += l + 1;
	}
	return def;
}

static void read_env(void)
{
	struct mtd_info *mtd = ERR_PTR(-ENODEV);
	size_t len, sz, got = 0;
	char *buf;
	int i;

	/* the NAND may probe after this thread starts */
	for (i = 0; i < 50 && IS_ERR(mtd) && !kthread_should_stop(); i++) {
		mtd = get_mtd_device_nm(ENV_PART);
		if (IS_ERR(mtd))
			msleep(100);
	}
	if (IS_ERR(mtd)) {
		pr_info("dp200-bootbar: no %s partition, defaults\n", ENV_PART);
		return;
	}
	len = min_t(u64, mtd->size, ENV_MAX);
	buf = vmalloc(len);
	if (buf && mtd_read(mtd, 0, len, &got, buf) >= 0 && got == len) {
		/* U-Boot's CONFIG_ENV_SIZE isn't known: the CRC says which */
		for (sz = len; sz >= 0x1000; sz /= 2)
			if (get_unaligned_le32(buf) == ~crc32_le(~0, buf + 4, sz - 4))
				break;
		if (sz < 0x1000) {
			pr_info("dp200-bootbar: %s CRC not found, defaults\n", ENV_PART);
		} else {
			const char *env = buf + 4;

			sz -= 4;
			if (bar_color < 0)
				bar_color = env_int(env, sz, "bar_color", -1);
			if (boot_time < 0)
				boot_time = env_int(env, sz, "boot_time", -1);
			if (shift_x == SHIFT_UNSET)
				shift_x = env_int(env, sz, "bar_shift_x", SHIFT_UNSET);
			if (shift_y == SHIFT_UNSET)
				shift_y = env_int(env, sz, "bar_shift_y", SHIFT_UNSET);
		}
	}
	vfree(buf);
	put_mtd_device(mtd);
}

static int bar_thread(void *unused)
{
	u16 c;
	int y;
	unsigned int ms;

	read_env();
	if (bar_color < 0)
		bar_color = 0;
	if (boot_time <= 0)
		boot_time = 17;
	if (shift_x == SHIFT_UNSET)
		shift_x = 10;
	if (shift_y == SHIFT_UNSET)
		shift_y = 0;
	/* stay in the 800x480 buffer */
	shift_x = clamp(shift_x, -BAR_Y0, 479 - BAR_Y1);
	shift_y = clamp(shift_y, BAR_X1 - 799, BAR_X0);
	c = bar_color ? 0x0000 : 0xffff;
	ms = boot_time * 1000 / STEPS;
	pr_info("dp200-bootbar: %s bar, %d s, shift x %+d y %+d\n",
		bar_color ? "black" : "white", boot_time, shift_x, shift_y);

	/* the outline, rounded corners: as the vendor draws it */
	hline(BAR_Y0, BAR_X0 + 2, BAR_X1 - 1, c);
	px(BAR_X0 + 1, BAR_Y0 + 1, c);
	px(BAR_X1 - 1, BAR_Y0 + 1, c);
	px(BAR_X0 + 1, BAR_Y1 - 1, c);
	px(BAR_X1 - 1, BAR_Y1 - 1, c);
	hline(BAR_Y1, BAR_X0 + 2, BAR_X1 - 1, c);
	vline(BAR_X0, FILL_Y0, FILL_Y1, c);
	vline(BAR_X1, FILL_Y0, FILL_Y1, c);
	hline(BAR_Y0 + 1, BAR_X0 + 2, BAR_X1 - 1, c);

	for (y = FILL_Y0; y < FILL_Y1; y++) {
		hline(y, BAR_X0, BAR_X1, c);
		if (msleep_interruptible(ms) || kthread_should_stop())
			goto out;
	}
	hline(FILL_Y1, BAR_X0 + 2, BAR_X1 - 1, c);
out:
	/* kthread_stop() needs the thread to still exist: wait for it */
	while (!kthread_should_stop())
		schedule_timeout_interruptible(HZ);
	return 0;
}

static int stop_set(const char *val, const struct kernel_param *kp)
{
	bool stop;
	int ret = kstrtobool(val, &stop);

	if (ret || !stop)
		return ret;
	mutex_lock(&bar_lock);
	if (bar_task) {
		kthread_stop(bar_task);
		bar_task = NULL;
		pr_info("dp200-bootbar: stopped\n");
	}
	mutex_unlock(&bar_lock);
	return 0;
}

static int stop_get(char *buf, const struct kernel_param *kp)
{
	return sysfs_emit(buf, "%d\n", !READ_ONCE(bar_task));
}

static const struct kernel_param_ops stop_ops = {
	.set = stop_set,
	.get = stop_get,
};
module_param_cb(stop, &stop_ops, NULL, 0644);
MODULE_PARM_DESC(stop, "write 1 to end the bar (the screen app does, at start)");

static int __init dp200_bootbar_init(void)
{
	struct device_node *np;
	struct resource res;
	u32 w = 0, h = 0;
	const char *fmt;
	int ret;

	if (!of_machine_is_compatible("sindoh,dp200"))
		return 0;
	np = of_find_compatible_node(NULL, NULL, "simple-framebuffer");
	if (!np)
		return 0;
	ret = of_address_to_resource(np, 0, &res);
	if (!ret && (of_property_read_u32(np, "width", &w) ||
		     of_property_read_u32(np, "height", &h) ||
		     of_property_read_u32(np, "stride", &stride) ||
		     of_property_read_string(np, "format", &fmt) ||
		     strcmp(fmt, "r5g6b5")))
		ret = -EINVAL;
	of_node_put(np);
	/* the vendor geometry needs its 800x480 RGB565 buffer */
	if (ret || w != 800 || h != 480 || stride < w * 2 ||
	    resource_size(&res) < (resource_size_t)stride * h) {
		pr_info("dp200-bootbar: no 800x480 r5g6b5 framebuffer, no bar\n");
		return 0;
	}
	fb = ioremap_wc(res.start, (resource_size_t)stride * h);
	if (!fb)
		return -ENOMEM;
	mutex_lock(&bar_lock);
	bar_task = kthread_run(bar_thread, NULL, "dp200-bootbar");
	if (IS_ERR(bar_task)) {
		ret = PTR_ERR(bar_task);
		bar_task = NULL;
	}
	mutex_unlock(&bar_lock);
	return ret;
}
device_initcall(dp200_bootbar_init);

MODULE_DESCRIPTION("Sindoh DP200 boot progress bar (as the vendor mv61tft)");
MODULE_LICENSE("GPL");
