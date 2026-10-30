// SPDX-License-Identifier: GPL-2.0
/*
 * UPC coprocessors of the Marvell 88PA61x0 printer SoCs (88PA6170 in the
 * Sindoh DP200): two small "Dragonite" cores, each with its own ITCM, and a
 * DTCM they share. On the DP200 they run the Klipper MCU firmware: core 0
 * ("IO") heaters, fans and sensors, core 1 ("FM") the stepper engines.
 *
 * The user interface is the one of the vendor module upc.ko (mach-gogin),
 * so host/upctool and the stock application work unchanged:
 *
 *   /dev/upc0, /dev/upc1  one node per core
 *   UPC_IOC_HOLD          CPUSoftReset = 0, both cores held
 *   UPC_IOC_RUN           CPUSoftReset = 1, both cores run
 *   UPC_IOC_SEL_ITCM      read()/write() go to this core's ITCM
 *   UPC_IOC_SEL_DTCM      ... to the shared DTCM, from the offset passed
 *                         by value
 *   UPC_IOC_MBOX_WRITE    {box, value}; box 0 or 5 then waits for GPStatus
 *                         bit 0, box 1 for bit 1 (interruptible)
 *   UPC_IOC_MBOX_READ     {box, value}
 *
 * read()/write() use the file position and there is no lseek, as in the
 * vendor driver; callers reopen for each transfer. The vendor keeps the
 * ITCM/DTCM selection in globals, this driver per open file.
 *
 * Register layout (from the vendor module): ITCM of core n at the start of
 * resource n; XENA registers at UPC0 + 0x8000 with the mailboxes, GPStatus
 * (+0x150) and CPUSoftReset (+0x154); DTCM at UPC1 + 0x70000.
 *
 * Safety (new compared with the vendor driver): at probe, on a probe
 * error, on remove and shutdown, on reboot and on panic the driver holds
 * both cores and forces the outputs they drive off, as "upctool stop"
 * does: every dec_pwm block to a static low level and every stepper engine
 * aborted with its A4982 driver disabled. After a U-Boot boot the cores
 * are idle anyway. Like the vendor module at load, probe also sets the UPC
 * clock field of the APB configuration (optional "apb" range).
 *
 * XENA inputs: the endstops and the cartridge lever reach the XENA input
 * register (XIRD1) only when their SoC pads have the function the vendor's
 * board code gives them. U-Boot leaves them GPIO. With the optional
 * "xena-pads" range (consecutive pin-select registers) and
 * "marvell,xena-pad-config", probe sets them, but only after it has held
 * the cores and found every output off (user-approved: bank 5 pins 20-24
 * = 0x1003, UPC test 2c).
 *
 * Differences from stock that upctool does not notice: one mailbox
 * write-and-wait at a time but without blocking UPC_IOC_HOLD; the
 * ITCM/DTCM selection is per open file and resets to ITCM at open; DTCM
 * accesses may reach offset + position < 0x40000; a write at the end
 * returns -ENOSPC; the driver cannot be unbound.
 */
#include <linux/bitfield.h>
#include <linux/completion.h>
#include <linux/fs.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/notifier.h>
#include <linux/of.h>
#include <linux/panic_notifier.h>
#include <linux/platform_device.h>
#include <linux/reboot.h>
#include <linux/slab.h>
#include <linux/uaccess.h>

/* The vendor ioctl numbers */
struct upc_mbox {
	__u32 box;
	__u32 value;
};

#define UPC_IOC_RUN		_IOWR('u', 0x21, __u8)		/* 0xc0017521 */
#define UPC_IOC_HOLD		_IOWR('u', 0x22, __u8)		/* 0xc0017522 */
#define UPC_IOC_SEL_ITCM	_IO('u', 0x23)			/* 0x00007523 */
#define UPC_IOC_SEL_DTCM	_IOWR('u', 0x24, __u32)		/* 0xc0047524 */
#define UPC_IOC_MBOX_WRITE	_IOWR('u', 0x30, struct upc_mbox) /* 0xc0087530 */
#define UPC_IOC_MBOX_READ	_IOWR('u', 0x31, struct upc_mbox) /* 0xc0087531 */

