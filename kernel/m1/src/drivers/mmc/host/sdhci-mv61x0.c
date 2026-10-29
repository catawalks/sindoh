// SPDX-License-Identifier: GPL-2.0
/*
 * SD/MMC controllers of the Marvell 88PA61x0 printer SoCs (88PA6170 in the
 * Sindoh DP200): two standard SDHCI slots at 0xf9080000 and 0xf9080200
 * sharing one interrupt. The SD socket is slot 0.
 *
 * The quirks are the vendor's (sdhci_gogin_readw/readl and its platform
 * data): 16-bit reads of the slot interrupt status (0xfc) and the host
 * version (0xfe) return 0, the capabilities lose bit 25 (3.0 V), and the
 * host has no busy IRQ, no working card detect and no high-speed bit.
 */
#include <linux/bits.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>

#include "sdhci-pltfm.h"

static u16 mv61x0_sdhci_readw(struct sdhci_host *host, int reg)
{
	if (reg == SDHCI_SLOT_INT_STATUS || reg == SDHCI_HOST_VERSION)
		return 0;
	return readw(host->ioaddr + reg);
}

static u32 mv61x0_sdhci_readl(struct sdhci_host *host, int reg)
{
	u32 val = readl(host->ioaddr + reg);

	if (reg == SDHCI_CAPABILITIES)
		val &= ~SDHCI_CAN_VDD_300;
	return val;
}

static const struct sdhci_ops mv61x0_sdhci_ops = {
	.read_w			= mv61x0_sdhci_readw,
	.read_l			= mv61x0_sdhci_readl,
	.set_clock		= sdhci_set_clock,
	.set_bus_width		= sdhci_set_bus_width,
	.reset			= sdhci_reset,
	.set_uhs_signaling	= sdhci_set_uhs_signaling,
};

static const struct sdhci_pltfm_data mv61x0_sdhci_pdata = {
	.ops	= &mv61x0_sdhci_ops,
	.quirks	= SDHCI_QUIRK_NO_BUSY_IRQ |
		  SDHCI_QUIRK_BROKEN_CARD_DETECTION |
		  SDHCI_QUIRK_NO_HISPD_BIT,
};

static int mv61x0_sdhci_probe(struct platform_device *pdev)
{
	struct sdhci_host *host;
	int ret;

	host = sdhci_pltfm_init(pdev, &mv61x0_sdhci_pdata, 0);
	if (IS_ERR(host))
		return PTR_ERR(host);

	ret = mmc_of_parse(host->mmc);
	if (ret)
		return ret;

	return sdhci_add_host(host);
}

static const struct of_device_id mv61x0_sdhci_of_match[] = {
	{ .compatible = "marvell,88pa6170-sdhci" },
	{ }
};
MODULE_DEVICE_TABLE(of, mv61x0_sdhci_of_match);

static struct platform_driver mv61x0_sdhci_driver = {
	.probe	= mv61x0_sdhci_probe,
	.remove	= sdhci_pltfm_remove,
	.driver	= {
		.name		= "sdhci-mv61x0",
		.of_match_table	= mv61x0_sdhci_of_match,
		.pm		= &sdhci_pltfm_pmops,
	},
};
module_platform_driver(mv61x0_sdhci_driver);

MODULE_DESCRIPTION("Marvell 88PA61x0 SDHCI glue");
MODULE_LICENSE("GPL");
