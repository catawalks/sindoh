# MarvellEmbeddedProcessors on GitHub: is there anything for the 88PA6170? (2026-11-01)

Checked https://github.com/orgs/MarvellEmbeddedProcessors/repositories:
- the repo list (65 repos);
- the branch lists of linux-marvell, u-boot-marvell, mainline-public and
  openwrt-kernel;
- a code search for `pa6170`, `88PA6170`, `gemstone`, `mv61x0` and
  `granite2`. The search hit GitHub's rate limit after six of the eight
  searches.

**Result: nothing for this SoC.**
- **What the org covers:**
  - OCTEON data-plane work (DPDK, VPP, SONiC);
  - Armada 3700/7K/8K/38x kernels, U-Boot, ATF, EDK2 and OpenWrt;
  - ML tools.
- **Printer SoCs:**
  - no source anywhere for the 88PA6170 / Gemstone ("mv61x0" in the stock
    kernel) or its NAND BCH mode;
  - the printer kernels were never published there (the stock kernel's
    GPL source would come from Sindoh or Marvell's LSP releases).
- **The NAND controller:** mainline's marvell_nand already covers the
  controller generation in the Armada kernels. Our bch_v1 code (patch 0010)
  is the part none of them have.

**The only printer reference:** A3700-utils-marvell/wtptp, Marvell's
TIM builder and the WTP downloader for BootROM UART/USB download. Its
platform list includes `88PA62_70` (GRANITE2), `88PA62_20` and `88PA62_10`,
later printer SoCs. The 88PA6170 isn't listed.
- **For the DP200:** if the 6170's BootROM speaks the same download
  protocol, that would be a way to unbrick a printer whose U-Boot is gone.
  Not verified, and not needed by the current plan, which never writes
  U-Boot.
- **For the 2X, 1X and 7X:** these models use the 88PA6270 "granite2"
  (other_models.md), which the tool lists by name (`P88PA62_70`). If we
  expand to those models, this is the most useful thing in the org: the
  BootROM download protocol and the TIM boot-header format. That means
  unbricking, and running our own boot images without writing their
  eMMC/NAND first.
  - Worth keeping, with the exact repo commit (a3e1c67) noted here.
  - No clone is needed until then.
- **Not a TIM:** mtd0 starts with `c1de ed1c`, which isn't a TIM header
  (`TIMH`). So the boot block format is likely different.

**Should we clone it or add our work there?** No.
- **We can't contribute there:** it's Marvell's own org. Its repos are
  product trees for other chips.
- **Where our work goes instead:** the kernel work (the bch_v1 read/write
  path, the BBT descriptors, the DTS) belongs upstream, on the linux-mtd
  list, if we ever send it.
- **What a clone would add:** nothing the kernel build uses.
