// SPDX-License-Identifier: GPL-2.0
/*
 * RTC of the Marvell 88PA61x0 printer SoCs (88PA6170 in the Sindoh DP200).
 * Layout and setup from the vendor driver (gogin_rtc_*, 3.2):
 *
 *   +0x00   control: 3 written at setup, reads 0xfc once it runs
 *   +0x04   cleared at setup, reads 0xc0
 *   +0x08   cleared at setup, reads 0xc0
 *   +0x0c   time: seconds counter, read as one 32-bit word; written twice,
 *           125 us apart, to set it (gogin_rtc_set_time)
 *   +0x10   alarm (seconds), cleared at setup
 *   +0x14   cleared at setup
 *   +0x1c   cleared at setup (then 500 ms)
 *   +0x20   0x0008ac1c first, 0x00ffffff once the setup verifies
 *   APB configuration 0xf8000200: bit 30 cleared first (stock 0x80000080,
 *   U-Boot 0xc0000080)
 *
 * The setup only runs with "marvell,vendor-setup" in the DT (and the "apb"
 * range); set_time only exists with "marvell,set-time". No alarm, no
 * interrupt.
 */
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/rtc.h>
#include <linux/spinlock.h>

#define MV61X0_RTC_CTRL		0x00
#define MV61X0_RTC_R04		0x04
#define MV61X0_RTC_R08		0x08
#define MV61X0_RTC_TIME		0x0c
#define MV61X0_RTC_ALARM	0x10
#define MV61X0_RTC_R14		0x14
#define MV61X0_RTC_R1C		0x1c
#define MV61X0_RTC_R20		0x20
#define MV61X0_RTC_R20_SETUP	0x0008ac1c
#define MV61X0_RTC_R20_RUN	0x00ffffff
#define MV61X0_APB_RTC_GATE	((u32)BIT(30))

struct mv61x0_rtc {
	void __iomem *base;
	struct rtc_device *rtc;
	spinlock_t lock;
};

/* The vendor's write: a barrier, the write, then __const_udelay(0x83126) */
static void mv61x0_rtc_wr(struct mv61x0_rtc *mr, u32 off, u32 val)
{
	writel(val, mr->base + off);
	udelay(125);
}

static int mv61x0_rtc_setup(struct device *dev, struct mv61x0_rtc *mr)
{
	struct platform_device *pdev = to_platform_device(dev);
	struct resource *res;
	void __iomem *apb;
	int try;

	res = platform_get_resource_byname(pdev, IORESOURCE_MEM, "apb");
	if (!res)
		return -EINVAL;
	/* No request: the APB block is shared (the UPC driver uses +0x180) */
	apb = devm_ioremap(dev, res->start, resource_size(res));
	if (!apb)
		return -ENOMEM;
	dev_info(dev, "setup: APB %08x -> %08x\n", readl(apb),
		 readl(apb) & ~MV61X0_APB_RTC_GATE);
	writel(readl(apb) & ~MV61X0_APB_RTC_GATE, apb);

	for (try = 0; try < 3; try++) {
		mv61x0_rtc_wr(mr, MV61X0_RTC_R20, MV61X0_RTC_R20_SETUP);
		mv61x0_rtc_wr(mr, MV61X0_RTC_R1C, 0);
		msleep(500);
		mv61x0_rtc_wr(mr, MV61X0_RTC_R04, 0);
		mv61x0_rtc_wr(mr, MV61X0_RTC_ALARM, 0);
		mv61x0_rtc_wr(mr, MV61X0_RTC_R08, 0);
		mv61x0_rtc_wr(mr, MV61X0_RTC_R14, 0);
		mv61x0_rtc_wr(mr, MV61X0_RTC_CTRL, 3);

		if (readl(mr->base + MV61X0_RTC_CTRL) == 0xfc &&
		    readl(mr->base + MV61X0_RTC_ALARM) == 0 &&
		    readl(mr->base + MV61X0_RTC_R04) == 0xc0 &&
		    readl(mr->base + MV61X0_RTC_R14) == 0 &&
		    readl(mr->base + MV61X0_RTC_R08) == 0xc0 &&
		    readl(mr->base + MV61X0_RTC_R1C) == 0) {
			mv61x0_rtc_wr(mr, MV61X0_RTC_R20, MV61X0_RTC_R20_RUN);
			return 0;
		}
		dev_warn(dev, "setup try %d: ctrl %08x 04 %08x 08 %08x 10 %08x 14 %08x 1c %08x\n",
			 try + 1, readl(mr->base + MV61X0_RTC_CTRL),
			 readl(mr->base + MV61X0_RTC_R04),
			 readl(mr->base + MV61X0_RTC_R08),
			 readl(mr->base + MV61X0_RTC_ALARM),
			 readl(mr->base + MV61X0_RTC_R14),
			 readl(mr->base + MV61X0_RTC_R1C));
	}
	return -EIO;
}

