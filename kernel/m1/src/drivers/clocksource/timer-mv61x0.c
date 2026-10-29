// SPDX-License-Identifier: GPL-2.0
/*
 * Timer block of the Marvell 88PA61x0 printer SoCs (88PA6170 in the
 * Sindoh DP200).
 *
 * Four 32-bit timers that count up from 0 to their load value. The layout
 * and the programming sequences follow the vendor 3.2 kernel
 * (timer_set_next_event, timer_set_mode, enable_timer, timer_interrupt):
 *
 *   +0x00             watchdog control (timer 0): bit 31 enable, the low
 *                     nibble is toggled to kick it
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
 * runs free over the full 32 bits as clocksource and sched_clock, and the
 * interrupts of all four timers are taken and acknowledged.
 */

#include <linux/clk.h>
#include <linux/clockchips.h>
#include <linux/clocksource.h>
#include <linux/delay.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/irq.h>
#include <linux/moduleparam.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/of_irq.h>
#include <linux/reboot.h>
#include <linux/sched_clock.h>

#define MV61X0_WDT_CTRL		0x00
#define MV61X0_LOAD(n)		(0x04 + 0x10 * (n))
#define MV61X0_CTRL(n)		(0x08 + 0x10 * (n))
#define MV61X0_COUNT(n)		(0x0c + 0x10 * (n))
#define MV61X0_IRQ_STATUS	0x10
#define MV61X0_IRQ_CLEAR	0x20

#define MV61X0_CTRL_ENABLE	BIT(0)
#define MV61X0_CTRL_RELOAD	BIT(1)
#define MV61X0_WDT_ENABLE	BIT(31)

#define MV61X0_NR_TIMERS	4
#define MV61X0_WDT_TIMER	0
#define MV61X0_CE_TIMER		1
#define MV61X0_CS_TIMER		2

/* Two back-to-back reads of the 1 MHz counter must be this close */
#define MV61X0_MAX_STEP		1000

static void __iomem *mv61x0_base;
static void __iomem *mv61x0_cs_count;
static u32 mv61x0_ticks_per_jiffy;

/*
 * The first boot of milestone 1 saw the clock jump by 2^32 us now and
 * then. One read with a high bit wrong does that: timekeeping takes it as
 * a forward step, and the next good read as another one. Rejected reads
 * are counted here: /sys/module/timer_mv61x0/parameters/.
 */
static unsigned int mv61x0_glitches;
module_param_named(glitches, mv61x0_glitches, uint, 0444);
static unsigned int mv61x0_glitch_first;
module_param_named(glitch_first, mv61x0_glitch_first, uint, 0444);
static unsigned int mv61x0_glitch_second;
module_param_named(glitch_second, mv61x0_glitch_second, uint, 0444);

static u32 notrace mv61x0_read_count(void)
{
	u32 a, b;
	int i;

	a = readl_relaxed(mv61x0_cs_count);
	for (i = 0; i < 4; i++) {
		b = readl_relaxed(mv61x0_cs_count);
		if (b - a <= MV61X0_MAX_STEP)
			return b;
		mv61x0_glitches++;
		mv61x0_glitch_first = a;
		mv61x0_glitch_second = b;
		a = b;
	}
	return b;
}

static u64 mv61x0_cs_read(struct clocksource *cs)
{
	return mv61x0_read_count();
}

static struct clocksource mv61x0_cs = {
	.name	= "mv61x0_timer2",
	.rating	= 300,
	.read	= mv61x0_cs_read,
	.mask	= CLOCKSOURCE_MASK(32),
	.flags	= CLOCK_SOURCE_IS_CONTINUOUS,
};

static u64 notrace mv61x0_read_sched_clock(void)
{
	return mv61x0_read_count();
}

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

/* Acknowledge timer n's status bit; true if it was set */
static bool mv61x0_ack(unsigned int n)
{
	if (!(readl_relaxed(mv61x0_base + MV61X0_IRQ_STATUS) & BIT(n)))
		return false;
	writel_relaxed(BIT(n), mv61x0_base + MV61X0_IRQ_CLEAR);
	return true;
}

static irqreturn_t mv61x0_timer_interrupt(int irq, void *dev_id)
{
	struct clock_event_device *ce = dev_id;
	static unsigned int count;

	if (!mv61x0_ack(MV61X0_CE_TIMER))
		return IRQ_NONE;

	/* Bring-up trace: tick rate against the raw clocksource */
	count++;
	if (count <= 3 || count == 100 || count == 1000 || count == 10000)
		pr_info("mv61x0-timer: timer 1 irq #%u at timer 2 count %08x\n",
			count, readl_relaxed(mv61x0_cs_count));

	if (clockevent_state_oneshot(ce))
		mv61x0_ce_stop();
	ce->event_handler(ce);

	return IRQ_HANDLED;
}

/* Timers 0, 2 and 3: acknowledge only, as the vendor's default_callback */
static irqreturn_t mv61x0_ack_interrupt(int irq, void *dev_id)
{
	return mv61x0_ack((unsigned long)dev_id) ? IRQ_HANDLED : IRQ_NONE;
}

