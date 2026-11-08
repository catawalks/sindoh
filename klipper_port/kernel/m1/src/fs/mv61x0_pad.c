// SPDX-License-Identifier: GPL-2.0
/*
 * DP200 hang analysis (docs/kernel/nandboot_hang_analysis.md, hang 24):
 * zero padding linked where fs/pstore/ would be (CONFIG_MV61X0_LAYOUT_PAD),
 * so that a kernel without pstore gets the layout of one with it. Nothing
 * reads or runs it. The initcall only references the pads, so that
 * --gc-sections (LD_DEAD_CODE_DATA_ELIMINATION) keeps them.
 */
#include <linux/init.h>
#include <linux/stringify.h>

#define MV61X0_PAD(name, sec, n)					\
	asm(".pushsection " sec "\n" #name ":\n\t.space " __stringify(n)	\
	    "\n\t.popsection");						\
	extern char name[]

MV61X0_PAD(mv61x0_pad_fs_text, ".text, \"ax\", %progbits", CONFIG_MV61X0_PAD_FS_TEXT);
MV61X0_PAD(mv61x0_pad_fs_text_unlikely, ".text.unlikely, \"ax\", %progbits", CONFIG_MV61X0_PAD_FS_TEXT_UNLIKELY);
MV61X0_PAD(mv61x0_pad_fs_rodata, ".rodata.mv61x0_pad, \"a\", %progbits", CONFIG_MV61X0_PAD_FS_RODATA);
/* one string of that many bytes, so that the linker's string merging keeps it */
asm(".pushsection .rodata.str1.1, \"aMS\", %progbits, 1\n"
    "mv61x0_pad_fs_str:\n\t.fill " __stringify(CONFIG_MV61X0_PAD_FS_RODATA_STR)
    " - 1, 1, 0x50\n\t.byte 0\n\t.popsection");
extern char mv61x0_pad_fs_str[];
/*
 * Incompressible padding (an xorshift32 sequence), to make the compressed
 * image bigger without changing what the kernel does.
 */
asm(".pushsection .rodata.mv61x0_rand, \"a\", %progbits\n"
    "mv61x0_pad_fs_rand:\n\t.set x, 0x2545f491\n"
    "\t.rept " __stringify(CONFIG_MV61X0_PAD_FS_RANDOM) " / 4\n"
    "\t.set x, x ^ ((x << 13) & 0xffffffff)\n"
    "\t.set x, x ^ (x >> 17)\n"
    "\t.set x, x ^ ((x << 5) & 0xffffffff)\n"
    "\t.long x\n\t.endr\n\t.popsection");
extern char mv61x0_pad_fs_rand[];
MV61X0_PAD(mv61x0_pad_fs_data, ".data, \"aw\", %progbits", CONFIG_MV61X0_PAD_FS_DATA);
MV61X0_PAD(mv61x0_pad_fs_bss, ".bss, \"aw\", %nobits", CONFIG_MV61X0_PAD_FS_BSS);
MV61X0_PAD(mv61x0_pad_fs_init_text, ".init.text, \"ax\", %progbits", CONFIG_MV61X0_PAD_FS_INIT_TEXT);

static int __init mv61x0_pad_fs_keep(void)
{
	asm volatile("" : : "r" (mv61x0_pad_fs_text), "r" (mv61x0_pad_fs_rodata),
		     "r" (mv61x0_pad_fs_data), "r" (mv61x0_pad_fs_bss),
		     "r" (mv61x0_pad_fs_init_text), "r" (mv61x0_pad_fs_str),
		     "r" (mv61x0_pad_fs_text_unlikely), "r" (mv61x0_pad_fs_rand));
	return 0;
}
core_initcall(mv61x0_pad_fs_keep);