static int mv61x0_rtc_read_time(struct device *dev, struct rtc_time *tm)
{
	struct mv61x0_rtc *mr = dev_get_drvdata(dev);

	rtc_time64_to_tm(readl(mr->base + MV61X0_RTC_TIME), tm);
	return 0;
}

/* gogin_rtc_set_time: the seconds value written twice, 125 us apart */
static int mv61x0_rtc_set_time(struct device *dev, struct rtc_time *tm)
{
	struct mv61x0_rtc *mr = dev_get_drvdata(dev);
	time64_t t = rtc_tm_to_time64(tm);

	if (t < 0 || t > U32_MAX)
		return -ERANGE;
	spin_lock_irq(&mr->lock);
	mv61x0_rtc_wr(mr, MV61X0_RTC_TIME, t);
	mv61x0_rtc_wr(mr, MV61X0_RTC_TIME, t);
	spin_unlock_irq(&mr->lock);
	return 0;
}

static const struct rtc_class_ops mv61x0_rtc_ops = {
	.read_time	= mv61x0_rtc_read_time,
};

static const struct rtc_class_ops mv61x0_rtc_rw_ops = {
	.read_time	= mv61x0_rtc_read_time,
	.set_time	= mv61x0_rtc_set_time,
};

static int mv61x0_rtc_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct mv61x0_rtc *mr;
	u32 t0, t1;
	int ret;

	mr = devm_kzalloc(dev, sizeof(*mr), GFP_KERNEL);
	if (!mr)
		return -ENOMEM;
	mr->base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(mr->base))
		return PTR_ERR(mr->base);
	platform_set_drvdata(pdev, mr);
	spin_lock_init(&mr->lock);

	if (of_property_read_bool(dev->of_node, "marvell,vendor-setup")) {
		ret = mv61x0_rtc_setup(dev, mr);
		dev_info(dev, "vendor setup %s\n", ret ? "failed" : "done");
	}

	t0 = readl(mr->base + MV61X0_RTC_TIME);
	mdelay(2100);
	t1 = readl(mr->base + MV61X0_RTC_TIME);
	dev_info(dev, "control %08x, time %08x -> %08x over 2.1 s%s\n",
		 readl(mr->base + MV61X0_RTC_CTRL), t0, t1,
		 t1 == t0 ? " (not counting)" : "");

	mr->rtc = devm_rtc_allocate_device(dev);
	if (IS_ERR(mr->rtc))
		return PTR_ERR(mr->rtc);
	if (of_property_read_bool(dev->of_node, "marvell,set-time")) {
		mr->rtc->ops = &mv61x0_rtc_rw_ops;
		dev_info(dev, "set_time enabled\n");
	} else {
		mr->rtc->ops = &mv61x0_rtc_ops;
	}
	mr->rtc->range_max = U32_MAX;

	return devm_rtc_register_device(mr->rtc);
}

static const struct of_device_id mv61x0_rtc_of_match[] = {
	{ .compatible = "marvell,88pa6170-rtc" },
	{ }
};
MODULE_DEVICE_TABLE(of, mv61x0_rtc_of_match);

static struct platform_driver mv61x0_rtc_driver = {
	.probe	= mv61x0_rtc_probe,
	.driver	= {
		.name		= "mv61x0-rtc",
		.of_match_table	= mv61x0_rtc_of_match,
	},
};
module_platform_driver(mv61x0_rtc_driver);

MODULE_DESCRIPTION("Marvell 88PA61x0 RTC");
MODULE_LICENSE("GPL");