/* U-Boot's reset_cpu: let the watchdog on timer 0 run out after 1 ms */
static int mv61x0_restart(struct notifier_block *nb, unsigned long mode,
			  void *cmd)
{
	void __iomem *wdt = mv61x0_base + MV61X0_WDT_CTRL;

	writel(readl(wdt) ^ 0xf, wdt);
	writel(0, mv61x0_base + MV61X0_CTRL(MV61X0_WDT_TIMER));
	writel(1000, mv61x0_base + MV61X0_LOAD(MV61X0_WDT_TIMER));
	writel(MV61X0_CTRL_ENABLE | MV61X0_CTRL_RELOAD,
	       mv61x0_base + MV61X0_CTRL(MV61X0_WDT_TIMER));
	writel((readl(wdt) ^ 0xf) | MV61X0_WDT_ENABLE, wdt);
	mdelay(1000);

	return NOTIFY_DONE;
}

static struct notifier_block mv61x0_restart_nb = {
	.notifier_call	= mv61x0_restart,
	.priority	= 128,
};

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
	unsigned long n;

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

	/* What the boot loader left behind, for the bring-up log */
	pr_info("mv61x0-timer: wdt %08x ctrl %08x %08x %08x %08x status %08x prescale %u\n",
		readl_relaxed(mv61x0_base + MV61X0_WDT_CTRL),
		readl_relaxed(mv61x0_base + MV61X0_CTRL(0)),
		readl_relaxed(mv61x0_base + MV61X0_CTRL(1)),
		readl_relaxed(mv61x0_base + MV61X0_CTRL(2)),
		readl_relaxed(mv61x0_base + MV61X0_CTRL(3)),
		readl_relaxed(mv61x0_base + MV61X0_IRQ_STATUS), pre);

	/*
	 * The kexec loader (netload, KEXEC_WDT) may arm the watchdog so that
	 * a kernel which never gets here resets the board: we got here, so
	 * stop it. U-Boot leaves it off (wdt 0000000f, ctrl 0).
	 */
	if ((readl_relaxed(mv61x0_base + MV61X0_WDT_CTRL) & MV61X0_WDT_ENABLE) ||
	    (readl_relaxed(mv61x0_base + MV61X0_CTRL(MV61X0_WDT_TIMER)) &
	     MV61X0_CTRL_ENABLE)) {
		void __iomem *wdt = mv61x0_base + MV61X0_WDT_CTRL;

		writel(0, mv61x0_base + MV61X0_CTRL(MV61X0_WDT_TIMER));
		writel((readl(wdt) ^ 0xf) & ~MV61X0_WDT_ENABLE, wdt);
		pr_info("mv61x0-timer: stopped the watchdog the loader armed (wdt %08x)\n",
			readl(wdt));
	}

	/* Take over timers 1 and 2 */
	writel_relaxed(0, mv61x0_base + MV61X0_CTRL(MV61X0_CE_TIMER));
	writel_relaxed(0, mv61x0_base + MV61X0_CTRL(MV61X0_CS_TIMER));

	/* Clocksource: free-running over the whole range, as the vendor does */
	mv61x0_cs_count = mv61x0_base + MV61X0_COUNT(MV61X0_CS_TIMER);
	writel_relaxed(0xffffffff, mv61x0_base + MV61X0_LOAD(MV61X0_CS_TIMER));
	writel_relaxed(MV61X0_CTRL_ENABLE | MV61X0_CTRL_RELOAD,
		       mv61x0_base + MV61X0_CTRL(MV61X0_CS_TIMER));

	dir = mv61x0_count_direction(&first, &second);
	pr_info("mv61x0-timer: timer %d counts %s (%08x -> %08x), %u Hz, status %08x\n",
		MV61X0_CS_TIMER, dir > 0 ? "up" : dir < 0 ? "DOWN" : "NOT AT ALL",
		first, second, rate,
		readl_relaxed(mv61x0_base + MV61X0_IRQ_STATUS));

	/* Drop whatever is pending, after the restart of timer 2 */
	writel_relaxed(GENMASK(MV61X0_NR_TIMERS - 1, 0),
		       mv61x0_base + MV61X0_IRQ_CLEAR);

	ret = clocksource_register_hz(&mv61x0_cs, rate);
	if (ret) {
		pr_err("mv61x0-timer: clocksource failed: %d\n", ret);
		return ret;
	}
	sched_clock_register(mv61x0_read_sched_clock, 32, rate);

	/* Interrupts of the timers this driver does not drive: ack only */
	for (n = 0; n < MV61X0_NR_TIMERS; n++) {
		static const char *const names[MV61X0_NR_TIMERS] = {
			"mv61x0_timer0", NULL, "mv61x0_timer2", "mv61x0_timer3",
		};

		if (n == MV61X0_CE_TIMER)
			continue;
		irq = irq_of_parse_and_map(np, n);
		if (!irq || request_irq(irq, mv61x0_ack_interrupt, 0,
					names[n], (void *)n))
			pr_warn("mv61x0-timer: no interrupt for timer %lu\n", n);
	}

	/* Clock event device */
	irq = irq_of_parse_and_map(np, MV61X0_CE_TIMER);
	if (!irq) {
		pr_err("mv61x0-timer: no interrupt for timer %d\n",
		       MV61X0_CE_TIMER);
		return -EINVAL;
	}
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

	register_restart_handler(&mv61x0_restart_nb);

	return 0;
}
TIMER_OF_DECLARE(mv61x0, "marvell,88pa6170-timer", mv61x0_timer_init);
