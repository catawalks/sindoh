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
#include <linux/nmi.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/of_irq.h>
#include <linux/reboot.h>
#include <linux/sched_clock.h>
#include <linux/smp.h>
#include <linux/workqueue.h>

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
static u32 mv61x0_rate;

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

/* Timer 1 interrupts taken, for the tick check below */
static unsigned int mv61x0_ce_irqs;

static irqreturn_t mv61x0_timer_interrupt(int irq, void *dev_id)
{
	struct clock_event_device *ce = dev_id;
	unsigned int count;

	if (!mv61x0_ack(MV61X0_CE_TIMER))
		return IRQ_NONE;

	/* Bring-up trace: tick rate against the raw clocksource */
	count = mv61x0_ce_irqs + 1;
	WRITE_ONCE(mv61x0_ce_irqs, count);
	if (count <= 3 || count == 100 || count == 1000 || count == 10000)
		pr_info("mv61x0-timer: timer 1 irq #%u at timer 2 count %08x\n",
			count, readl_relaxed(mv61x0_cs_count));

	if (clockevent_state_oneshot(ce))
		mv61x0_ce_stop();
	ce->event_handler(ce);

	return IRQ_HANDLED;
}

/*
 * Tick check, for debug images only (docs/kernel/nandboot_hang_analysis.md,
 * hang 9): timer_mv61x0.tick_check=MS runs timer 3 every MS ms, with its
 * interrupt on CPU1, and watches timer 1's interrupt count. Timer 1 is the
 * only tick: CPU1's comes from CPU0 by broadcast IPI, so if timer 1's
 * interrupt stops, every timer, the hang watchdog's kicks and the lockup
 * detectors stop on both CPUs, while the CPUs may still be running. After
 * 200 ms without one this prints the timer and GIC state of timer 1's
 * interrupt (then every second) and pings CPU0 by IPI, at 2 s it asks all
 * CPUs for a backtrace, and at 3 s it panics, so the log lands in pstore.
 * A stalled bus stops CPU1 in its first register read, and nothing is
 * printed: that tells the two apart. Off (0) by default.
 */
static unsigned int mv61x0_tick_check;
module_param_named(tick_check, mv61x0_tick_check, uint, 0444);
static void __iomem *mv61x0_gicd, *mv61x0_gicc;
static int mv61x0_t3_irq;
static unsigned int mv61x0_pongs;
static call_single_data_t mv61x0_ping_csd;
static bool mv61x0_tick_armed;

static void mv61x0_pong(void *unused)
{
	WRITE_ONCE(mv61x0_pongs, mv61x0_pongs + 1);
}

static void mv61x0_tick_report(unsigned int ms, unsigned int pings)
{
	void __iomem *d = mv61x0_gicd;
	unsigned int hw = irqd_to_hwirq(irq_get_irq_data(mv61x0_ce.irq));
	u32 bit = BIT(hw % 32), w = 4 * (hw / 32);

	pr_emerg("mv61x0-timer: tick check: no timer 1 irq for %u ms (cpu%d, jiffies %08lx, irq #%u, cpu0 pongs %u/%u): t1 ctrl %08x load %08x count %08x status %08x t2 %08x\n",
		 ms, smp_processor_id(), jiffies, READ_ONCE(mv61x0_ce_irqs),
		 READ_ONCE(mv61x0_pongs), pings,
		 readl_relaxed(mv61x0_base + MV61X0_CTRL(MV61X0_CE_TIMER)),
		 readl_relaxed(mv61x0_base + MV61X0_LOAD(MV61X0_CE_TIMER)),
		 readl_relaxed(mv61x0_base + MV61X0_COUNT(MV61X0_CE_TIMER)),
		 readl_relaxed(mv61x0_base + MV61X0_IRQ_STATUS),
		 readl_relaxed(mv61x0_cs_count));
	if (d && mv61x0_gicc)
		pr_emerg("mv61x0-timer: tick check: gic hwirq %u en %d pend %d act %d tgt %02x prio %02x dctlr %x; cpu%d gicc ctlr %x pmr %02x rpr %02x hppir %03x\n",
			 hw, !!(readl_relaxed(d + 0x100 + w) & bit),
			 !!(readl_relaxed(d + 0x200 + w) & bit),
			 !!(readl_relaxed(d + 0x300 + w) & bit),
			 readb_relaxed(d + 0x800 + hw),
			 readb_relaxed(d + 0x400 + hw), readl_relaxed(d),
			 smp_processor_id(), readl_relaxed(mv61x0_gicc),
			 readl_relaxed(mv61x0_gicc + 0x04),
			 readl_relaxed(mv61x0_gicc + 0x14),
			 readl_relaxed(mv61x0_gicc + 0x18));
}

static void mv61x0_tick_check_irq(void)
{
	static unsigned int last, stuck, pings;
	unsigned int now = READ_ONCE(mv61x0_ce_irqs);
	unsigned int p = mv61x0_tick_check, ms;

	if (now != last) {
		last = now;
		stuck = 0;
		return;
	}
	ms = ++stuck * p;
	if (ms < 200)
		return;
	if (ms - p < 200 || ms / 1000 != (ms - p) / 1000) {
		mv61x0_tick_report(ms, pings);
		if (!smp_call_function_single_async(0, &mv61x0_ping_csd))
			pings++;
	}
	if (ms >= 2000 && ms - p < 2000)
		trigger_all_cpu_backtrace();
	if (ms >= 3000)
		panic("mv61x0-timer: tick check: timer 1 interrupts stopped");
}