#define UPC_NR_CORES		2
#define UPC_ITCM_SIZE		0x4000
#define UPC_DTCM_OFFSET		0x70000		/* in the UPC1 range */
#define UPC_DTCM_SIZE		0x40000

#define XENA_OFFSET		0x8000		/* in the UPC0 range */
#define XENA_MBOX0		0x128
#define XENA_MBOX1		0x12c
#define XENA_MBOX2		0x1130		/* boxes 2-5, 4 bytes apart */
#define XENA_GPSTATUS		0x150
#define XENA_SOFT_RESET		0x154
#define UPC_NR_MBOX		6

/* Outputs, see common/upc_hw.h */
#define PWM_CTRL(n)		(0x100 * (n))	/* blocks 1-32 */
#define PWM_CTRL_RUN		BIT(0)
#define PWM_CTRL_LEVEL		BIT(2)
#define PWM_FIRST		1
#define PWM_LAST		32
#define SMOT_BLOCK(n)		(0x1000 * (n))	/* engines 0-4 */
#define SMOT_ABORT		0x04
#define SMOT_ABORT_MOVE		0x100
#define SMOT_CFG		0x0c
#define SMOT_CFG_DISABLE	BIT(0)
#define SMOT_COUNT		5

/* APB configuration 0xf8000180, as upc_set_apb_xcpu_clock() */
#define APB_XCPU_CLOCK		GENMASK(7, 5)
#define APB_XCPU_CLOCK_STOCK	3

#define UPC_CHUNK		256

enum upc_tcm { UPC_ITCM, UPC_DTCM };

struct mv61x0_upc;

struct upc_core {
	struct mv61x0_upc *upc;
	struct miscdevice misc;
	char name[8];
	unsigned int index;
};

struct mv61x0_upc {
	struct device *dev;
	void __iomem *mem[UPC_NR_CORES];	/* ITCM at offset 0 */
	void __iomem *xena;
	void __iomem *dtcm;
	void __iomem *pwm;
	void __iomem *smot;
	void __iomem *apb;			/* optional: APB config, UPC clock */
	void __iomem *pads;			/* optional: XENA input pad selects */
	resource_size_t pads_size;
	struct mutex lock;
	struct mutex mbox_lock;			/* one mailbox write-and-wait */
	struct completion gp[UPC_NR_CORES];	/* GPStatus bit n, core n IRQ */
	struct upc_core core[UPC_NR_CORES];
	struct notifier_block panic_nb;
	struct notifier_block reboot_nb;
};

struct upc_file {
	struct upc_core *core;
	enum upc_tcm tcm;
	u32 dtcm_offset;
};

/*
 * Hold both cores, then force the outputs off. Lock-free and atomic, so
 * that the panic notifier can call it; every part checks its mapping.
 */
static void upc_hold_and_safe(struct mv61x0_upc *upc)
{
	unsigned int n;
	u32 c;

	if (upc->xena)
		writel(0, upc->xena + XENA_SOFT_RESET);

	if (upc->pwm) {
		for (n = PWM_FIRST; n <= PWM_LAST; n++) {
			c = readl(upc->pwm + PWM_CTRL(n));
			writel(c & ~PWM_CTRL_LEVEL, upc->pwm + PWM_CTRL(n));
			writel(c & ~(PWM_CTRL_LEVEL | PWM_CTRL_RUN),
			       upc->pwm + PWM_CTRL(n));
		}
	}

	if (upc->smot) {
		for (n = 0; n < SMOT_COUNT; n++) {
			void __iomem *b = upc->smot + SMOT_BLOCK(n);

			writel(SMOT_ABORT_MOVE, b + SMOT_ABORT);
			writel(readl(b + SMOT_CFG) | SMOT_CFG_DISABLE,
			       b + SMOT_CFG);
		}
	}
}

