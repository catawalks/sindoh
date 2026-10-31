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
 *
 * With "marvell,read-only" the bank is for reading only: requesting a line
 * whose pin has another function fails (-EBUSY) and leaves the pin mux
 * alone, and setting an output level or direction fails (-EPERM). Inputs
 * and the current direction and output levels can still be read.
 *
 * Interrupts (vendor gpio_*_irq): one GIC line per bank; +0x10 enable,
 * +0x14 acknowledge (write the line's bit), +0x18 status; the trigger is
 * bits 7:5 of the line's pin configuration (0 level low, 1 falling edge,
 * 2 level high, 3 rising edge, 7 both edges). With an "interrupts" property
 * the bank is an interrupt controller; probe masks every line first. In
 * read-only mode, a consumer's interrupt still sets that line's trigger
 * bits (the only pin-configuration write it makes).
 *
 * Board setup at probe, from the DT, whatever the read-only mode (for pins
 * the board needs set before any driver asks, user-approved values only):
 * "marvell,init-output-high" lists lines driven high (output level first,
 * then the direction, as the vendor does), then "marvell,pin-config" gives
 * <line value> pairs for the pin-configuration registers.
 */
#include <linux/bitops.h>
#include <linux/interrupt.h>
#include <linux/irq.h>
#include <linux/irqchip/chained_irq.h>
#include <linux/gpio/driver.h>
#include <linux/gpio/generic.h>
#include <linux/bitfield.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/spinlock.h>

#define MV61X0_GPIO_IN		0x00
#define MV61X0_GPIO_OUT		0x04
#define MV61X0_GPIO_DIR		0x08
#define MV61X0_GPIO_IRQ_EN	0x10
#define MV61X0_GPIO_IRQ_ACK	0x14
#define MV61X0_GPIO_IRQ_STATUS	0x18
#define MV61X0_PINCFG_IRQ_TYPE	GENMASK(7, 5)
#define MV61X0_GPIO_PINCFG(n)	(0x80 + 4 * (n))
#define MV61X0_PINCFG_SELECT	GENMASK(2, 0)

struct mv61x0_gpio {
	struct gpio_generic_chip chip;
	void __iomem *base;
	spinlock_t pincfg_lock;
	bool read_only;
};

static int mv61x0_gpio_request(struct gpio_chip *gc, unsigned int offset)
{
	struct mv61x0_gpio *mg = gpiochip_get_data(gc);
	void __iomem *reg = mg->base + MV61X0_GPIO_PINCFG(offset);
	unsigned long flags;
	u32 cfg;

	spin_lock_irqsave(&mg->pincfg_lock, flags);
	cfg = readl(reg);
	if ((cfg & MV61X0_PINCFG_SELECT) && mg->read_only) {
		spin_unlock_irqrestore(&mg->pincfg_lock, flags);
		dev_info(gc->parent, "line %u: pin function %lu, read-only bank: refused\n",
			 offset, cfg & MV61X0_PINCFG_SELECT);
		return -EBUSY;
	}
	if (cfg & MV61X0_PINCFG_SELECT) {
		dev_info(gc->parent, "line %u: pin function %lu -> GPIO\n",
			 offset, cfg & MV61X0_PINCFG_SELECT);
		writel(cfg & ~MV61X0_PINCFG_SELECT, reg);
	}
	spin_unlock_irqrestore(&mg->pincfg_lock, flags);

	return 0;
}

static void mv61x0_gpio_irq_ack(struct irq_data *d)
{
	struct gpio_chip *gc = irq_data_get_irq_chip_data(d);
	struct mv61x0_gpio *mg = gpiochip_get_data(gc);

	writel(BIT(irqd_to_hwirq(d)), mg->base + MV61X0_GPIO_IRQ_ACK);
}