static int __init mv61x0_tick_check_init(void)
{
	struct device_node *np;
	unsigned int ms = mv61x0_tick_check;

	if (!mv61x0_base || !ms || mv61x0_t3_irq <= 0)
		return 0;
	ms = clamp(ms, 10U, 100U);
	mv61x0_tick_check = ms;
	np = of_find_compatible_node(NULL, NULL, "arm,cortex-a9-gic");
	if (np) {
		mv61x0_gicd = of_iomap(np, 0);
		mv61x0_gicc = of_iomap(np, 1);
		of_node_put(np);
	}
	INIT_CSD(&mv61x0_ping_csd, mv61x0_pong, NULL);
	if (cpu_online(1))
		irq_set_affinity(mv61x0_t3_irq, cpumask_of(1));

	WRITE_ONCE(mv61x0_tick_armed, true);
	writel_relaxed(0, mv61x0_base + MV61X0_CTRL(3));
	writel_relaxed(ms * (mv61x0_rate / 1000), mv61x0_base + MV61X0_LOAD(3));
	writel(MV61X0_CTRL_ENABLE | MV61X0_CTRL_RELOAD,
	       mv61x0_base + MV61X0_CTRL(3));
	pr_warn("mv61x0-timer: tick check every %u ms on timer 3 (irq %d, cpu%d): panics 3 s after the last timer 1 irq\n",
		ms, mv61x0_t3_irq, cpu_online(1) ? 1 : 0);
	return 0;
}
late_initcall(mv61x0_tick_check_init);

/* Timers 0, 2 and 3: acknowledge only, as the vendor's default_callback */
static irqreturn_t mv61x0_ack_interrupt(int irq, void *dev_id)
{
	unsigned long n = (unsigned long)dev_id;

	if (!mv61x0_ack(n))
		return IRQ_NONE;
	if (n == 3 && READ_ONCE(mv61x0_tick_armed))
		mv61x0_tick_check_irq();
	return IRQ_HANDLED;
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

/*
 * Hang watchdog, for debug images only (docs/kernel/nandboot_hang_analysis.md;
 * each run needs the owner's OK): timer_mv61x0.hang_wdt=SECONDS arms the
 * watchdog on timer 0 at late_initcall, and a kworker kicks it every 5 s the
 * way the vendor's service_watchdog_timer does (low nibble toggled, enable
 * set). A hard hang then resets the board by itself after SECONDS. Off (0)
 * by default. hang_wdt_nokick=1 stops the kicks, to test the reset.
 * Note: after "poweroff" the board resets again once SECONDS are up.
 */
static unsigned int mv61x0_hang_wdt;
module_param_named(hang_wdt, mv61x0_hang_wdt, uint, 0444);
static bool mv61x0_hang_wdt_nokick;
module_param_named(hang_wdt_nokick, mv61x0_hang_wdt_nokick, bool, 0644);
static struct delayed_work mv61x0_wdt_work;

#define MV61X0_HANG_WDT_KICK	(5 * HZ)

static void mv61x0_wdt_kick(struct work_struct *work)
{
	void __iomem *wdt = mv61x0_base + MV61X0_WDT_CTRL;

	if (!READ_ONCE(mv61x0_hang_wdt_nokick))
		writel((readl(wdt) ^ 0xf) | MV61X0_WDT_ENABLE, wdt);
	schedule_delayed_work(&mv61x0_wdt_work, MV61X0_HANG_WDT_KICK);
}

static int __init mv61x0_hang_wdt_init(void)
{
	void __iomem *wdt = mv61x0_base + MV61X0_WDT_CTRL;
	unsigned int secs = mv61x0_hang_wdt;

	if (!mv61x0_base || !secs)
		return 0;
	/* a 32-bit count of timer ticks; at least two kicks per period */
	secs = clamp(secs, 15U, U32_MAX / mv61x0_rate);
	mv61x0_hang_wdt = secs;

	/* U-Boot's reset_cpu sequence (mv61x0_restart) with a long count */
	writel(readl(wdt) ^ 0xf, wdt);
	writel(0, mv61x0_base + MV61X0_CTRL(MV61X0_WDT_TIMER));
	writel(secs * mv61x0_rate, mv61x0_base + MV61X0_LOAD(MV61X0_WDT_TIMER));
	writel(MV61X0_CTRL_ENABLE | MV61X0_CTRL_RELOAD,
	       mv61x0_base + MV61X0_CTRL(MV61X0_WDT_TIMER));
	writel((readl(wdt) ^ 0xf) | MV61X0_WDT_ENABLE, wdt);

	INIT_DELAYED_WORK(&mv61x0_wdt_work, mv61x0_wdt_kick);
	schedule_delayed_work(&mv61x0_wdt_work, MV61X0_HANG_WDT_KICK);
	pr_warn("mv61x0-timer: hang watchdog armed: reset after %u s without a kick (every 5 s)\n",
		secs);
	return 0;
}
late_initcall(mv61x0_hang_wdt_init);

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
	mv61x0_rate = rate;

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
		else if (n == 3)
			mv61x0_t3_irq = irq;
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
