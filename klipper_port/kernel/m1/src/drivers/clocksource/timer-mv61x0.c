// SPDX-License-Identifier: GPL-2.0
/*
 * Timer block of the Marvell 88PA61x0 printer SoCs (88PA6170 in the
 * Sindoh DP200).
 *
 * Four 32-bit timers that count up from 0 to their load value. The layout
 * and the programming sequences follow the vendor 3.2 kernel
 * (timer_set_next_event, timer_set_mode, enable_timer, timer_interrupt):
 *
 *   +0x00             watchdog control (timer 0), not touched here
 *   +0x04 + 0x10 * n  load (terminal count)
 *   +0x08 + 0x10 * n  control: bit 0 enable, bit 1 auto-reload
 *   +0x0c + 0x10 * n  count
 *   +0x10             interrupt status, bit n per timer
 *   +0x20             interrupt clear, write bit n
 *
 * The second register range is the prescaler shared by the timers: bus
 * clocks per timer tick. The vendor kernel writes 198 there (198 MHz bus,
 * 1 MHz tick); "marvell,prescale" makes this driver do the same.
 *
 * As in the vendor kernel, timer 1 is the clock event device and timer 2
 * runs free over the full 32 bits as clocksource and sched_clock. The
 * count direction is measured at boot and printed, because only the
 * vendor's use of the counter (cnt32_to_63) says it counts up.
 */

#include <linux/clk.h>
#include <linux/clockchips.h>
#include <linux/clocksource.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/irq.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/of_irq.h>
#include <linux/sched_clock.h>

#define MV61X0_WDT_CTRL		0x00
#define MV61X0_LOAD(n)		(0x04 + 0x10 * (n))
#define MV61X0_CTRL(n)		(0x08 + 0x10 * (n))
#define MV61X0_COUNT(n)		(0x0c + 0x10 * (n))
#define MV61X0_IRQ_STATUS	0x10
#define MV61X0_IRQ_CLEAR	0x20

#define MV61X0_CTRL_ENABLE	BIT(0)
#define MV61X0_CTRL_RELOAD	BIT(1)

#define MV61X0_CE_TIMER		1
#define MV61X0_CS_TIMER		2

static void __iomem *mv61x0_base;
static void __iomem *mv61x0_cs_count;
static bool mv61x0_count_down;
static u32 mv61x0_ticks_per_jiffy;

static void mv61x0_ce_stop(void)
{
	writel_relaxed(0, mv61x0_base + MV61X0_CTRL(MV61X0_CE_TIMER));
}

static void mv61x0_ce_start(u32 ticks, u32 ctrl)
{
	/* Vendor order: stop, load, start (starting restarts the count) */
	mv61x0_ce_stop();
	writel_relaxed(ticks, mv61x0_base + MV61X0_LOAD(MV61X0_CE_TIMER));
	writel_relaxed(ctrl, mv61x0_base + MV61X0_CTRL(MV61X0_CE_TIMER));
}

static int mv61x0_set_next_event(unsigned long delta,
				 struct clock_event_device *ce)
{
	mv61x0_ce_start(delta, MV61X0_CTRL_ENABLE);
	return 0;
}

static int mv61x0_set_periodic(struct clock_event_device *ce)
{
	mv61x0_ce_start(mv61x0_ticks_per_jiffy,
			MV61X0_CTRL_ENABLE | MV61X0_CTRL_RELOAD);
	return 0;
}

static int mv61x0_shutdown(struct clock_event_device *ce)
{
	mv61x0_ce_stop();
	return 0;
}

static struct clock_event_device mv61x0_ce = {
	.name			= "mv61x0_timer1",
	.features		= CLOCK_EVT_FEAT_PERIODIC |
				  CLOCK_EVT_FEAT_ONESHOT,
	.rating			= 300,
	.set_next_event		= mv61x0_set_next_event,
	.set_state_periodic	= mv61x0_set_periodic,
	.set_state_oneshot	= mv61x0_shutdown,
	.set_state_shutdown	= mv61x0_shutdown,
	.tick_resume		= mv61x0_shutdown,
};

static irqreturn_t mv61x0_timer_interrupt(int irq, void *dev_id)
{
	struct clock_event_device *ce = dev_id;
	u32 bit = BIT(MV61X0_CE_TIMER);

	if (!(readl_relaxed(mv61x0_base + MV61X0_IRQ_STATUS) & bit))
		return IRQ_NONE;

	writel_relaxed(bit, mv61x0_base + MV61X0_IRQ_CLEAR);
	if (clockevent_state_oneshot(ce))
		mv61x0_ce_stop();
	ce->event_handler(ce);

	return IRQ_HANDLED;
}

static u64 notrace mv61x0_read_sched_clock(void)
{
	u32 count = readl_relaxed(mv61x0_cs_count);

	return mv61x0_count_down ? ~count : count;
}