/* The state upc_hold_and_safe() forces: cores held, every output off */
static bool upc_outputs_safe(struct mv61x0_upc *upc)
{
	unsigned int n;

	if (readl(upc->xena + XENA_SOFT_RESET))
		return false;
	for (n = PWM_FIRST; n <= PWM_LAST; n++)
		if (readl(upc->pwm + PWM_CTRL(n)) &
		    (PWM_CTRL_RUN | PWM_CTRL_LEVEL))
			return false;
	for (n = 0; n < SMOT_COUNT; n++)
		if (!(readl(upc->smot + SMOT_BLOCK(n) + SMOT_CFG) &
		      SMOT_CFG_DISABLE))
			return false;
	return true;
}

/*
 * Give the XENA input pads their UPC function, as the vendor's
 * board_do_mpp_config does at every stock boot. Only with the cores held
 * and every output off, so that a pad that turns out to be an output can
 * only show its peripheral's idle level.
 */
static void upc_setup_input_pads(struct mv61x0_upc *upc)
{
	resource_size_t off;
	u32 val;

	if (!upc->pads)
		return;
	if (of_property_read_u32(upc->dev->of_node, "marvell,xena-pad-config",
				 &val)) {
		dev_warn(upc->dev, "xena-pads without marvell,xena-pad-config\n");
		return;
	}
	if (!upc_outputs_safe(upc)) {
		dev_err(upc->dev, "outputs not safe: XENA input pads left alone\n");
		return;
	}
	for (off = 0; off + 4 <= upc->pads_size; off += 4) {
		u32 old = readl(upc->pads + off);

		writel(val, upc->pads + off);
		dev_info(upc->dev, "XENA input pad %u: %08x -> %08x\n",
			 (unsigned int)(off / 4), old, readl(upc->pads + off));
	}
	if (!upc_outputs_safe(upc))
		dev_err(upc->dev, "outputs not safe after the pad setup\n");
}

static void __iomem *upc_mbox_reg(struct mv61x0_upc *upc, u32 box)
{
	switch (box) {
	case 0:
		return upc->xena + XENA_MBOX0;
	case 1:
		return upc->xena + XENA_MBOX1;
	default:
		return upc->xena + XENA_MBOX2 + 4 * (box - 2);
	}
}

static int upc_open(struct inode *inode, struct file *file)
{
	struct upc_core *core = container_of(file->private_data,
					     struct upc_core, misc);
	struct upc_file *uf;

	uf = kzalloc(sizeof(*uf), GFP_KERNEL);
	if (!uf)
		return -ENOMEM;
	uf->core = core;
	uf->tcm = UPC_ITCM;
	file->private_data = uf;
	return 0;
}

static int upc_release(struct inode *inode, struct file *file)
{
	kfree(file->private_data);
	return 0;
}

/* Where a transfer of *count bytes at pos lands; shortens *count */
static void __iomem *upc_tcm_window(struct upc_file *uf, loff_t pos,
				    size_t *count)
{
	struct mv61x0_upc *upc = uf->core->upc;
	void __iomem *base;
	loff_t start, size;

	if (uf->tcm == UPC_ITCM) {
		base = upc->mem[uf->core->index];
		start = pos;
		size = UPC_ITCM_SIZE;
	} else {
		base = upc->dtcm;
		start = (loff_t)uf->dtcm_offset + pos;
		size = UPC_DTCM_SIZE;
	}
	if (pos < 0 || start >= size)
		return NULL;
	if (*count > size - start)
		*count = size - start;
	return base + start;
}

