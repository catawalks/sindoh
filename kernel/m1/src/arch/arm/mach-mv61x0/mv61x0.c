// SPDX-License-Identifier: GPL-2.0
/*
 * Marvell 88PA61x0 printer SoCs (88PA6170 in the Sindoh DP200).
 *
 * The device tree describes everything milestone 1 needs. Still to come:
 * secondary CPU start (vendor: physical address of secondary_startup to
 * 0xfa000000, then an SGI) and the PL310 L2 cache.
 */
#include <asm/mach/arch.h>

static const char *const mv61x0_dt_compat[] __initconst = {
	"marvell,88pa6170",
	NULL,
};

DT_MACHINE_START(MV61X0_DT, "Marvell 88PA61x0")
	.dt_compat	= mv61x0_dt_compat,
MACHINE_END
