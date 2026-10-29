// SPDX-License-Identifier: GPL-2.0
/*
 * Secondary interrupt controllers (SIC0, SIC1) of the Marvell 88PA61x0
 * printer SoCs (88PA6170 in the Sindoh DP200): 32 inputs each, chained
 * to one GIC SPI. Registers as the vendor 3.2 kernel uses them
 * (sic_mask_irq, sic_unmask_irq, sic_ack_irq, sic_handler):
 *
 *   +0x00  enable set, write 1s
 *   +0x0c  clear latched status, write 1s
 *   +0x14  enable clear, write 1s
 *   +0x18  status
 *
 * Like the vendor, every input runs with handle_level_irq and unmasking
 * also clears the input's latched status.
 */
#include <linux/bitops.h>
#include <linux/io.h>
#include <linux/irq.h>
#include <linux/irqchip.h>
#include <linux/irqchip/chained_irq.h>
#include <linux/irqdomain.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/of_irq.h>
#include <linux/slab.h>

#define SIC_ENABLE_SET		0x00
#define SIC_CLEAR		0x0c
#define SIC_ENABLE_CLR		0x14
#define SIC_STATUS		0x18

#define SIC_NR_IRQS		32

struct mv61x0_sic {
	void __iomem *base;
	struct irq_domain *domain;
	unsigned long enabled;
};

static void mv61x0_sic_ack(struct irq_data *d)
{
	struct mv61x0_sic *sic = irq_data_get_irq_chip_data(d);

	writel_relaxed(BIT(irqd_to_hwirq(d)), sic->base + SIC_CLEAR);
}

static void mv61x0_sic_mask(struct irq_data *d)
{
	struct mv61x0_sic *sic = irq_data_get_irq_chip_data(d);

	clear_bit(irqd_to_hwirq(d), &sic->enabled);
	writel_relaxed(BIT(irqd_to_hwirq(d)), sic->base + SIC_ENABLE_CLR);
}

static void mv61x0_sic_unmask(struct irq_data *d)
{
	struct mv61x0_sic *sic = irq_data_get_irq_chip_data(d);

	set_bit(irqd_to_hwirq(d), &sic->enabled);
	writel_relaxed(BIT(irqd_to_hwirq(d)), sic->base + SIC_ENABLE_SET);
	writel_relaxed(BIT(irqd_to_hwirq(d)), sic->base + SIC_CLEAR);
}

static struct irq_chip mv61x0_sic_chip = {
	.name		= "SIC",
	.irq_ack	= mv61x0_sic_ack,
	.irq_mask	= mv61x0_sic_mask,
	.irq_unmask	= mv61x0_sic_unmask,
};

static void mv61x0_sic_handler(struct irq_desc *desc)
{
	struct mv61x0_sic *sic = irq_desc_get_handler_data(desc);
	struct irq_chip *chip = irq_desc_get_chip(desc);
	unsigned long status, stray;
	unsigned int bit;

	chained_irq_enter(chip, desc);
	status = readl_relaxed(sic->base + SIC_STATUS);
	stray = status & ~READ_ONCE(sic->enabled);
	if (stray)
		writel_relaxed(stray, sic->base + SIC_CLEAR);
	status &= ~stray;
	for_each_set_bit(bit, &status, SIC_NR_IRQS)
		generic_handle_domain_irq(sic->domain, bit);
	chained_irq_exit(chip, desc);
}

static int mv61x0_sic_map(struct irq_domain *d, unsigned int virq,
			  irq_hw_number_t hw)
{
	irq_set_chip_and_handler(virq, &mv61x0_sic_chip, handle_level_irq);
	irq_set_chip_data(virq, d->host_data);
	irq_set_probe(virq);
	return 0;
}

static const struct irq_domain_ops mv61x0_sic_domain_ops = {
	.map	= mv61x0_sic_map,
	.xlate	= irq_domain_xlate_onecell,
};

static int __init mv61x0_sic_init(struct device_node *np,
				  struct device_node *parent)
{
	struct mv61x0_sic *sic;
	int irq;

	sic = kzalloc(sizeof(*sic), GFP_KERNEL);
	if (!sic)
		return -ENOMEM;

	sic->base = of_iomap(np, 0);
	irq = irq_of_parse_and_map(np, 0);
	if (!sic->base || !irq) {
		pr_err("%pOF: no registers or no parent interrupt\n", np);
		return -ENXIO;
	}

	pr_info("%pOF: status %08x at probe, parent irq %d\n", np,
		readl_relaxed(sic->base + SIC_STATUS), irq);

	/* Start with every input masked and nothing latched */
	writel_relaxed(~0U, sic->base + SIC_ENABLE_CLR);
	writel_relaxed(~0U, sic->base + SIC_CLEAR);

	sic->domain = irq_domain_create_linear(of_fwnode_handle(np), SIC_NR_IRQS,
					       &mv61x0_sic_domain_ops, sic);
	if (!sic->domain) {
		pr_err("%pOF: cannot create the irq domain\n", np);
		return -ENOMEM;
	}
	irq_set_chained_handler_and_data(irq, mv61x0_sic_handler, sic);

	return 0;
}
IRQCHIP_DECLARE(mv61x0_sic, "marvell,88pa6170-sic", mv61x0_sic_init);
