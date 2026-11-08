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
#include <linux/moduleparam.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/smp.h>
#include <asm/barrier.h>
#include <asm/cputype.h>
#include <asm/mach/arch.h>

#define MV61X0_MC_DRAIN		0x530
#define MV61X0_MC_DRAIN_ALL	0x01010101

static void __iomem *mv61x0_mc;

/*
 * mv61x0.mc_drain (0644): 0 skips the drain write, for the hang analysis
 * (docs/kernel/nandboot_hang_analysis.md, hang 12). On by default.
 */
static bool mv61x0_mc_drain = true;
module_param_named(mc_drain, mv61x0_mc_drain, bool, 0644);

static void mv61x0_mb(void)
{
	if (READ_ONCE(mv61x0_mc_drain))
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
			pr_info("mv61x0: DDR write-buffer drain on mb() (vendor cache sync)%s\n",
				mv61x0_mc_drain ? "" : ", off (mc_drain=0)");
		}
	}
	of_node_put(np);

	/*
	 * For the hang analysis: MMFR3 says whether the walker is coherent
	 * (bits 23:20) and whether cache and TLB maintenance is broadcast
	 * (15:12), TTBR0 the attributes of the table walk.
	 */
	{
		u32 ttbr0, ttbcr;

		asm volatile("mrc p15, 0, %0, c2, c0, 0" : "=r" (ttbr0));
		asm volatile("mrc p15, 0, %0, c2, c0, 2" : "=r" (ttbcr));
		pr_info("mv61x0: ID_MMFR0 %08x MMFR1 %08x MMFR3 %08x, TTBR0 %08x TTBCR %08x, page-table writes %scleaned\n",
			read_cpuid_ext(CPUID_EXT_MMFR0),
			read_cpuid_ext(CPUID_EXT_MMFR1),
			read_cpuid_ext(CPUID_EXT_MMFR3), ttbr0, ttbcr,
			IS_ENABLED(CONFIG_PJ4B_MV61X0_PTE_CLEAN) ? "" : "not ");
	}
}

/*
 * For the hang analysis (hang 13): the PJ4B setup registers on each CPU.
 * The vendor kernel and mainline's __v7_pj4b_setup program them
 * differently (CONFIG_PJ4B_MV61X0_VENDOR_SETUP picks the vendor's).
 */
static void mv61x0_pj4b_regs(void *unused)
{
	u32 actlr, func0, dbg0, dbg1, dbg2;

	asm volatile("mrc p15, 0, %0, c1, c0, 1" : "=r" (actlr));
	asm volatile("mrc p15, 1, %0, c15, c2, 0" : "=r" (func0));
	asm volatile("mrc p15, 1, %0, c15, c1, 0" : "=r" (dbg0));
	asm volatile("mrc p15, 1, %0, c15, c1, 1" : "=r" (dbg1));
	asm volatile("mrc p15, 1, %0, c15, c1, 2" : "=r" (dbg2));
	pr_info("mv61x0: cpu%d ACTLR %08x aux func0 %08x dbg0 %08x dbg1 %08x dbg2 %08x (%s PJ4B setup)\n",
		smp_processor_id(), actlr, func0, dbg0, dbg1, dbg2,
		IS_ENABLED(CONFIG_PJ4B_MV61X0_VENDOR_SETUP) ? "vendor" : "mainline");
}

static int __init mv61x0_pj4b_regs_init(void)
{
	if (of_machine_is_compatible("marvell,88pa6170"))
		on_each_cpu(mv61x0_pj4b_regs, NULL, 1);
	return 0;
}
late_initcall(mv61x0_pj4b_regs_init);

static const char *const mv61x0_dt_compat[] __initconst = {
	"marvell,88pa6170",
	NULL,
};

DT_MACHINE_START(MV61X0_DT, "Marvell 88PA61x0")
	.dt_compat	= mv61x0_dt_compat,
	.init_machine	= mv61x0_init,
MACHINE_END