static void mv61x0_gpio_irq_mask(struct irq_data *d)
{
	struct gpio_chip *gc = irq_data_get_irq_chip_data(d);
	struct mv61x0_gpio *mg = gpiochip_get_data(gc);
	irq_hw_number_t hw = irqd_to_hwirq(d);
	unsigned long flags;

	spin_lock_irqsave(&mg->pincfg_lock, flags);
	writel(readl(mg->base + MV61X0_GPIO_IRQ_EN) & ~BIT(hw),
	       mg->base + MV61X0_GPIO_IRQ_EN);
	spin_unlock_irqrestore(&mg->pincfg_lock, flags);
	gpiochip_disable_irq(gc, hw);
}

static void mv61x0_gpio_irq_unmask(struct irq_data *d)
{
	struct gpio_chip *gc = irq_data_get_irq_chip_data(d);
	struct mv61x0_gpio *mg = gpiochip_get_data(gc);
	irq_hw_number_t hw = irqd_to_hwirq(d);
	unsigned long flags;

	gpiochip_enable_irq(gc, hw);
	spin_lock_irqsave(&mg->pincfg_lock, flags);
	writel(readl(mg->base + MV61X0_GPIO_IRQ_EN) | BIT(hw),
	       mg->base + MV61X0_GPIO_IRQ_EN);
	spin_unlock_irqrestore(&mg->pincfg_lock, flags);
}

static int mv61x0_gpio_irq_set_type(struct irq_data *d, unsigned int type)
{
	struct gpio_chip *gc = irq_data_get_irq_chip_data(d);
	struct mv61x0_gpio *mg = gpiochip_get_data(gc);
	void __iomem *reg = mg->base + MV61X0_GPIO_PINCFG(irqd_to_hwirq(d));
	unsigned long flags;
	u32 t;

	switch (type & IRQ_TYPE_SENSE_MASK) {
	case IRQ_TYPE_LEVEL_LOW:	t = 0; break;
	case IRQ_TYPE_EDGE_FALLING:	t = 1; break;
	case IRQ_TYPE_LEVEL_HIGH:	t = 2; break;
	case IRQ_TYPE_EDGE_RISING:	t = 3; break;
	case IRQ_TYPE_EDGE_BOTH:	t = 7; break;
	default:			return -EINVAL;
	}
	spin_lock_irqsave(&mg->pincfg_lock, flags);
	writel((readl(reg) & ~MV61X0_PINCFG_IRQ_TYPE) |
	       FIELD_PREP(MV61X0_PINCFG_IRQ_TYPE, t), reg);
	spin_unlock_irqrestore(&mg->pincfg_lock, flags);
	irq_set_handler_locked(d, type & IRQ_TYPE_LEVEL_MASK ?
			       handle_level_irq : handle_edge_irq);
	return 0;
}

static const struct irq_chip mv61x0_gpio_irqchip = {
	.name		= "mv61x0-gpio",
	.irq_ack	= mv61x0_gpio_irq_ack,
	.irq_mask	= mv61x0_gpio_irq_mask,
	.irq_unmask	= mv61x0_gpio_irq_unmask,
	.irq_set_type	= mv61x0_gpio_irq_set_type,
	.flags		= IRQCHIP_IMMUTABLE,
	GPIOCHIP_IRQ_RESOURCE_HELPERS,
};

static void mv61x0_gpio_irq_handler(struct irq_desc *desc)
{
	struct gpio_chip *gc = irq_desc_get_handler_data(desc);
	struct mv61x0_gpio *mg = gpiochip_get_data(gc);
	struct irq_chip *chip = irq_desc_get_chip(desc);
	unsigned long pending;
	unsigned int bit;

	chained_irq_enter(chip, desc);
	pending = readl(mg->base + MV61X0_GPIO_IRQ_STATUS) &
		  readl(mg->base + MV61X0_GPIO_IRQ_EN);
	for_each_set_bit(bit, &pending, 32)
		generic_handle_domain_irq(gc->irq.domain, bit);
	chained_irq_exit(chip, desc);
}

