/* SPDX-License-Identifier: GPL-2.0 */
/*
 * 88PA61x0 PJ4B-MP erratum 6011, the way the Marvell 3.2 vendor kernel of
 * the 88PA6170 works around it (CONFIG_PJ4B_ERRATA_6011): every LDREX is
 * issued five times. In kernel atomics, cmpxchg and locks IRQs are off for
 * the five loads only, and back on before the STREX, the WFE and the retry
 * branch, as in the vendor's bitops and rwlocks. So no retry loop and no
 * lock wait ever runs with IRQs masked by the workaround: two CPUs
 * retrying against each other with IRQs off could never be broken up
 * (docs/kernel/smp_freeze_summary.md).
 *
 * __PJ4B_LDREX_IRQ("ldrex %0, [%3]") goes right before the original load
 * and replaces it: it ends in "@", which comments the original out. Sites
 * that use it list ip as clobbered (__PJ4B_CLOBBER after "cc", or
 * __PJ4B_CLOBBER_ONLY where there is no clobber list).
 *
 * __PJ4B_LDREX("ldrex %0, [%3]") gives four extra loads and no IRQ
 * masking, for user-memory sequences with fixups on the load (futex, SWP
 * emulation), like the vendor's kuser helpers.
 */
#ifndef __ASM_ARM_PJ4B_6011_H
#define __ASM_ARM_PJ4B_6011_H

#ifdef CONFIG_PJ4B_ERRATA_6011
#define __PJ4B_LDREX(i)		i "\n\t" i "\n\t" i "\n\t" i "\n\t"
#define __PJ4B_LDREX_IRQ(i)	"mrs	ip, cpsr\n\tcpsid	i\n\t"		\
				i "\n\t" i "\n\t" i "\n\t" i "\n\t" i "\n\t"	\
				"msr	cpsr_c, ip\n\t@ "
#define __PJ4B_CLOBBER		, "ip"
#define __PJ4B_CLOBBER_ONLY	: "ip"
#else
#define __PJ4B_LDREX(i)
#define __PJ4B_LDREX_IRQ(i)
#define __PJ4B_CLOBBER
#define __PJ4B_CLOBBER_ONLY
#endif

#endif /* __ASM_ARM_PJ4B_6011_H */
