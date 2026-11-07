/* SPDX-License-Identifier: GPL-2.0 */
/*
 * 88PA61x0 PJ4B-MP erratum 6011, the way the Marvell 3.2 vendor kernel of
 * the 88PA6170 works around it (CONFIG_PJ4B_ERRATA_6011): every LDREX is
 * issued five times, and in kernel atomics and locks with IRQs disabled
 * around the exclusive sequence. Test option for the nandboot hangs
 * (docs/kernel/nandboot_hang_analysis.md).
 *
 * __PJ4B_LDREX("ldrex %0, [%3]") gives the four extra loads, to put right
 * before the original one (so a "1:" label stays on the first load).
 */
#ifndef __ASM_ARM_PJ4B_6011_H
#define __ASM_ARM_PJ4B_6011_H

#ifdef CONFIG_PJ4B_ERRATA_6011
#include <asm/irqflags.h>

#define __PJ4B_LDREX(i)		i "\n\t" i "\n\t" i "\n\t" i "\n\t"
#define pj4b_6011_save(f)	((f) = arch_local_irq_save())
#define pj4b_6011_restore(f)	arch_local_irq_restore(f)
#else
#define __PJ4B_LDREX(i)
#define pj4b_6011_save(f)	((void)((f) = 0))
#define pj4b_6011_restore(f)	((void)(f))
#endif

#endif /* __ASM_ARM_PJ4B_6011_H */