static int mv61x0_gpio_ro_output(struct gpio_chip *gc, unsigned int offset,
				 int value)
{
	return -EPERM;
}

static int mv61x0_gpio_ro_set_multiple(struct gpio_chip *gc,
				       unsigned long *mask, unsigned long *bits)
{
	return -EPERM;
}

static void mv61x0_gpio_board_setup(struct device *dev,
				    struct mv61x0_gpio *mg)
{
	struct device_node *np = dev->of_node;
	u32 line, val;
	int i, n;

	n = of_property_count_u32_elems(np, "marvell,init-output-high");
	for (i = 0; i < n; i++) {
		if (of_property_read_u32_index(np, "marvell,init-output-high",
					       i, &line) || line > 31)
			continue;
		writel(readl(mg->base + MV61X0_GPIO_OUT) | BIT(line),
		       mg->base + MV61X0_GPIO_OUT);
		writel(readl(mg->base + MV61X0_GPIO_DIR) | BIT(line),
		       mg->base + MV61X0_GPIO_DIR);
		dev_info(dev, "line %u: output high (board setup)\n", line);
	}

	n = of_property_count_u32_elems(np, "marvell,pin-config");
	for (i = 0; i + 1 < n; i += 2) {
		if (of_property_read_u32_index(np, "marvell,pin-config", i,
					       &line) ||
		    of_property_read_u32_index(np, "marvell,pin-config", i + 1,
					       &val) || line > 31)
			continue;
		dev_info(dev, "line %u: pin config %08x -> %08x (board setup)\n",
			 line, readl(mg->base + MV61X0_GPIO_PINCFG(line)), val);
		writel(val, mg->base + MV61X0_GPIO_PINCFG(line));
	}
}

static int mv61x0_gpio_probe(struct platform_device *pdev)
{
	struct gpio_generic_chip_config config = { };
	struct device *dev = &pdev->dev;
	struct mv61x0_gpio *mg;
	int ret, irq;

	mg = devm_kzalloc(dev, sizeof(*mg), GFP_KERNEL);
	if (!mg)
		return -ENOMEM;
	spin_lock_init(&mg->pincfg_lock);

	mg->base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(mg->base))
		return PTR_ERR(mg->base);

	/* Before the generic chip reads the output/direction shadows */
	mv61x0_gpio_board_setup(dev, mg);

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

	irq = platform_get_irq_optional(pdev, 0);
	if (irq > 0) {
		struct gpio_irq_chip *girq = &mg->chip.gc.irq;

		/* every line masked and acknowledged before the chain opens */
		writel(0, mg->base + MV61X0_GPIO_IRQ_EN);
		writel(~0U, mg->base + MV61X0_GPIO_IRQ_ACK);
		gpio_irq_chip_set_chip(girq, &mv61x0_gpio_irqchip);
		girq->parent_handler = mv61x0_gpio_irq_handler;
		girq->num_parents = 1;
		girq->parents = devm_kcalloc(dev, 1, sizeof(*girq->parents),
					     GFP_KERNEL);
		if (!girq->parents)
			return -ENOMEM;
		girq->parents[0] = irq;
		girq->default_type = IRQ_TYPE_NONE;
		girq->handler = handle_bad_irq;
	}
	mg->read_only = of_property_read_bool(dev->of_node, "marvell,read-only");
	if (mg->read_only) {
		mg->chip.gc.direction_output = mv61x0_gpio_ro_output;
		mg->chip.gc.set = mv61x0_gpio_ro_output;
		mg->chip.gc.set_multiple = mv61x0_gpio_ro_set_multiple;
	}
	mg->chip.gc.ngpio = 32;
	mg->chip.gc.base = -1;
	mg->chip.gc.label = dev_name(dev);

	ret = devm_gpiochip_add_data(dev, &mg->chip.gc, mg);
	if (ret)
		return ret;

	dev_info(dev, "32 lines%s: in %08x out %08x dir %08x (untouched)\n",
		 mg->read_only ? " (read-only)" : "",
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
