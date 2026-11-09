// SPDX-License-Identifier: GPL-2.0
/*
 * DP200 hang analysis (docs/kernel/nandboot_hang_analysis.md, nandps4):
 * a platform driver that binds nothing, registered at postcore_initcall
 * as ramoops_init registers ramoops_driver. With
 * CONFIG_MV61X0_DUMMY_PDRV_AS_RAMOOPS it takes ramoops' name and OF match
 * ("ramoops"), and says so if anything ever calls its probe.
 */
#include <linux/init.h>
#include <linux/mod_devicetable.h>
#include <linux/platform_device.h>

#ifdef CONFIG_MV61X0_DUMMY_PDRV_AS_RAMOOPS
#define MV61X0_DUMMY_NAME	"ramoops"
#define MV61X0_DUMMY_COMPAT	"ramoops"
#else
#define MV61X0_DUMMY_NAME	"mv61x0-dummy"
#define MV61X0_DUMMY_COMPAT	"dp200,hang-analysis-dummy"
#endif

static int mv61x0_dummy_probe(struct platform_device *pdev)
{
	dev_emerg(&pdev->dev, "mv61x0-dummy: probe called (%s, of_node %pOF)\n",
		  pdev->name, pdev->dev.of_node);
	return -ENODEV;
}

static const struct of_device_id mv61x0_dummy_match[] = {
	{ .compatible = MV61X0_DUMMY_COMPAT },
	{ }
};

static struct platform_driver mv61x0_dummy_driver = {
	.probe = mv61x0_dummy_probe,
	.driver = {
		.name = MV61X0_DUMMY_NAME,
		.of_match_table = mv61x0_dummy_match,
	},
};

static int __init mv61x0_dummy_init(void)
{
	pr_info("mv61x0-dummy: registering platform driver \"%s\"\n",
		MV61X0_DUMMY_NAME);
	return platform_driver_register(&mv61x0_dummy_driver);
}
postcore_initcall(mv61x0_dummy_init);
