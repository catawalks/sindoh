// SPDX-License-Identifier: GPL-2.0
/*
 * DP200 hang analysis (docs/kernel/nandboot_hang_analysis.md, hang 24):
 * zero padding linked where lib/reed_solomon/ would be
 * (CONFIG_MV61X0_LAYOUT_PAD), so that a kernel without pstore gets the
 * layout of one with it. Nothing reads or runs it. The initcall only
 * references the pads, so that --gc-sections keeps them.
 */
#include <linux/init.h>
#include <linux/stringify.h>

#define MV61X0_PAD(name, sec, n)					\
	asm(".pushsection " sec "\n" #name ":\n\t.space " __stringify(n)	\
	    "\n\t.popsection");						\
	extern char name[]

MV61X0_PAD(mv61x0_pad_lib_text, ".text, \"ax\", %progbits", CONFIG_MV61X0_PAD_LIB_TEXT);
MV61X0_PAD(mv61x0_pad_lib_rodata, ".rodata.mv61x0_pad, \"a\", %progbits", CONFIG_MV61X0_PAD_LIB_RODATA);
MV61X0_PAD(mv61x0_pad_lib_data, ".data, \"aw\", %progbits", CONFIG_MV61X0_PAD_LIB_DATA);
MV61X0_PAD(mv61x0_pad_lib_bss, ".bss, \"aw\", %nobits", CONFIG_MV61X0_PAD_LIB_BSS);

static int __init mv61x0_pad_lib_keep(void)
{
	asm volatile("" : : "r" (mv61x0_pad_lib_text), "r" (mv61x0_pad_lib_rodata),
		     "r" (mv61x0_pad_lib_data), "r" (mv61x0_pad_lib_bss));
	return 0;
}
core_initcall(mv61x0_pad_lib_keep);