static ssize_t upc_write(struct file *file, const char __user *buf,
			 size_t count, loff_t *ppos)
{
	struct upc_file *uf = file->private_data;
	struct mv61x0_upc *upc = uf->core->upc;
	u8 chunk[UPC_CHUNK];
	void __iomem *dst;
	size_t done = 0, n, i;

	mutex_lock(&upc->lock);
	dst = upc_tcm_window(uf, *ppos, &count);
	if (!dst) {
		mutex_unlock(&upc->lock);
		return count ? -ENOSPC : 0;
	}
	while (done < count) {
		n = min_t(size_t, count - done, UPC_CHUNK);
		if (copy_from_user(chunk, buf + done, n)) {
			mutex_unlock(&upc->lock);
			return done ? done : -EFAULT;
		}
		/* Byte writes, as the vendor driver does for both TCMs */
		for (i = 0; i < n; i++)
			writeb(chunk[i], dst + done + i);
		done += n;
	}
	mutex_unlock(&upc->lock);

	*ppos += done;
	return done;
}

static ssize_t upc_read(struct file *file, char __user *buf, size_t count,
			loff_t *ppos)
{
	struct upc_file *uf = file->private_data;
	struct mv61x0_upc *upc = uf->core->upc;
	u8 chunk[UPC_CHUNK];
	void __iomem *src;
	size_t done = 0, n, i;

	mutex_lock(&upc->lock);
	src = upc_tcm_window(uf, *ppos, &count);
	if (!src) {
		mutex_unlock(&upc->lock);
		return 0;
	}
	while (done < count) {
		n = min_t(size_t, count - done, UPC_CHUNK);
		for (i = 0; i < n; i++)
			chunk[i] = readb(src + done + i);
		if (copy_to_user(buf + done, chunk, n)) {
			mutex_unlock(&upc->lock);
			return done ? done : -EFAULT;
		}
		done += n;
	}
	mutex_unlock(&upc->lock);

	*ppos += done;
	return done;
}

static long upc_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct upc_file *uf = file->private_data;
	struct mv61x0_upc *upc = uf->core->upc;
	struct upc_mbox mb;
	struct completion *done;
	bool wait;
	int ret;

	switch (cmd) {
	case UPC_IOC_HOLD:
	case UPC_IOC_RUN:
		mutex_lock(&upc->lock);
		writel(cmd == UPC_IOC_RUN, upc->xena + XENA_SOFT_RESET);
		mutex_unlock(&upc->lock);
		return 0;

	case UPC_IOC_SEL_ITCM:
		uf->tcm = UPC_ITCM;
		return 0;

	case UPC_IOC_SEL_DTCM:
		if (arg >= UPC_DTCM_SIZE)
			return -EINVAL;
		uf->tcm = UPC_DTCM;
		uf->dtcm_offset = arg;
		return 0;

	case UPC_IOC_MBOX_WRITE:
		if (copy_from_user(&mb, (void __user *)arg, sizeof(mb)))
			return -EFAULT;
		if (mb.box >= UPC_NR_MBOX)
			return -EINVAL;
		/* Box 0 and 5 wait for GPStatus bit 0 (core 0), box 1 for bit 1 */
		wait = mb.box == 0 || mb.box == 1 || mb.box == 5;
		done = &upc->gp[mb.box == 1];
		/*
		 * Like stock, one mailbox write-and-wait at a time; unlike
		 * stock, without the register lock, so UPC_IOC_HOLD still works
		 * while a wait is pending.
		 */
		mutex_lock(&upc->mbox_lock);
		if (wait)
			reinit_completion(done);
		mutex_lock(&upc->lock);
		writel(mb.value, upc_mbox_reg(upc, mb.box));
		mutex_unlock(&upc->lock);
		ret = wait ? wait_for_completion_interruptible(done) : 0;
		mutex_unlock(&upc->mbox_lock);
		/* -EINTR as stock: a restarted ioctl would send the command twice */
		return ret ? -EINTR : 0;

	case UPC_IOC_MBOX_READ:
		if (copy_from_user(&mb, (void __user *)arg, sizeof(mb)))
			return -EFAULT;
		if (mb.box >= UPC_NR_MBOX)
			return -EINVAL;
		mutex_lock(&upc->lock);
		mb.value = readl(upc_mbox_reg(upc, mb.box));
		mutex_unlock(&upc->lock);
		if (copy_to_user((void __user *)arg, &mb, sizeof(mb)))
			return -EFAULT;
		return 0;
	}

	return -ENOTTY;
}

