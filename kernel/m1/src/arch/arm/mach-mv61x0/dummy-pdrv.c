// SPDX-License-Identifier: GPL-2.0
/*
 * DP200 hang analysis (docs/kernel/nandboot_hang_analysis.md, nandps4):
 * a platform driver that binds nothing, registered at postcore_initcall
 * as ramoops_init registers ramoops_driver. Nothing matches its OF table,
 * so its probe never runs.
 */
#include <linux/init.h>
#include <linux/mod_devicetable.h>
#include <linux/platform_device.h>

static int mv61x0_dummy_probe(struct platform_device *pdev)
{
	return -ENODEV;
}

static const struct of_device_id mv61x0_dummy_match[] = {
	{ .compatible = "dp200,hang-analysis-dummy" },
	{ }
};

static struct platform_driver mv61x0_dummy_driver = {
	.probe = mv61x0_dummy_probe,
	.driver = {
		.name = "mv61x0-dummy",
		.of_match_table = mv61x0_dummy_match,
	},
};

static int __init mv61x0_dummy_init(void)
{
	return platform_driver_register(&mv61x0_dummy_driver);
}
postcore_initcall(mv61x0_dummy_init);
