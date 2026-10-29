// SPDX-License-Identifier: GPL-2.0
/*
 * GPIO banks of the Marvell 88PA61x0 printer SoCs (88PA6170 in the Sindoh
 * DP200): eight banks of 32 lines at 0xf8040000 + 0x1000 * n. Layout from
 * the vendor driver (gogin_gpio_*):
 *
 *   +0x00             input level
 *   +0x04             output level
 *   +0x08             direction, 1 = output
 *   +0x80 + 4 * pin   pin configuration; bits 2:0 select the function,
 *                     0 = GPIO, 1-3 = the alternate functions
 *
 * Nothing is driven at probe. The output and direction shadows start from
 * the hardware, so changing one line never rewrites the others, and the
 * output level is set before the direction, as the vendor does. Requesting
 * a line switches its pin to the GPIO function, again as the vendor
 * request hook does; that is the only pin-mux change this driver makes.
 */
#include <linux/bitops.h>
#include <linux/gpio/driver.h>
#include <linux/gpio/generic.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/spinlock.h>

#define MV61X0_GPIO_IN		0x00
#define MV61X0_GPIO_OUT		0x04
#define MV61X0_GPIO_DIR		0x08
#define MV61X0_GPIO_PINCFG(n)	(0x80 + 4 * (n))
#define MV61X0_PINCFG_SELECT	GENMASK(2, 0)

struct mv61x0_gpio {
	struct gpio_generic_chip chip;
	void __iomem *base;
	spinlock_t pincfg_lock;
};

static int mv61x0_gpio_request(struct gpio_chip *gc, unsigned int offset)
{
	struct mv61x0_gpio *mg = gpiochip_get_data(gc);
	void __iomem *reg = mg->base + MV61X0_GPIO_PINCFG(offset);
	unsigned long flags;
	u32 cfg;

	spin_lock_irqsave(&mg->pincfg_lock, flags);
	cfg = readl(reg);
	if (cfg & MV61X0_PINCFG_SELECT) {
		dev_info(gc->parent, "line %u: pin function %lu -> GPIO\n",
			 offset, cfg & MV61X0_PINCFG_SELECT);
		writel(cfg & ~MV61X0_PINCFG_SELECT, reg);
	}
	spin_unlock_irqrestore(&mg->pincfg_lock, flags);

	return 0;
}

static int mv61x0_gpio_probe(struct platform_device *pdev)
{
	struct gpio_generic_chip_config config = { };
	struct device *dev = &pdev->dev;
	struct mv61x0_gpio *mg;
	int ret;

	mg = devm_kzalloc(dev, sizeof(*mg), GFP_KERNEL);
	if (!mg)
		return -ENOMEM;
	spin_lock_init(&mg->pincfg_lock);

	mg->base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(mg->base))
		return PTR_ERR(mg->base);

	config.dev = dev;
	config.sz = 4;
	config.dat = mg->base + MV61X0_GPIO_IN;
	config.set = mg->base + MV61X0_GPIO_OUT;
	config.dirout = mg->base + MV61X0_GPIO_DIR;
	config.flags = GPIO_GENERIC_READ_OUTPUT_REG_SET;
	ret = gpio_generic_chip_init(&mg->chip, &config);
	if (ret)
		return ret;

	mg->chip.gc.request = mv61x0_gpio_request;
	mg->chip.gc.ngpio = 32;
	mg->chip.gc.base = -1;
	mg->chip.gc.label = dev_name(dev);

	ret = devm_gpiochip_add_data(dev, &mg->chip.gc, mg);
	if (ret)
		return ret;

	dev_info(dev, "32 lines: in %08x out %08x dir %08x (untouched)\n",
		 readl(mg->base + MV61X0_GPIO_IN),
		 readl(mg->base + MV61X0_GPIO_OUT),
		 readl(mg->base + MV61X0_GPIO_DIR));
	return 0;
}

static const struct of_device_id mv61x0_gpio_of_match[] = {
	{ .compatible = "marvell,88pa6170-gpio" },
	{ }
};
MODULE_DEVICE_TABLE(of, mv61x0_gpio_of_match);

static struct platform_driver mv61x0_gpio_driver = {
	.probe	= mv61x0_gpio_probe,
	.driver	= {
		.name		= "mv61x0-gpio",
		.of_match_table	= mv61x0_gpio_of_match,
	},
};
module_platform_driver(mv61x0_gpio_driver);

MODULE_DESCRIPTION("Marvell 88PA61x0 GPIO");
MODULE_LICENSE("GPL");
