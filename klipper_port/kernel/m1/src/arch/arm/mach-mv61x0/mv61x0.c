// SPDX-License-Identifier: GPL-2.0
/*
 * Marvell 88PA61x0 printer SoCs (88PA6170 in the Sindoh DP200).
 *
 * The device tree describes the hardware; secondary CPU start is in
 * platsmp.c.
 *
 * There is no PL310: the vendor kernel's "L2x0" (l2x0_init on 0xf8fe0000)
 * really reads the SCU and the GIC CPU interface, and it then clears every
 * outer-cache operation except sync. Its sync, mv61x0_cache_sync, writes
 * 0x01010101 to +0x530 of the DDR controller at 0xfa300000 (U-Boot reads
 * that block's chip-select address map at +0x100/+0x110/+0x130 and its
 * "MV" ID at +0x10), most likely a write-buffer drain for the controller's
 * ports. Mainline's place for that is soc_mb, run by mb()/wmb() and so by
 * every writel(), as on mach-mstar. It is installed when the DT's
 * memory-controller node is enabled (it is, as in stock).
 */
#include <linux/io.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <asm/barrier.h>
#include <asm/mach/arch.h>

#define MV61X0_MC_DRAIN		0x530
#define MV61X0_MC_DRAIN_ALL	0x01010101

static void __iomem *mv61x0_mc;

static void mv61x0_mb(void)
{
	writel_relaxed(MV61X0_MC_DRAIN_ALL, mv61x0_mc + MV61X0_MC_DRAIN);
}

static void __init mv61x0_init(void)
{
	struct device_node *np;

	np = of_find_compatible_node(NULL, NULL, "marvell,88pa6170-ddr");
	if (np && of_device_is_available(np)) {
		mv61x0_mc = of_iomap(np, 0);
		if (mv61x0_mc) {
			soc_mb = mv61x0_mb;
			pr_info("mv61x0: DDR write-buffer drain on mb() (vendor cache sync)\n");
		}
	}
	of_node_put(np);
}

static const char *const mv61x0_dt_compat[] __initconst = {
	"marvell,88pa6170",
	NULL,
};

DT_MACHINE_START(MV61X0_DT, "Marvell 88PA61x0")
	.dt_compat	= mv61x0_dt_compat,
	.init_machine	= mv61x0_init,
MACHINE_END