static const struct file_operations upc_fops = {
	.owner		= THIS_MODULE,
	.open		= upc_open,
	.release	= upc_release,
	.read		= upc_read,
	.write		= upc_write,
	.unlocked_ioctl	= upc_ioctl,
	/* no .llseek: lseek() fails with -ESPIPE, as with the vendor driver */
};

/*
 * Core n raises GPStatus bit n on its own interrupt line. Clear that bit
 * only, as stock does per device, and wake the mailbox waiter for it. A
 * line without its bit set is not ours, so a stuck line can be disabled.
 */
static irqreturn_t upc_irq(int irq, void *data)
{
	struct upc_core *core = data;
	struct mv61x0_upc *upc = core->upc;
	u32 bit = BIT(core->index);
	u32 gp;

	gp = readl(upc->xena + XENA_GPSTATUS);
	if (!(gp & bit))
		return IRQ_NONE;
	writel(gp & ~bit, upc->xena + XENA_GPSTATUS);
	complete(&upc->gp[core->index]);

	return IRQ_HANDLED;
}

static int upc_panic(struct notifier_block *nb, unsigned long event,
		     void *data)
{
	upc_hold_and_safe(container_of(nb, struct mv61x0_upc, panic_nb));
	pr_emerg("mv61x0-upc: panic: cores held, outputs off\n");
	return NOTIFY_DONE;
}

static int upc_reboot(struct notifier_block *nb, unsigned long event,
		      void *data)
{
	struct mv61x0_upc *upc = container_of(nb, struct mv61x0_upc, reboot_nb);

	upc_hold_and_safe(upc);
	dev_info(upc->dev, "reboot: cores held, outputs off\n");
	return NOTIFY_DONE;
}

static void __iomem *upc_map(struct platform_device *pdev, const char *name,
			     resource_size_t min_size)
{
	struct resource *res;

	res = platform_get_resource_byname(pdev, IORESOURCE_MEM, name);
	if (!res || resource_size(res) < min_size)
		return NULL;
	/* No request_mem_region: upctool keeps using /dev/mem for DTCM */
	return devm_ioremap(&pdev->dev, res->start, resource_size(res));
}

