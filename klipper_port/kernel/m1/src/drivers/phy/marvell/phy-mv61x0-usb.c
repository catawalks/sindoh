// SPDX-License-Identifier: GPL-2.0
/*
 * USB 2.0 PHYs of the Marvell 88PA61x0 printer SoCs (88PA6170 in the
 * Sindoh DP200): three PHYs, for the device (0), host (1) and OTG (2)
 * controllers, and a PLL they share. The programming is the vendor 3.2
 * kernel's usb_phy_init(), run once for all three PHYs when the first
 * one is initialised:
 *
 *   PLL      +0x04  bits 3:0 = 5, bits 11:4 = 0x60, bit 21 enable,
 *                   bit 23 locked; +0x08 bit 9 set before enabling
 *   PHY n    at 0x40 * (n + 1):
 *            +0x0c  bit 15 power
 *            +0x04  bit 12 pulsed after the PLL locks
 *            +0x14  bits 27:26 set and bit 28 cleared for 12.5 ms,
 *                   then the reverse
 *
 * A PHY that is already powered (the boot loader used it) is left alone,
 * and so is a PLL that is already enabled, as the vendor does.
 */
#include <linux/bitfield.h>
#include <linux/bitops.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/phy/phy.h>
#include <linux/platform_device.h>

#define MV61X0_USB_NR_PHYS	3

#define PLL_CTRL		0x04
#define PLL_CTRL_REFDIV		GENMASK(3, 0)
#define PLL_CTRL_FBDIV		GENMASK(11, 4)
#define PLL_CTRL_ENABLE		BIT(21)
#define PLL_CTRL_LOCKED		BIT(23)
#define PLL_CTRL2		0x08
#define PLL_CTRL2_BIT9		BIT(9)

#define PHY_BASE(n)		(0x40 * ((n) + 1))
#define PHY_CTRL		0x04
#define PHY_CTRL_PULSE		BIT(12)
#define PHY_POWER		0x0c
#define PHY_POWER_ON		BIT(15)
#define PHY_CAL			0x14
#define PHY_CAL_START		GENMASK(27, 26)
#define PHY_CAL_DONE		BIT(28)

struct mv61x0_usb_phy {
	void __iomem *base;
	struct mutex lock;
	bool initialised;
	struct phy *phys[MV61X0_USB_NR_PHYS];
};

static void mv61x0_rmw(void __iomem *reg, u32 clear, u32 set)
{
	writel((readl(reg) & ~clear) | set, reg);
}

static int mv61x0_usb_phy_setup(struct device *dev, void __iomem *base)
{
	unsigned long was_powered = 0;
	void __iomem *p;
	u32 val;
	int n, ret;

	for (n = 0; n < MV61X0_USB_NR_PHYS; n++) {
		p = base + PHY_BASE(n);
		if (readl(p + PHY_POWER) & PHY_POWER_ON)
			__set_bit(n, &was_powered);
		else
			mv61x0_rmw(p + PHY_POWER, 0, PHY_POWER_ON);
		usleep_range(2500, 3000);
	}

	if (!(readl(base + PLL_CTRL) & PLL_CTRL_ENABLE)) {
		mv61x0_rmw(base + PLL_CTRL, PLL_CTRL_REFDIV,
			   FIELD_PREP(PLL_CTRL_REFDIV, 5));
		mv61x0_rmw(base + PLL_CTRL, PLL_CTRL_FBDIV,
			   FIELD_PREP(PLL_CTRL_FBDIV, 0x60));
		mv61x0_rmw(base + PLL_CTRL2, 0, PLL_CTRL2_BIT9);
		usleep_range(5000, 6000);
		mv61x0_rmw(base + PLL_CTRL, 0, PLL_CTRL_ENABLE);
		ret = readl_poll_timeout(base + PLL_CTRL, val,
					 val & PLL_CTRL_LOCKED, 100, 100000);
		if (ret) {
			dev_err(dev, "PLL does not lock (%08x)\n", val);
			return ret;
		}
		msleep(25);
	}

	for (n = 0; n < MV61X0_USB_NR_PHYS; n++) {
		if (test_bit(n, &was_powered))
			continue;
		p = base + PHY_BASE(n);
		mv61x0_rmw(p + PHY_CTRL, 0, PHY_CTRL_PULSE);
		usleep_range(2500, 3000);
		mv61x0_rmw(p + PHY_CTRL, PHY_CTRL_PULSE, 0);
		msleep(10);
		mv61x0_rmw(p + PHY_CAL, PHY_CAL_DONE, PHY_CAL_START);
		usleep_range(12500, 13000);
		mv61x0_rmw(p + PHY_CAL, PHY_CAL_START, PHY_CAL_DONE);
	}

	dev_info(dev, "PLL %08x, PHYs %s by the boot loader: %lx\n",
		 readl(base + PLL_CTRL),
		 was_powered ? "partly powered" : "not powered", was_powered);
	return 0;
}

static int mv61x0_usb_phy_init(struct phy *phy)
{
	struct mv61x0_usb_phy *priv = phy_get_drvdata(phy);
	int ret = 0;

	mutex_lock(&priv->lock);
	if (!priv->initialised) {
		ret = mv61x0_usb_phy_setup(&phy->dev, priv->base);
		priv->initialised = !ret;
	}
	mutex_unlock(&priv->lock);

	return ret;
}

static const struct phy_ops mv61x0_usb_phy_ops = {
	.init	= mv61x0_usb_phy_init,
	.owner	= THIS_MODULE,
};

static struct phy *mv61x0_usb_phy_xlate(struct device *dev,
					const struct of_phandle_args *args)
{
	struct mv61x0_usb_phy *priv = dev_get_drvdata(dev);

	if (args->args[0] >= MV61X0_USB_NR_PHYS)
		return ERR_PTR(-EINVAL);
	return priv->phys[args->args[0]];
}

static int mv61x0_usb_phy_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct phy_provider *provider;
	struct mv61x0_usb_phy *priv;
	int n;

	priv = devm_kzalloc(dev, sizeof(*priv), GFP_KERNEL);
	if (!priv)
		return -ENOMEM;

	priv->base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(priv->base))
		return PTR_ERR(priv->base);
	mutex_init(&priv->lock);
	dev_set_drvdata(dev, priv);

	for (n = 0; n < MV61X0_USB_NR_PHYS; n++) {
		priv->phys[n] = devm_phy_create(dev, NULL, &mv61x0_usb_phy_ops);
		if (IS_ERR(priv->phys[n]))
			return PTR_ERR(priv->phys[n]);
		phy_set_drvdata(priv->phys[n], priv);
	}

	provider = devm_of_phy_provider_register(dev, mv61x0_usb_phy_xlate);
	return PTR_ERR_OR_ZERO(provider);
}

static const struct of_device_id mv61x0_usb_phy_of_match[] = {
	{ .compatible = "marvell,88pa6170-usb-phy" },
	{ }
};
MODULE_DEVICE_TABLE(of, mv61x0_usb_phy_of_match);

static struct platform_driver mv61x0_usb_phy_driver = {
	.probe	= mv61x0_usb_phy_probe,
	.driver	= {
		.name		= "mv61x0-usb-phy",
		.of_match_table	= mv61x0_usb_phy_of_match,
	},
};
module_platform_driver(mv61x0_usb_phy_driver);

MODULE_DESCRIPTION("Marvell 88PA61x0 USB 2.0 PHY");
MODULE_LICENSE("GPL");
