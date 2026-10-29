// SPDX-License-Identifier: GPL-2.0
/*
 * Secondary CPU start on the Marvell 88PA61x0, the way the vendor 3.2
 * kernel does it (platform_smp_prepare_cpus, boot_secondary): enable the
 * A9-style SCU, write the physical address of secondary_startup to the
 * mailbox at 0xfa000000, then send the CPU an SGI. CPU 1 waits for both
 * in the boot ROM.
 */
#include <linux/io.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/smp.h>
#include <asm/smp_scu.h>

#define MV61X0_CPU_MAILBOX	0xfa000000

static void __iomem *mv61x0_mailbox;

static int mv61x0_boot_secondary(unsigned int cpu, struct task_struct *idle)
{
	if (!mv61x0_mailbox)
		return -ENODEV;

	writel(__pa_symbol(secondary_startup), mv61x0_mailbox);
	arch_send_wakeup_ipi_mask(cpumask_of(cpu));

	return 0;
}

static void __init mv61x0_smp_prepare_cpus(unsigned int max_cpus)
{
	struct device_node *np;
	void __iomem *scu;

	np = of_find_compatible_node(NULL, NULL, "arm,cortex-a9-scu");
	scu = of_iomap(np, 0);
	of_node_put(np);
	if (!scu) {
		pr_err("mv61x0: no SCU, staying on one CPU\n");
		return;
	}
	scu_enable(scu);
	iounmap(scu);

	mv61x0_mailbox = ioremap(MV61X0_CPU_MAILBOX, 4);
}

static const struct smp_operations mv61x0_smp_ops __initconst = {
	.smp_prepare_cpus	= mv61x0_smp_prepare_cpus,
	.smp_boot_secondary	= mv61x0_boot_secondary,
};
CPU_METHOD_OF_DECLARE(mv61x0_smp, "marvell,88pa6170-smp", &mv61x0_smp_ops);
