// SPDX-License-Identifier: GPL-2.0
/*
 * RTC of the Marvell 88PA61x0 printer SoCs (88PA6170 in the Sindoh DP200),
 * read-only. Layout from the vendor driver (gogin_rtc_*, 3.2):
 *
 *   +0x00   control (the vendor probe ends its setup by writing 3)
 *   +0x0c   time: seconds counter; read for the time, written (twice,
 *           1 ms apart) to set it
 *   +0x10   alarm (seconds)
 *   +0x04, +0x08, +0x14, +0x1c, +0x20: written by the vendor probe
 *
 * This driver only reads +0x00 and +0x0c: no set_time, no alarm, no
 * interrupt, nothing written. The vendor probe's setup sequence (and a bit
 * it clears in the APB configuration at 0xf8000200) is a separate proposal.
 * The stock kernel sets the time to 1970 at every boot, so there is
 * probably no backup battery.
 */
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/rtc.h>

#define MV61X0_RTC_CTRL		0x00
#define MV61X0_RTC_TIME		0x0c

struct mv61x0_rtc {
	void __iomem *base;
	struct rtc_device *rtc;
};

static int mv61x0_rtc_read_time(struct device *dev, struct rtc_time *tm)
{
	struct mv61x0_rtc *mr = dev_get_drvdata(dev);

	rtc_time64_to_tm(readl(mr->base + MV61X0_RTC_TIME), tm);
	return 0;
}

static const struct rtc_class_ops mv61x0_rtc_ops = {
	.read_time	= mv61x0_rtc_read_time,
};

static int mv61x0_rtc_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct mv61x0_rtc *mr;
	u32 t0, t1;

	mr = devm_kzalloc(dev, sizeof(*mr), GFP_KERNEL);
	if (!mr)
		return -ENOMEM;
	mr->base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(mr->base))
		return PTR_ERR(mr->base);
	platform_set_drvdata(pdev, mr);

	t0 = readl(mr->base + MV61X0_RTC_TIME);
	mdelay(1100);
	t1 = readl(mr->base + MV61X0_RTC_TIME);
	dev_info(dev, "read-only: control %08x, time %u -> %u over 1.1 s%s\n",
		 readl(mr->base + MV61X0_RTC_CTRL), t0, t1,
		 t1 == t0 ? " (not counting: setup is a proposal)" : "");

	mr->rtc = devm_rtc_allocate_device(dev);
	if (IS_ERR(mr->rtc))
		return PTR_ERR(mr->rtc);
	mr->rtc->ops = &mv61x0_rtc_ops;
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

MODULE_DESCRIPTION("Marvell 88PA61x0 RTC (read-only)");
MODULE_LICENSE("GPL");