static int mv61x0_upc_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct mv61x0_upc *upc;
	u32 reset, gp;
	int i, irq, ret;

	upc = devm_kzalloc(dev, sizeof(*upc), GFP_KERNEL);
	if (!upc)
		return -ENOMEM;
	upc->dev = dev;
	mutex_init(&upc->lock);
	mutex_init(&upc->mbox_lock);
	for (i = 0; i < UPC_NR_CORES; i++)
		init_completion(&upc->gp[i]);
	for (i = 0; i < UPC_NR_CORES; i++) {
		upc->core[i].upc = upc;
		upc->core[i].index = i;
	}
	platform_set_drvdata(pdev, upc);

	/* Map what exists first, so that every error below can make safe */
	upc->mem[0] = upc_map(pdev, "upc0", XENA_OFFSET + 0x2000);
	upc->mem[1] = upc_map(pdev, "upc1", UPC_DTCM_OFFSET + UPC_DTCM_SIZE);
	upc->pwm = upc_map(pdev, "pwm", PWM_CTRL(PWM_LAST) + 4);
	upc->smot = upc_map(pdev, "smot", SMOT_BLOCK(SMOT_COUNT - 1) + 0x100);
	if (upc->mem[0])
		upc->xena = upc->mem[0] + XENA_OFFSET;
	if (upc->mem[1])
		upc->dtcm = upc->mem[1] + UPC_DTCM_OFFSET;

	/*
	 * The vendor module's init_module sets the UPC (XCPU) clock field of
	 * the APB configuration, bits 7:5, to 3 before anything else touches
	 * the cores; Klipper's ~396 MHz FM clock was measured with that.
	 */
	upc->apb = upc_map(pdev, "apb", 4);
	if (upc->apb) {
		u32 apb = readl(upc->apb);

		writel((apb & ~APB_XCPU_CLOCK) |
		       FIELD_PREP(APB_XCPU_CLOCK, APB_XCPU_CLOCK_STOCK),
		       upc->apb);
		dev_info(dev, "APB config %08x -> %08x\n", apb, readl(upc->apb));
	}

	reset = upc->xena ? readl(upc->xena + XENA_SOFT_RESET) : 0;
	gp = upc->xena ? readl(upc->xena + XENA_GPSTATUS) : 0;
	upc_hold_and_safe(upc);

	if (!upc->mem[0] || !upc->mem[1] || !upc->pwm || !upc->smot) {
		dev_err(dev, "missing or short register range\n");
		ret = -ENXIO;
		goto fail;
	}

	upc->pads = upc_map(pdev, "xena-pads", 4);
	if (upc->pads)
		upc->pads_size = resource_size(platform_get_resource_byname(pdev,
					IORESOURCE_MEM, "xena-pads"));
	upc_setup_input_pads(upc);

	for (i = 0; i < UPC_NR_CORES; i++) {
		irq = platform_get_irq(pdev, i);
		if (irq < 0) {
			ret = irq;
			goto fail;
		}
		ret = devm_request_irq(dev, irq, upc_irq, 0, dev_name(dev),
				       &upc->core[i]);
		if (ret)
			goto fail;
	}

	for (i = 0; i < UPC_NR_CORES; i++) {
		struct upc_core *core = &upc->core[i];

		snprintf(core->name, sizeof(core->name), "upc%d", i);
		core->misc.minor = MISC_DYNAMIC_MINOR;
		core->misc.name = core->name;
		core->misc.fops = &upc_fops;
		core->misc.parent = dev;
		ret = misc_register(&core->misc);
		if (ret) {
			while (--i >= 0)
				misc_deregister(&upc->core[i].misc);
			goto fail;
		}
	}

	upc->panic_nb.notifier_call = upc_panic;
	upc->panic_nb.priority = INT_MAX;
	atomic_notifier_chain_register(&panic_notifier_list, &upc->panic_nb);
	upc->reboot_nb.notifier_call = upc_reboot;
	upc->reboot_nb.priority = INT_MAX;
	register_reboot_notifier(&upc->reboot_nb);

	dev_info(dev, "cores held, outputs safe (CPUSoftReset was %u, GPStatus %08x)\n",
		 reset, gp);
	return 0;

fail:
	upc_hold_and_safe(upc);
	dev_err(dev, "probe failed (%d); cores held, outputs safe\n", ret);
	return ret;
}

static void mv61x0_upc_remove(struct platform_device *pdev)
{
	struct mv61x0_upc *upc = platform_get_drvdata(pdev);
	int i;

	unregister_reboot_notifier(&upc->reboot_nb);
	atomic_notifier_chain_unregister(&panic_notifier_list, &upc->panic_nb);
	for (i = 0; i < UPC_NR_CORES; i++)
		misc_deregister(&upc->core[i].misc);
	upc_hold_and_safe(upc);
}

static void mv61x0_upc_shutdown(struct platform_device *pdev)
{
	upc_hold_and_safe(platform_get_drvdata(pdev));
}

static const struct of_device_id mv61x0_upc_of_match[] = {
	{ .compatible = "marvell,88pa6170-upc" },
	{ }
};
MODULE_DEVICE_TABLE(of, mv61x0_upc_of_match);

static struct platform_driver mv61x0_upc_driver = {
	.probe		= mv61x0_upc_probe,
	.remove		= mv61x0_upc_remove,
	.shutdown	= mv61x0_upc_shutdown,
	.driver		= {
		.name		= "mv61x0-upc",
		/* no unbind: open files would outlive the state */
		.suppress_bind_attrs = true,
		.of_match_table	= mv61x0_upc_of_match,
	},
};
module_platform_driver(mv61x0_upc_driver);

MODULE_DESCRIPTION("Marvell 88PA61x0 UPC coprocessors (vendor upc.ko ABI)");
MODULE_LICENSE("GPL");