/* Returns 1 for up, -1 for down, 0 if the counter does not move */
static int __init mv61x0_count_direction(u32 *first, u32 *second)
{
	u32 a, b;
	int i;

	a = readl_relaxed(mv61x0_cs_count);
	for (i = 0; i < 1000000; i++) {
		b = readl_relaxed(mv61x0_cs_count);
		if (b != a)
			break;
		cpu_relax();
	}
	*first = a;
	*second = b;
	if (b == a)
		return 0;
	/* Started from 0 (up) or from the load value (down): no wrap yet */
	return b > a ? 1 : -1;
}

static int __init mv61x0_timer_init(struct device_node *np)
{
	void __iomem *prescaler;
	struct clk *clk;
	u32 rate, pre = 0, first, second;
	int irq, dir, ret;

	mv61x0_base = of_iomap(np, 0);
	if (!mv61x0_base) {
		pr_err("mv61x0-timer: cannot map registers\n");
		return -ENXIO;
	}

	prescaler = of_iomap(np, 1);
	if (prescaler) {
		if (!of_property_read_u32(np, "marvell,prescale", &pre))
			writel_relaxed(pre, prescaler);
		pre = readl_relaxed(prescaler);
	}

	clk = of_clk_get(np, 0);
	if (!IS_ERR(clk)) {
		ret = clk_prepare_enable(clk);
		if (ret)
			return ret;
		rate = clk_get_rate(clk);
	} else if (of_property_read_u32(np, "clock-frequency", &rate)) {
		pr_err("mv61x0-timer: no clock rate\n");
		return -EINVAL;
	}

	irq = irq_of_parse_and_map(np, MV61X0_CE_TIMER);
	if (!irq) {
		pr_err("mv61x0-timer: no interrupt for timer %d\n",
		       MV61X0_CE_TIMER);
		return -EINVAL;
	}

	/* What the boot loader left behind, for the bring-up log */
	pr_info("mv61x0-timer: wdt %08x ctrl %08x %08x %08x %08x prescale %u\n",
		readl_relaxed(mv61x0_base + MV61X0_WDT_CTRL),
		readl_relaxed(mv61x0_base + MV61X0_CTRL(0)),
		readl_relaxed(mv61x0_base + MV61X0_CTRL(1)),
		readl_relaxed(mv61x0_base + MV61X0_CTRL(2)),
		readl_relaxed(mv61x0_base + MV61X0_CTRL(3)), pre);

	/* Take over timers 1 and 2 */
	writel_relaxed(0, mv61x0_base + MV61X0_CTRL(MV61X0_CE_TIMER));
	writel_relaxed(0, mv61x0_base + MV61X0_CTRL(MV61X0_CS_TIMER));
	writel_relaxed(BIT(MV61X0_CE_TIMER) | BIT(MV61X0_CS_TIMER),
		       mv61x0_base + MV61X0_IRQ_CLEAR);

	/* Clocksource: free-running over the whole range, as the vendor does */
	mv61x0_cs_count = mv61x0_base + MV61X0_COUNT(MV61X0_CS_TIMER);
	writel_relaxed(0xffffffff, mv61x0_base + MV61X0_LOAD(MV61X0_CS_TIMER));
	writel_relaxed(MV61X0_CTRL_ENABLE | MV61X0_CTRL_RELOAD,
		       mv61x0_base + MV61X0_CTRL(MV61X0_CS_TIMER));

	dir = mv61x0_count_direction(&first, &second);
	if (!dir)
		pr_err("mv61x0-timer: timer %d count stuck at %08x\n",
		       MV61X0_CS_TIMER, first);
	else
		pr_info("mv61x0-timer: timer %d counts %s (%08x -> %08x), %u Hz\n",
			MV61X0_CS_TIMER, dir > 0 ? "up" : "down",
			first, second, rate);
	mv61x0_count_down = dir < 0;

	ret = clocksource_mmio_init(mv61x0_cs_count, "mv61x0_timer2", rate,
				    300, 32, mv61x0_count_down ?
				    clocksource_mmio_readl_down :
				    clocksource_mmio_readl_up);
	if (ret) {
		pr_err("mv61x0-timer: clocksource failed: %d\n", ret);
		return ret;
	}
	sched_clock_register(mv61x0_read_sched_clock, 32, rate);

	/* Clock event device */
	mv61x0_ticks_per_jiffy = DIV_ROUND_CLOSEST(rate, HZ);
	ret = request_irq(irq, mv61x0_timer_interrupt,
			  IRQF_TIMER | IRQF_IRQPOLL, "mv61x0_timer1",
			  &mv61x0_ce);
	if (ret) {
		pr_err("mv61x0-timer: cannot request irq %d: %d\n", irq, ret);
		return ret;
	}
	mv61x0_ce.irq = irq;
	mv61x0_ce.cpumask = cpu_possible_mask;
	clockevents_config_and_register(&mv61x0_ce, rate, 2, 0xffffffff);

	return 0;
}
TIMER_OF_DECLARE(mv61x0, "marvell,88pa6170-timer", mv61x0_timer_init);
