# The nandboot hard hangs (11-06, 11-07): analysis and test plan

Offline analysis, 2026-11-07. Nothing here touched the printer. Inputs: the
two hangs as the main session reported them, the vendor 3.2 kernel image
(`Image` md5 a416b1bc..., `tools/kernel_re/`), our 6.18.59 tree and the
m1-nandboot build of 59134b5 (fcba26da).

## The two hangs

| | Hang 1 (11-06 ~22:10, 33d2e5d2) | Hang 2 (11-07 00:34, fcba26da) |
|---|---|---|
| Load | Wi-Fi: re-enumerate, deauth/reassoc churn | whole-root `tar` from the SD card (~30 s in), nc streams on eth0, mlan0 up |
| Ping on eth0 | **yes** | no |
| Serial echo, SysRq | no | no (BREAK + l/w ignored) |
| Lockup detectors | not built in yet | soft lockup built in with panic: **did not fire** |

A soft lockup is caught by each CPU's own hrtimer interrupt. If it doesn't
fire, and the UART interrupt (routed to CPU0) isn't served either, then
either **both CPUs have IRQs masked and are spinning**, or **a CPU is stuck
in a bus or memory access** that never completes. Hang 2 is one of those.
Hang 1 is milder: CPU0 still served the GMAC interrupt and softirqs, but
the tty layer and userspace were dead. One CPU stuck with IRQs off, and
the other blocked behind it once it needs that CPU (an IPI, a lock, a
kworker), fits that.

## The main finding: the vendor's PJ4B errata workarounds are not in our kernel

The vendor config enables `ARM_ERRATA_PJ4B_6075`, `_6011`, `_6315`,
`_5727`, `_5756`, `_FORCE_CLEAN_INVALIDATE` and the SoC options
`MACH_MV61X0_88PA6170_ERRATA_BZ_833` / `_BZ_664`
(vendor_3.2.0-g67a8e16.config, lines 316-383). Marvell never sent these
upstream. In the vendor image there are two forms of them:

1. **Erratum 6011: every exclusive load is issued five times.** Each
   `ldrex` in the vendor kernel is a run of five identical `ldrex`, then
   the `strex`. That covers spinlocks, atomics, cmpxchg, bitops and the
   kuser helpers (`__kuser_pj4b_errata6011_cmpxchg32/64`,
   `pj4b_errata_6011_64` = an extra `dsb`). A scan of the image
   (`tools/ldrex_scan.py`, see below) finds **2097 runs of 5 and 9 single `ldrex`**
   (8 in init data, 1 in the stock `__kuser_cmpxchg64` that the 6011
   version replaces). **Our nandboot vmlinux: 1490 single `ldrex`, none
   doubled.**
2. **D-cache maintenance by MVA: IRQs off, `dsb`, a 50-loop delay, then
   the operation.** `v7_dma_inv_range`, `v7_dma_clean_range`,
   `v7_dma_flush_range`, `v7_flush_kern_dcache_area`,
   `v7_coherent_user_range`, `v7_flush_dcache_all`,
   `v7_clean_dcache_to_PoUIS` and `cpu_v7_dcache_clean_area` all start
   with `mrs ip, apsr; cpsid i; dsb sy; mov r3, #0x32; 1: subs r3, #1;
   bne 1b`, and end with `dsb sy; msr cpsr_c, ip`. `v7_dma_clean_range`
   also turns each clean (`c7, c10, 1`) into clean+invalidate
   (`c7, c14, 1`) when `arm_errata_pj4b_force_clean_invalidate` is set.
   That flag is in .bss, so it is 0 unless something sets it at run time;
   whatever sets it isn't identified yet. **Ours (cache-v7.S, unmodified):
   none of this.** The scan finds 8 wrappers in the vendor image and 0 in
   ours.

Which erratum number each form belongs to is unknown beyond the symbol
names (6011 = the exclusives). The other options are most likely the c15
auxiliary-register bits of `__v7_pj4bmp_setup`, which patch 0001 already
copies bit for bit (Debug 0 bit 12, Debug 2 bit 29 / ~bit 23, Debug 1
~bit 25, Functional 0 ~bit 7, ACTLR SMP+FW).

Why this fits:
- Hang 2 came under heavy SD reads. Each completed request is unmapped
  with `v7_dma_inv_range` over its pages, so by-MVA invalidates run
  constantly while the SD, USB and GMAC interrupts arrive on top. That is
  exactly the window the vendor closes with `cpsid i` and the
  `dsb`+delay.
- Hang 1 came under Wi-Fi churn: USB DMA (mwifiex_usb rx/tx URBs), the
  same cache maintenance, and lock-heavy cfg80211/mwifiex paths.
- A lost or corrupted exclusive (6011) breaks a spinlock or an atomic.
  Two CPUs then spin forever in `raw_spin_lock_irqsave`: IRQs masked on
  both, no soft-lockup report, no UART. That is hang 2's signature.
- m1-debian has the same gap and has not hung, but it never ran a
  sustained DMA load on mainline (the payloads were built under stock).
  Its record doesn't clear it.

## Other candidates (less likely, and what would point at each)

| Candidate | For | Against / test |
|---|---|---|
| SDHCI DMA (SDMA/ADMA2 from the capabilities; the vendor driver's mode is unknown) wedging the AXI bus | heavy SD read in hang 2 | hang 1 had no SD load. Test: PIO only, `sdhci.debug_quirks=0x2000c060` (it *replaces* the driver's quirks, so ours 0x2000c000 + `BROKEN_DMA` 0x20 + `BROKEN_ADMA` 0x40), under the same tar |
| A bus stall on an MMIO access (an ungated or absent block, the second SD slot at 0xf9080200, EHCI) | everything dies at once | nothing enabled here touches unknown blocks; the second slot isn't in the DT |
| GIC / SIC (patch 0002) losing an interrupt | UART and eth both dead | a lost interrupt hangs one device, not the CPUs' own timers |
| What the nandboot config adds (modules, usb-storage/SCSI, netpoll, the watchdogs) | hang 2 only seen on nandboot | none of these touch the CPU or the bus; test (c) below |
| PREEMPT_NONE (ours) vs PREEMPT (vendor) | | a scheduling difference, not a SoC hang |

## Morning test plan (each test with the owner nearby to power-cycle)

The m1-nandboot command line is forced (`CMDLINE_FORCE`), so a different
command line needs a rebuilt image. Each test runs the hang-2 load: loop
the whole-root `tar ... | wc -c` for 20 min, or until it hangs (hang 2
came ~30 s in). Run Klipper idle as before. Ranked by information per
test:

1. **(d) `maxcpus=1`**, otherwise as hang 2. The PJ4B errata above are
   about coherency between the two cores (the exclusive monitor, snoops
   during maintenance). If UP survives 20 min where SMP hung in 30 s, the
   cause is SMP or errata. If UP hangs too, the cause is a device, bus or
   DMA problem, so go to test 3.
2. **Errata image** (new, offline work): nandboot plus the vendor's
   cache-op wrapper in `arch/arm/mm/cache-v7.S` (8 routines, small), then
   the 6011 `ldrex` runs (atomic.h, spinlock.h, cmpxchg.h, futex.h,
   bitops, entry-armv.S kuser helpers: mechanical, through one macro).
   SMP and hang-2 load. A pass is both the diagnosis and the fix. If
   test 1 passed, this decides between "errata" and "some other SMP bug".
3. **(b)+(c) together: SD only.** SMP, Wi-Fi down (`ip link set mlan0
   down`, modules unloaded), no nc streams, eth0 idle; serial only. If it
   still hangs, Wi-Fi, USB and eth are cleared at once. If not, add one
   back per run: the nc streams first (GMAC DMA), then Wi-Fi.
4. **(a) m1-debian + the same tar.** This checks nandboot's config
   additions. It says little about the SoC: m1-debian has the same errata
   gap. Do it only if test 3 passes, i.e. the load needs more than SD
   reads.

### The test images (built 2026-11-07, not booted)

`VARIANT=nandboot HANGTEST=<t> ./build.sh` builds 59134b5's nandboot plus
`variants/nandboot-<t>.config`, under its own name. m1-nandboot.uimg
(fcba26da) is not rebuilt. All three add the buddy hard-lockup detector
with panic (`HARDLOCKUP_DETECTOR`, `BOOTPARAM_HARDLOCKUP_PANIC`). **Each
image needs its own modules tar** in the root's /lib/modules: the
`-errata` mwifiex has the erratum code too, and the vermagic doesn't tell
the builds apart.

| Image | md5 | Bytes | What changes |
|---|---|---|---|
| m1-nandboot-up.uimg | 0eff24319c75a52cd5895c87b5d70732 | 2,809,188 | `maxcpus=1` on the forced command line (test 1) |
| m1-nandboot-wrap.uimg | d997f1297e502e88adc5ebe8043d7b4f | 2,808,212 | SMP + `PJ4B_MV61X0_CACHE_WRAP` (patch 0011) |
| m1-nandboot-errata.uimg | 5b17e2ec0c90ae69c8bed2863c2675f0 | 2,814,412 | SMP + 0011 + `PJ4B_ERRATA_6011` (patch 0012) (test 2) |

| Modules tar | md5 |
|---|---|
| m1-nandboot-up-modules.tar | a4b47ed340e59fcf4ca80c0bdf83d14f |
| m1-nandboot-wrap-modules.tar | d8533156ea921151c6a6720c8bec08fb |
| m1-nandboot-errata-modules.tar | fff05ae2c292611aad9bfb63415a1eb6 |

- **Patch 0011** (`arch/arm/mm/cache-v7.S`; Kconfig options for both
  patches in `arch/arm/mm/Kconfig`, off by default). It adds IRQs off,
  `dsb` and the 50-loop delay, then the CPSR is restored at every exit, in:
  - the set/way routines: `v7_flush_dcache_louis` and
    `v7_flush_dcache_all`, with the CPSR in ip and every exit through
    `finished`;
  - `v7_coherent_user_range`: the vendor's single loop of D clean, `dsb`
    and I invalidate per line; the fault fixup restores IRQs too;
  - `v7_flush_kern_dcache_area` and the three `v7_dma_*_range` routines.

  `cpu_v7_dcache_clean_area` isn't changed: on SMP mainline it returns
  at once (the table walk reads L1). The vendor's 3.2 still cleaned PTE
  lines there, and in `set_pte_ext`. That is a 3.2 behaviour, not an
  erratum, and isn't copied.
- **Patch 0012** plus the new header `src/arch/arm/include/asm/pj4b-6011.h`:
  - Every `ldrex` gets four extra copies in front of it, at 35 sites:
    atomic.h, cmpxchg.h, spinlock.h, futex.h, swp_emulate.c, lib/bitops.h
    and the kuser helpers. edac.h is skipped; EDAC isn't built.
  - The asm statements in atomic.h, cmpxchg.h and spinlock.h run inside
    `arch_local_irq_save`/`restore`. In bitops the IRQs are off over the
    five loads only, restored before the `strex`, as the vendor's
    `_set_bit`. Futex and SWP emulation get no IRQ masking, as the
    vendor's.
  - The kuser cmpxchg helpers branch to five-load copies placed in front
    of 0xffff0f60. The slot addresses and `__kuser_helper_version` (5)
    stay as before.
  - **User-space `ldrex` is not covered.** The armhf initramfs tools,
    musl and armhf libraries have their own. The armel root's atomics
    mostly go through the kuser cmpxchg, which is covered.
- **Checked in the binaries** (objdump, `tools/ldrex_scan.py`):
  - fcba26da 1490 single `ldrex`; -up 1492; -wrap 1492 single; -errata
    **1273 runs of 5, none single**.
  - The wrapper is in all 7 routines of -wrap and -errata, none of -up.
  - In -errata's modules: mwifiex.ko 18 runs of 5, mwifiex_usb.ko 2,
    each with `cpsid i`.
  - The kuser helpers are 288 bytes; `__kuser_cmpxchg64` is 160 bytes
    before the end, i.e. at 0xffff0f60.

Optional, with no DMA at all: two `dd if=/dev/zero of=/dev/null bs=64k`
plus a fork loop (`while :; do /bin/true; done`) on SMP. This exercises
the exclusives, TLB IPIs and `v7_coherent_user_range` on exec. A hang
here points at the CPU errata without any device involved.

## Evidence that survives the power cycle (cheap, for a debug image)

A **power cycle wipes DRAM**: unrefreshed DDR decays, and U-Boot's DDR
init runs on every boot. So pstore alone won't help unless the hang turns
into a **warm reset**. In order of cost:

1. **Kernel netconsole instead of the busybox nc streams.** It's already
   built in (configfs). netpoll sends from the CPU that prints, with IRQs
   off, so an oops, panic or lockup report still reaches the PC. The nc
   stream dies with userspace. Set it up once per boot:

   ```
   mkdir /sys/kernel/config/netconsole/pc
   echo <PC IP> > .../remote_ip; echo <PC MAC> > .../remote_mac
   echo 1 > .../enabled
   dmesg -n 8
   ```

   Then on the PC: `nc -lu 6666`.
2. **The buddy hard-lockup detector:** `CONFIG_HARDLOCKUP_DETECTOR=y`
   (the buddy flavour is available, `HAVE_HARDLOCKUP_DETECTOR_BUDDY=y`)
   and `CONFIG_BOOTPARAM_HARDLOCKUP_PANIC=y`. Each CPU checks that the
   other's hrtimer still ticks. One CPU stuck with IRQs off (hang 1's
   shape) gets a backtrace and a panic, then `panic=10` reboots. It can't
   help when both CPUs are stuck.
3. **A hang watchdog on timer 0**, the vendor's watchdog, which our
   restart handler already fires (`mv61x0_restart`,
   timer-mv61x0.c:195). Load it with ~30 s (the 1 MHz tick) and pet it
   from the watchdog core (`WDOG_HW_RUNNING`, petted by a kworker) or a
   pinned hrtimer. A full hang then gives a warm reset, the same path as
   every `reboot`, instead of needing the owner. **Debug images only:** a
   reset during a NAND write is the one thing the end-goal image must not
   do, and arming a hardware watchdog needs the owner's OK.
4. **ramoops in reserved RAM, useful only together with 3:**
   `CONFIG_PSTORE=y`, `PSTORE_RAM`, `PSTORE_CONSOLE` (the whole printk
   stream, so the last lines before a silent hang are kept even without
   a panic), plus a DT node, e.g.
   `ramoops@1e000000 { compatible = "ramoops"; reg = <0x1e000000
   0x100000>; console-size = <0x80000>; record-size = <0x20000>; }`.
   Keep it clear of U-Boot's RAM: the load at 0x400000-0xbc0000,
   env_temp 0x1f000000, malloc 0x1fbbc000+, TLB 0x1fff0000, and the logo
   at 0x18000000. 0x1e000000 avoids all of them. Check it once before
   relying on it: `echo c > /proc/sysrq-trigger` → panic → warm reboot →
   `/sys/fs/pstore/dmesg-ramoops-0` present. If U-Boot's DDR init
   scrambles RAM, it won't be there.

## Reproducing the scan

`kernel/m1/tools/ldrex_scan.py` (it reads only the images) counts runs of
`ldrex` (`(w & 0x0f900fff) == 0x01900f9f`) and the wrapper prologue
`f10c0080 f57ff04f e3a03032`:

| Image | ldrex runs | wrappers |
|---|---|---|
| vendor `Image` (a416b1bc) | 2097 × 5, 9 × 1 | 8 |
| m1-nandboot-vmlinux (59134b5) | 1490 × 1 | 0 |

Disassembly: `tools/kernel_re/kdis.py Image vendor_System.map
v7_dma_inv_range do_raw_spin_lock __kuser_pj4b_errata6011_cmpxchg32
__v7_pj4bmp_setup`.

## Night tests on the printer (2026-11-07, main session)

The same load each time: three passes of `tar -C / --one-file-system -cf -
. | wc -c` (3.27 GB from the card, about 4.3 min each), with the busybox nc
streams on eth0, mlan0 up and Klipper idle.

| Run | Image | Result |
|---|---|---|
| A | m1-debian 5df089a9 (Nov 1 tree) | 3 passes, no hang (886 s) |
| B | m1-debian-nandw f370f49e (Nov 1 tree, NANDW DT) | 3 passes, no hang (870 s) |
| E | m1-nandboot-errata 5b17e2ec (e1ee7e8) | 3 passes, no hang (874 s) |
| N | m1-nandboot fcba26da (plain, again) | **hang 3** in pass 3: 668 s uptime, ~570 s into the load; no ping, no serial, no SysRq |
| E2 (day, 11-07) | m1-nandboot-errata 5b17e2ec, its own modules | 20 passes, no hang (4943 s of load, 5054 s uptime); no oops, warning or SD error in dmesg |

**Plain nandboot** hung in both runs under this load: ~30 s in (hang 2)
and ~570 s in (hang 3). The errata image (0 of 1) and the Nov 1 images
(0 of 2) didn't, but each had only ~13 min of load, which isn't enough to
rule out a rarer hang. The next runs need to be longer, and should reset
by themselves (a timer-0 watchdog in a debug image, owner's OK) so that
one hang doesn't end a night.

E2, the long run (2026-11-07 day): the errata image went through 20 passes
(65 GB read, ~82 min of load), more than 8 times the load at which plain
nandboot hung the second time. Together with E, the errata image has ~97
min of this load without a hang; plain nandboot has hung in 2 of 2 runs
inside ~10 min. That points strongly at the missing PJ4B errata
workarounds, which the vendor kernel also carries. Stage 4 should use the
errata image (or plain nandboot with e1ee7e8's patches as the default),
after the owner's OK.

## What differs between the Nov 1 images and plain nandboot (offline, 2026-11-07)

Builds: m1-debian #22 and m1-debian-nandw #24 (Nov 1, 18:42/18:43) and
m1-nandboot #7 (fcba26da, Nov 7 00:05). The toolchain is the same
(Debian gcc 14.2.0-19, binutils 2.44).

- **Kernel source: only patch 0010 changed.** `git diff a6e0188 59134b5`
  over `kernel/m1/src`, `patches`, `m1.config` and `variants/full.*`
  shows nothing else: no change in arch, mm or other drivers. Patch 0010
  changed in two ways:
  - **Write guard v2** (11-06): the window became up to 4 ranges under a
    spinlock, plus the area table. It runs only on program/erase, and
    there is no NAND write during the tar.
  - **The BCH read path** (4838d55, 11-01 19:21, *after* the Nov 1
    builds): a corrected read now takes the bit count from ERRCNT instead
    of re-reading the page raw, and an early UNCERR re-reads. This runs
    on NAND reads: in nandboot only during the boot-time UBI attach of
    mtd6 (then detached), not during the card tar.
  - So **test B (f370f49e) had guard v1 and the old read path.** It
    didn't test patch 0010 as it is now.
- **Config** (`m1-full-nandw-full.config` Nov 1 against
  `m1-nandboot-full.config`, DVB and tuner lines left out):
  - added: `MODULES`, `MODULE_UNLOAD`, `STRICT_MODULE_RWX`,
    `ARM_MODULE_PLTS`, `EXECMEM`, mwifiex `=m`;
  - added: `SCSI`, `BLK_DEV_SD`, `USB_STORAGE`, BSG, `SG_POOL`;
  - added: `NETPOLL`, `NET_POLL_CONTROLLER`, `NETCONSOLE` (+ dynamic),
    `CONFIGFS_FS`;
  - added: `LOCKUP_DETECTOR`, `SOFTLOCKUP_DETECTOR` (+ panic),
    `DETECT_HUNG_TASK` (120 s), `WQ_WATCHDOG`;
  - added: `MEDIA_SUBDRV_AUTOSELECT`, which drops the ~140 DVB drivers
    that were built in; `I2C_MUX`, `MEDIA_ATTACH`;
  - gone: `REGMAP_I2C`;
  - command line: `CMDLINE_FORCE` with our own line, so no `console=tty0`,
    no `ubi.mtd=filesystem` and no stock extras. The memory size still
    comes from the ATAG.
- **Elsewhere:** the nandboot initramfs (attach mtd6, detach it for a
  card root, close the window, switch_root), mwifiex loaded as a module
  after the root is up, and the NANDW DT (nandboot.dts).
- **The errata image (E, passed) has every one of these** differences
  from the Nov 1 images. It differs from N only by patches 0011/0012 and
  the hard-lockup detector. So if E keeps passing on longer runs, the
  errata fix is the cause, not a tree change. If the Nov 1 images also
  keep passing, one of the config additions (most likely candidates: the
  per-CPU lockup-watchdog hrtimers and stopper kicks, or modules and
  STRICT_MODULE_RWX) makes the erratum window easier to hit, rather than
  being a bug of its own.

## The debug image: m1-nandboot-errata-dbg (built, not booted)

**Debug image only. It arms a hardware watchdog, so every run needs the
owner's OK first.** `VARIANT=nandboot HANGTEST=errata-dbg ./build.sh`
gives the -errata image plus the two items below. `m1-nandboot-errata-dbg.uimg` md5
`d4350cf0e66005610bd4736320c8017f`, 2,821,420 bytes; its modules tar
`m1-nandboot-errata-dbg-modules.tar` md5 `4f9b91070ae164abed5ab28668074f57`.
Checked in the build: 1273 LDREX runs of 5, the PSTORE options set, the
ramoops node in the DTB, the hang watchdog code present.


- **A hang watchdog on timer 0** (timer-mv61x0.c, opt-in by
  `timer_mv61x0.hang_wdt=30` on the forced command line; the default 0
  changes nothing in other images):
  - at late_initcall it arms timer 0 with U-Boot's `reset_cpu` sequence
    and a 30 s count;
  - a kworker kicks it every 5 s, the vendor's way
    (`service_watchdog_timer`: toggle the low nibble, enable set);
  - a hard hang (both CPUs, or the workqueues) resets the board after
    ≤ 30 s, a warm reset like every `reboot`;
  - the boot log shows `mv61x0-timer: hang watchdog armed: reset after
    30 s ...`.
  - Not verified on the hardware: that a kick restarts the count. The
    kexec loader's 60 s arm and the stop at boot work (kexec_test2.md),
    but no long count has ever been allowed to run out.
  - `echo 1 > /sys/module/timer_mv61x0/parameters/hang_wdt_nokick` stops
    the kicks, so the reset can be tested.
  - After `poweroff` the board resets again 30 s later. Use the power
    switch.
- **pstore/ramoops**, 1 MB at 0x1e000000 (`nandboot-errata-dbg.dts`,
  with ECC): the console log (512 KB), 3 panic/oops records and pmsg. The
  area is clear of everything the stock U-Boot uses (see the DTS
  comment). It survives only if U-Boot's DDR init after a warm reset
  doesn't scramble RAM. A power cycle always loses it.

Check order, with the owner present, before relying on it for a night:

1. Boot it. `dmesg | grep -e "hang watchdog" -e ramoops` shows the
   watchdog armed and ramoops at 0x1e000000. Still up at 60 s uptime
   means the kicks restart the count.
2. `echo 1 > .../hang_wdt_nokick`: the board must reset by itself
   within ~30 s, through U-Boot and back into this image.
3. After that reset: `ls /sys/fs/pstore/`. `console-ramoops-0` holding
   the previous boot's log means RAM survived a watchdog reset.
4. `echo c > /proc/sysrq-trigger` (a panic): `panic=10`, then a warm
   reset, then `dmesg-ramoops-0` should hold the panic.
5. Only then the long run: the hang load in a loop. After each
   self-reset, save `/sys/fs/pstore/*` before anything else.

## Hang 4: the errata kernel on its first NAND-root run (2026-11-07, offline notes)

**What happened** (main session's report; no log exists):
- 5b17e2ec from mtd0, root `ubi0:filesystem` (mtd6), the first NAND-only
  boot, warm, ~11:28.
- The printer was idle: Klipper ready, the screen app, Moonraker, nginx.
  eth0 up; Wi-Fi down (it had failed at boot, wifi_boot_failure.md).
- The last answered serial command was ~11:32. The hang was found at
  ~11:58, at 25–30 min uptime: no ping, no serial echo, no panic, no
  `panic=10` reset. The soft- and hard-lockup detectors were both built
  in and stayed silent.
- At first this looked like a Wi-Fi T5 step (rmmod/insmod) hanging it.
  It wasn't: the Debian root has no kmod, so `rmmod` and `insmod` were
  "not found" (rc 127), and the command was never even echoed. The board
  was most likely already hung.
- The next boot (cold, NAND root) said "UBIFS (ubi0:0): recovery needed",
  as expected after a hard stop with the root rw.

**What's new compared with the runs that passed.** The errata image passed
~97 min of heavy SD load (E, E2) on the **card** root. On that root,
mtd6 is detached and the write window closed: patch 0010's NAND paths
only ran the boot-time UBI scan. The NAND-root run differs in this:

| | Card root (E, E2: no hang) | NAND root (hang 4) |
|---|---|---|
| File reads | ext4 on SD, DMA (SDHCI) | UBIFS on mtd6: **PIO** reads through patch 0010's BCH path, busy-polling NDSR with `cpu_relax()` |
| Writes | ext4 on SD | UBIFS journal, commits and GC: **program/erase** through the guarded write path (`AUTO_RS`, `wait_prog`), from the background threads and writeback even when idle (Klipper/Moonraker logs, the Moonraker database) |
| Executables | page cache filled by DMA | page cache filled by **CPU copies out of the NAND FIFO**, then executed: every page goes through `flush_dcache_page` / the I-cache sync on first map |
| Hours of this on mainline | many | none before: stage 5's 254 MB unpack ran with the root on the card (one large write burst, no hang); the 16 MB UBI write test (11-01) was on the Nov 1 tree |

**Candidates, re-ranked for hang 4:**

1. **Patch 0010 / the NAND controller under sustained mixed use.**
   - A bus access that never completes stops a CPU without any lockup
     report. If that's the NAND controller (or the peripheral bus
     behind it), any later access from the other CPU, including the
     UART for a panic message, stops too. That's exactly "nothing at
     all".
   - The PIO read takes all 2080 bytes (data + spare) out of NDDB after
     a single RDDREQ. The program path pushes data into NDDB the same
     way.
   - The FIFO has known quirks: the stale 4 bytes after an idle gap
     (`bch_v1_stop`). Also, a read of NDDB at the wrong moment pops a
     word and shifts every later read; we found that ourselves.
   - Whether an NDDB access on an empty or full FIFO can also *stall*
     instead of returning junk isn't known. Nothing so far has exercised
     reads and program/erase interleaved for half an hour.
2. **What the errata work doesn't cover yet.**
   - **Page-table cleaning.** The vendor 3.2 kernel cleans every PTE write
     to memory (`set_pte_ext`, `cpu_v7_dcache_clean_area`). Mainline's
     `cpu_v7_dcache_clean_area` is a no-op on SMP (`ALT_SMP(W(nop))`, "MP
     extensions imply L1 PTW"): it trusts the table walker to read
     through the L1 cache.
     - If the PJ4B-MP walker on this SoC doesn't, a stale PTE can
       translate to a wrong physical address. An access to an address
       nothing decodes can stall the bus: a hang with no report.
     - Not a NAND-specific path. The NAND root changes the
       page-fault and exec pattern, though.
   - `v7_clean_dcache_to_PoUIS` (the 8th vendor wrapper) has no mainline
     counterpart. Patch 0011 wraps the 7 routines mainline has.
   - Nothing in ours sets the equivalent of
     `arm_errata_pj4b_force_clean_invalidate`.
   - The SoC options `MACH_MV61X0_88PA6170_ERRATA_BZ_833` / `_BZ_664`
     are still unidentified.
   - The NAND root is the first workload that executes code the CPU
     itself copied into the page cache. That needs D-cache clean plus
     I-cache invalidate across both cores.
3. **Plain chance.** One hang in ~30 min, against 0 in ~97 min of card-root
   load, isn't a rate. But the plain kernel's hangs came at 30 s and
   570 s under load, and this one came with the board idle. That looks
   like a different trigger, not a rarer version of the same one.

The Wi-Fi failures don't explain it either: Wi-Fi was down for the whole
run.

### What I'd want for the next NAND-root run

In order of value. Items 1–3 need a build, offline; item 4 is a script.

1. **ramoops in the mtd0 image itself, and a runtime-armable hang
   watchdog.**
   - The errata-dbg image can't be used as is on a NAND-only printer: it
     would have to be kexec'd. After its watchdog reset, U-Boot boots the
     mtd0 kernel, which has no pstore and doesn't reserve 0x1e000000, so
     the log is lost or overwritten.
   - Proposal: add the `ramoops@1e000000` reserved-memory node and
     `PSTORE`/`PSTORE_RAM`/`PSTORE_CONSOLE`/`PSTORE_PMSG` to the
     **nandboot default**. That costs 1 MB of RAM, and any later boot
     from mtd0 shows the previous boot's console log in
     `/sys/fs/pstore/`.
   - Make `timer_mv61x0.hang_wdt` writable at run time (0644: writing N
     arms it, 0 stops it). Then a test session arms the watchdog from
     init.mainline or by hand, and normal boots never do. Arming still
     needs the owner's OK per run.
   - Updating mtd0 is a stage-4-style NAND write and needs the owner's
     OK.
2. **A NAND breadcrumb ring in that RAM.** A debug-only option in patch
   0010 (off by default): before each controller step, write the
   operation, page or block, phase (command sent / RDDREQ seen /
   word *n* of the PIO transfer / CMDD / done), CPU and jiffies into a
   small ring at a fixed RAM address (for example the pmsg zone, or 4 KB
   right after ramoops).
   - After a watchdog reset, the ring says whether a CPU died inside a
     NAND operation, and in which phase. That's the one question no
     log can answer for a bus stall.
   - The cost is a few stores per page.
3. **The errata gaps above, as a separate test image:** PTE cleaning back
   on SMP (`cpu_v7_dcache_clean_area` doing its clean loop), so the walker
   never sees a stale entry. The `BZ_833`/`_BZ_664` options need another
   pass over the vendor image to identify first.
4. **A heartbeat over netconsole** (already running) every 10 s, from a
   shell loop started by init.mainline:

   ```sh
   while :; do
     echo "hb $(cut -d' ' -f1 /proc/uptime) load $(cut -d' ' -f1-3 /proc/loadavg)" \
          "nand $(cat /sys/module/marvell_nand/parameters/stats)" \
          "irq $(awk '/nand|ehci|sdhci|eth/{printf "%s:%s/%s ", $NF, $2, $3}' /proc/interrupts)" \
          > /dev/kmsg
     sleep 10
   done &
   ```

   Also `dmesg -n 8`, so the kernel's own NAND, UBI and UBIFS warnings
   reach netconsole as they happen. The last heartbeat dates the hang to
   10 s, and the counters show whether NAND traffic was running.
5. **Isolation runs, all on the errata kernel** (each needs the owner's
   OK, watchdog-backed if item 1 exists):

   | Run | Root | Load | Hang points at |
   |---|---|---|---|
   | I1 | card | mtd6 attached, UBIFS mounted **rw**, a loop writing and reading back ~50 MB files in it, plus `sync` | patch 0010's program/erase and read paths, without the root on NAND |
   | I2 | card | mtd6 UBIFS mounted **ro**, a loop `tar`-ing it to /dev/null | the PIO read path alone |
   | I3 | NAND | idle as in hang 4, with the heartbeat | repeat and time-to-hang |
   | I4 | card | idle, same services, 2 h | baseline: the errata kernel idle (not yet run) |

   I1/I2 against I4 separates the NAND driver from "the root is on NAND".
   If I1 or I2 hangs, the breadcrumbs (item 2) say where.

## Hang 5: dc3b5f20 (errata + 8782 fix), NAND root, ~23 min (2026-11-07)

**What happened** (main session's report; logs `soak3_{dmesg,hb,netcon}.log`):
- Warm boot ~14:29, right after the mtd0 write, root `ubi0:filesystem`.
  A soak started at 448 s.
- The heartbeat (every 5 s) stopped between **1396.7 s** and ~1400 s. The
  last netconsole line was the soak's ping at 1371.5 s; no kernel
  line after it.
- No ping on eth0 or mlan0, no serial, no panic, no `panic=10` reset. Both
  lockup detectors stayed silent.
- The load: the soak loop sleeping between minute pings. Its whole-root
  `tar` reads (262 MB in ~6 s, so mostly page cache) ran 3 times without
  trouble, the last at 1325–1331 s. Klipper idle, Moonraker, the screen
  app, wpa_supplicant. Wi-Fi up, with power save off since 746 s.
- The dmesg is clean up to the hang: no NAND, BCH, UBI or UBIFS warning,
  no "Timeout on".

**The pattern now:**
- Plain nandboot hung on the card root under SD load. The errata patches
  fixed that (~97 min of SD load).
- The errata kernels have hung **twice on the NAND root**, both at ~23–30
  min uptime and both near idle.
- **Hang 4 is no longer alone, and it's not a Wi-Fi effect:** hang 5 had
  the 8782 fix in and Wi-Fi up.

### What runs periodically on a NAND root

| Mechanism | When | NAND operations |
|---|---|---|
| UBIFS write-buffer timer and VFS writeback (`dirty_writeback` 5 s, expire 30 s) | every few seconds while anything writes (Klipper and Moonraker logs, the Moonraker database, the screen app) | page **programs** into the journal |
| **UBIFS background commit** | when the journal's buds reach `bg_bud_bytes` = 13/16 of `max_bud_bytes` (journal 13 MiB, so ~11 MiB), or on any `sync` (`ubifs_sync_fs()` calls `ubifs_run_commit()`) | index and LPT writes, then **old buds unmapped** |
| **UBI background thread** (`ubi_bgt0d`) | after each unmap | **erases** of the freed PEBs |
| UBIFS garbage collection | when free LEBs run low (not the case: 107 MB used of 273) | reads, programs, erases |
| UBI wear levelling | erase-counter spread above the threshold (4096; max/mean 129/15 now) | — not now |
| UBI scrubbing | after a corrected bitflip read | reads, programs, erase |
| Patch 0010 | **no timers or periodic work**. Every wait is bounded (`POLL_TIMEOUT`, 200 ms for a program), with IRQs on | — |

**The lead: the first background commit and the erase burst after it.**
- The idle system writes a steady trickle. A background commit comes when
  ~11 MiB of journal has been written since the last one. At a few KB/s
  that's tens of minutes after boot, and it's the first time since boot
  that UBI *erases* blocks.
- On the card root (E, E2: 97 min, no hang) mtd6 is detached: no
  programs, no commits, no erases, ever.
- The large writes that worked on mainline (the stage 5 unpack, the 16 MB
  UBI test) ran as single bursts on an otherwise quiet system. They never
  had erases interleaved with the PIO reads that a running root does all
  the time.
- **Not ruled out:** the PTE-cleaning gap from hang 4 (a stale table walk
  can freeze the bus just as silently). The NAND trace tells the two apart:
  a hang inside a NAND step against a clean trace.

**Clock wraps don't fit:**
- jiffies wraps 5 min after boot (`INITIAL_JIFFIES`);
- `sched_clock` (32 bit at 1 MHz) wraps at 2147 s;
- the timer-2 clocksource wraps at 4295 s;
- the two hangs came at ~1400 s and ~1500–1800 s.

### Can a NAND access freeze the whole SoC without a lockup report?

- **A CPU spinning is ruled out.** Our NAND waits spin with IRQs on, and
  are bounded in time. A CPU stuck with IRQs off would be reported by the
  other CPU (buddy hard-lockup detector), and the other CPU's
  netconsole/serial would still work.
- **A bus stall fits completely.**
  - If a load or store to the NAND controller (NDSR, NDCB0, or the NDDB
    FIFO) never completes, that CPU stops mid-instruction.
  - The next access by the other CPU to the same peripheral bus stalls
    too: the UART, the timers, the GMAC, the SD controller.
  - Then nothing can report anything: no timer interrupt, no console, no
    network.
- Where it could happen:
  - The PIO paths (mainline's and 0010's) move a whole page through NDDB
    after a single RDDREQ/WRDREQ.
  - Error and early-UNCERR paths abandon a transfer midway.
  - `bch_v1_stop` drops ND_RUN between commands.
  - An erase finishing while a read's PIO is in progress can't happen (the
    NAND core serialises), but the controller's own state after an erase
    hasn't been exercised in mixed use.
- Whether the NFC stalls an NDDB access on an empty or full FIFO, instead
  of returning junk, is unknown. The trace below answers that.

### The debug build: m1-nandboot-nanddbg

`VARIANT=nandboot HANGTEST=nanddbg` (`variants/nandboot-nanddbg.config`,
`.dts`). It's the current nandboot (errata, 8782 fix) plus:
1. **The timer-0 hang watchdog, armed** (`timer_mv61x0.hang_wdt=30`): a
   bus stall resets the board within ~30 s instead of hanging until a
   power cut.
2. **pstore/ramoops**, 1 MB at 0x1e000000: the console log of the hung boot,
   in `/sys/fs/pstore/` after the reset.
3. **The NAND step trace (patch 0015)**, `marvell_nand.trace_phys=0x1e100000`,
   4 KB no-map.
   - The last 126 NAND controller steps go into the ring: each command
     (NDCB0–2), PIO in and out (start and end, with the length), each
     R/B wait and NDSR poll (start, end, result), the ISR (NDSR),
     bch_v1's RDDREQ poll (page, NDSR) and `bch_v1_stop`.
   - Each step has a µs timestamp, the CPU, and IRQs-off/interrupt flags.
   - The writes go through an uncached mapping, so they reach RAM before
     any following access.
   - At the next probe, **the driver prints the previous boot's ring to
     dmesg** ("trace #N ... cpuX step values"), then starts a new one.
   - A hang inside a NAND step shows as a ring that ends on a "start"
     with no "end" (e.g. `pio-in` without `pio-in-end`), on the hung CPU.
   - Patch 0015 is in every build, but it does nothing unless
     `trace_phys` is set.

**The first build (0685c985) didn't boot** (2026-11-07, from mtd0, warm and
cold alike):
- **What it showed:** after "Uncompressing Linux... done, booting the
  kernel.", nothing: no console line, no watchdog reset.
- **The decompressor layout was normal.** 5b17e2ec's banner shows the same
  pattern: relocated code below the kernel's `_end`, and the merged DTB at
  the top of the relocated range.
- **The cause is the 4 KB no-map hole at 0x1e100000.**
  - On 2-level ARM, one first-level entry pair covers 2 MB.
  - `map_lowmem()` section-mapped 0x1e000000–0x1e0fffff (whole 1 MB). Then
    0x1e101000–0x1e1fffff needed a page table in the same pair.
  - `arm_pte_alloc()` found the section in the pair's first entry and hit
    **`BUG_ON(pmd_bad(*pmd))`**. That's before `console_init()` (ttyS0
    comes up at ~0.17 s), so nothing was ever printed.
- A model of `map_lowmem()`'s rules (`kernel/m1/tools/lowmem_check.py`) gives "BUG at
  0x1e101000" for that layout, and "ok" for dc3b5f20, errata-dbg and the
  fixed layout.
- **Fix:** ramoops (1 MB at 0x1e000000) and the trace area (now 1 MB at
  0x1e100000; the driver uses its first 4 KB) are both no-map. Together
  they fill the aligned 2 MB pair, so no pair mixes a section with a page
  table. ramoops on a no-map area maps itself with `ioremap`, as it's
  meant to.
- **Rule for later DTs:** a no-map hole in lowmem must not leave part of a
  2 MB-aligned pair mapped. Make it a multiple of 2 MB, aligned, or put it
  next to another hole (the framebuffer works because its pair starts
  with the hole).

**Rebuilt 2026-11-07, not booted:**
- `m1-nandboot-nanddbg.uimg` md5 `e6cdb8a6616f4d15a37232b73bb59391`
  (2,823,460 bytes);
- modules tar `bfd2c0a7ffd2f8031356cfb885dde29c`. Use these modules with
  this image, not mtd0's.
- The config differs from the mtd0 image's (dc3b5f20) only in the
  command line, PSTORE (+ Reed-Solomon for its ECC) and the initramfs
  path. The DTB carries both no-map areas.
- **RAM-boot it first** (4GB-SD gap), before it goes into mtd0 again.
  Check that the console comes up, then `dmesg | grep -e ramoops -e
  "trace:" -e "hang watchdog"`.
- dc3b5f20 itself is unchanged. Patch 0015 joins later nandboot builds,
  inactive without `trace_phys`.

**It only helps if this same image boots after the reset.** The default
mtd0 kernel doesn't reserve these areas and doesn't print the ring.
- **Option A:** write nanddbg to mtd0 for the hunt, and the normal
  image back afterwards. That's a stage-4-type NAND write: owner's OK.
- **Option B:** after each reset, stop U-Boot on serial and RAM-boot
  nanddbg, as the rescue path does. That only works if someone is at the
  serial port before autoboot, and the mtd0 kernel must not boot in
  between, since it would reuse that RAM.

Before relying on it (owner present, after the errata-dbg check order):
1. the boot log shows the watchdog armed, ramoops, and
   `trace: NAND steps to 0x1e100000 (boot 1)`;
2. `echo 1 > /sys/module/timer_mv61x0/parameters/hang_wdt_nokick`: a reset
   within ~30 s;
3. after it, `dmesg | grep "trace #"` shows the steps of the boot before,
   and `/sys/fs/pstore/console-ramoops-0` exists.

**For the next NAND-root run:**
- **Speed up the suspect:** a loop on the NAND root that writes ~1 MB
  files, `sync`s (each sync forces a UBIFS commit) and deletes them
  (frees LEBs, so UBI erases). If the hang is in the commit/erase path, it
  should come in minutes instead of ~25 min.
- **Extend the heartbeat** with
  `/sys/module/marvell_nand/parameters/stats` and the UBI erase counters
  (`/sys/class/ubi/ubi0/max_ec`, `mean_ec`), so the last line shows
  whether erases were happening.
- **The control, card root + mtd6 rw:** the same write/sync/delete loop
  into UBIFS on mtd6 mounted from the card root (I1 in the hang-4
  section). If that hangs too, it's the NAND write/erase path, not "root
  on NAND".

### Reading the hang logger (`tools/hang_logger.sh`, 2026-11-07)

**marvell-nfc IRQs (4 in ~8 min) are an erase counter.**
- On this controller patch 0010's reads (the RDDREQ/CMDD loops) and
  programs (`bch_v1_wait_prog`) poll NDSR.
- Only the generic `exec_op` R/B waits (`marvell_nfc_wait_op()`) enable
  the RDY interrupt. Those are block erases, resets and status waits.
- So the per-second NFC IRQ delta in the logger counts erases. If the
  commit/erase lead is right, the last lines before a hang show it
  stepping, together with UBI's `max_ec`.

**The function-call IPIs on CPU1 (~150/s) are not cache maintenance.**
- On ARMv7 SMP, mainline never uses IPIs for cache maintenance:
  `cache_ops_need_broadcast()` is compiled to 0 for `__LINUX_ARM_ARCH__ >= 7`.
  The by-MVA and LoUIS operations rely on the hardware's broadcast. That's
  where the PJ4B wrappers (patch 0011) sit, and they're local code, not IPIs.
- Two things on ARM *do* send "Function call interrupts":
  1. **Remote wakeups.** The scheduler queues a wakeup on the target CPU
     with `__smp_call_single_queue()`, which ARM delivers as `IPI_CALL_FUNC`.
     All device IRQs (and so the softirqs that wake tasks) run on CPU0, so
     CPU0 wakes tasks that sleep on CPU1 all the time. That fits CPU1
     receiving ~3× more.
  2. **TLB maintenance by IPI**, if `tlb_ops_need_broadcast()` is true.
     That happens when ID_MMFR3 bits [15:12] (maintenance broadcast) are
     below 2 on this PJ4B, and nobody has read that field yet. Then every
     `flush_tlb_mm/page/range` goes through `on_each_cpu_mask()`.
     Fork/exec/exit and munmap are the big sources, and **the logger itself
     forks several `cat`/`awk` per second.**
- **To tell them apart:** compare the IPI rate with the logger paused for a
  minute (only a `sleep`), and with it running. A big drop means fork/exit
  traffic, so most likely TLB IPIs. Reading MMFR3 needs kernel code (an
  `mrc p15, 0, rX, c0, c1, 7`): a one-line `pr_info` at boot in a later
  debug build.
- **Relevance to the hangs:** these IPIs go through the generic csd lock
  and `smp_call_function` code, which uses atomics and spinlocks. Patch
  0012 covers those. If TLB flushes go by IPI, a lost TLB flush can't
  happen silently: the IPI path waits for the other CPU. A *stuck* IPI
  (the other CPU frozen on the bus) would hang the sender in
  `csd_lock_wait()` with interrupts on. That's one more way both CPUs end
  up stopped once one stalls.

## Hang 6: dc3b5f20, NAND root, 1337 s, caught by the hang logger (2026-11-07)

**What the logger shows** (once a second, from 512 s on; last line at 1336.69 s):
- **No NAND reads after 516.5 s.** The `stats` counters (29320 clean, 1485
  erased) stayed frozen for the last 820 s.
- **NFC IRQs stayed at 4**, so no erases at all.
- nr_dirtied/nr_written ~1/s, mostly the logger's own SD file; at most small
  UBIFS journal writes (programs) from Klipper/Moonraker. Dirty 4 kB.
- mmc0 ~11/s, usb2 ~250/s, eth0 ~3/s, timer1 100/s; IPIs steady.
- Nothing ramps before the stop.

**So hang 6 wasn't a commit or an erase burst.** The commit/erase lead from
hang 5 is weakened: the NAND sat read-idle and erase-free for 13 minutes,
and the board stopped anyway.

**Hang times so far** (NAND root, errata kernels, near idle):
- hang 4: unknown, between ~4 and ~30 min (last answer at 4 min, found at
  30);
- hang 5: 1397 s;
- hang 6: 1337 s.

Card-root runs passed 5054 s.

### (a) What on a NAND root could fire at a fixed ~22–23 min?

**Kernel side, nothing found:**

| Candidate | Period | Verdict |
|---|---|---|
| UBIFS write-buffer hrtimer | 3 s soft, +2 s | too short |
| VFS writeback | 5 s, expiry 30 s | too short |
| UBIFS background commit | journal fill, not time | none ran (no erases) |
| UBI background thread, wear levelling, scrubbing | on demand | no erases, no bitflips |
| Patch 0010 waits (`ktime` and `readl_*_poll_timeout`) | per operation | no long-lived state, no wrapping counter |
| The mtd6 write window | static module parameter | — |
| Hung-task detector / workqueue watchdog | 120 s / 30 s | same on the card root |
| jiffies (HZ 100) | wraps 300 s after boot | no |
| `sched_clock` / timer-2 clocksource (32 bit, 1 MHz) | 2147 s / 4295 s | no |

**One numeric coincidence, checked:** 2^39 cycles of the UPC clocks are
1386 s (FM, 396.6 MHz) and 1393 s (IO, 394.7 MHz). But the UPC firmware
(`klipper/src/upc/timer.c`) keeps a 32-bit accumulator over a 32-bit
down-counter that wraps every ~10.8 s. Nothing in it or in Klipper counts
to 2^39, and the card-root runs ran the same Klipper past 5054 s. Most
likely a coincidence. To close it, confirm the UPC firmware was actually
running in E2.

**What is NAND-root-only, then:** not a timer, but a *state*.
- On a NAND root, a long **read-idle stretch with occasional programs**
  (UBIFS journal writes) is normal: everything Klipper/Moonraker need is
  cached after a few minutes.
- So is **the first read after such a stretch**, when something evicts or
  first touches a file.
- Patch 0010 already documents one idle effect: after an idle gap, the
  first read can start with 4 stale FIFO bytes (`bch_v1_stop()` was added
  for it).
- Whether a longer gap, or programs without reads in between, leave the
  controller in a state where the next access stalls is exactly what the
  trace answers.

**A cheap discriminator, without the debug image** (owner's OK, NAND root):

| Run | What | If the idle state matters |
|---|---|---|
| R1 "keep busy" | every 20 s: `echo 1 > /proc/sys/vm/drop_caches` and read a few root files (e.g. `cat /usr/lib/python3*/os.py >/dev/null`) | no hang past 40 min |
| R2 "poke after idle" | leave it 15 min idle, then the same drop-and-read once | the hang comes at the poke, on demand |

### (b) Can a page program, not only an erase, stall the bus?

Yes, in principle. These are the only ways any NAND operation can stop a
CPU for good:
- **the PIO writes of the page into NDDB** (`marvell_nfc_xfer_data_out_pio`,
  2112 bytes after a single WRDREQ);
- **any NFC register access**, if the controller's bus interface wedges.

Everything else in the program path is bounded:
- the WRDREQ wait (`marvell_nfc_end_cmd`, `POLL_TIMEOUT`);
- `bch_v1_wait_prog` (200 ms, a sleeping poll).

The same goes for reads (NDDB reads after one RDDREQ) and erases (only
register accesses and the R/B interrupt wait). Hang 6 had at most programs
in flight, so (b) stays open. The trace's `pio-out` / `pio-out-end`
entries are what decide it.

### (c) The debug image

Already fixed and rebuilt: `m1-nandboot-nanddbg.uimg` **e6cdb8a6**, modules
**bfd2c0a7** (see "The first build didn't boot" above).
- RAM-boot it from the 4GB-SD gap with the NAND root.
- After a hang, its watchdog resets the board within ~30 s.
- The evidence (pstore console, NAND step ring) is only read if **nanddbg
  boots again** right after the reset. U-Boot's autoboot would start
  dc3b5f20 from mtd0, which neither reserves 0x1e000000–0x1e1fffff nor
  prints the ring, and may reuse that RAM.
- So the PC side should stop U-Boot on serial after the reset and RAM-boot
  nanddbg again, as for the first boot. Then: `dmesg | grep "trace #"` and
  `ls /sys/fs/pstore/`.

**Later, for unattended runs:** carry the "black box" in the default mtd0
image:
- both no-map areas, pstore, and the trace always on (a few uncached stores
  per NAND step);
- the hang watchdog armable at run time instead of on the command line;
- after any reset, the next mtd0 boot prints the ring by itself.

That's a new mtd0 kernel: RAM-boot test first (owner's rule), then the
owner's OK.

## Hang 7: the NAND step trace names the step (2026-11-07)

nanddbg (e6cdb8a6) RAM-booted from the 4GB-SD gap:
- **Boot 1** was up for more than 100 s; the `hang_wdt_nokick` test reset
  it, so the watchdog reset works.
- **Boot 2** froze at ~26 s uptime (last console line 26.04 s, Wi-Fi
  EAPOL), and the watchdog reset it.
- The normal mtd0 kernel booted once in between without overwriting the
  ring.
- nanddbg then went to mtd0 (owner's OK). Its boot 3 printed boot 2's
  ring: 126 steps, all on cpu0. The end of it:

```
#158348 25874934 us cpu0 poll 00000100              (CMDD after the PIO)
#158349 25874936 us cpu0 poll-end 00000000 00001d02
#158350 25882344 us cpu0 stop                       (7.4 ms later)
#158351 25882356 us cpu0 cmd 000d3000 bd580000 00000001   page 0x1bd58 (block 1781, page 24, mtd6)
#158352 25882359 us cpu0 rdd 0001bd58               <- last step: no rdd-end
```

The ~120 reads before it look normal: `rdd` → `rdd-end` in ~150 µs, the
two PIO bursts, a ~2 µs CMDD poll.

### What the ring says

- **The CPU never came out of bch_v1's RDDREQ wait.**
  - That wait is bounded: `ktime` against `POLL_TIMEOUT`, then
    `rdd-end` with -ETIMEDOUT or -EBADMSG. Every exit logs `rdd-end`, and
    none was logged.
  - So the CPU stopped inside one access in the loop:
    `readl_relaxed(NDSR)`, or the timer-2 read inside `ktime_get()`.
  - It's a **bus stall**, not a loop, as the hang signature (both CPUs
    silent, no detector) already suggested.
- **The command before it went through.**
  - `bch_v1_stop`, then `prepare_cmd` (ND_RUN poll, NDSR clear, ND_RUN set,
    WRCMDREQ poll) all completed. The `cmd` entry is logged after them,
    just before the three NDCB0 writes.
  - The stall can be the first NDSR read after those writes. Since the
    writes are posted, it can also be the NDCB0 write itself, surfacing
    on the next read.
- **The 7.4 ms gap before `stop`** is the NAND core lock being released and
  re-taken: the caller (UBIFS/UBI read path) did other work, or cpu0 ran
  something else. Only NAND steps are traced, so the ring can't say what.
  All 126 steps ran on cpu0. Gaps of 0.5–0.7 ms between pages appear
  elsewhere in the ring, so 7.4 ms is long but not unique to the failure.
- **Why the NAND root, and why only sometimes:** every page read polls NDSR
  in a tight loop for ~150 µs, plus a `ktime_get()` per turn. That's
  roughly 100–150 register reads per page while the controller loads the
  page and runs the BCH engine.
  - A NAND root does this for every file it reads. The card root does it
    only during the boot-time UBI scan.
  - If the controller's register interface can wedge when it's read at the
    wrong moment of that internal sequence, the odds grow with the number
    of reads polled. That fits hangs anywhere from 26 s (boot, many reads)
    to ~23 min (idle, few reads).

### What the vendor driver does instead (`mv61x0_nand_do_cmd`, `mv61x0_nand_irq`)

From the 3.2 image:
1. **Before each command:**
   - write NDSR = `0x001f9fff` (clear everything);
   - clear ND_RUN (NDCR bit 28);
   - read NDSR (dummy);
   - set NDECCCTRL (0x21 with ECC, 0 without);
   - write NDCR = setup | ND_RUN | ECC_EN;
   - read NDSR (dummy);
   - write NDSR = clear again.
2. **WRCMDREQ:** up to 11 tries. Each try reads NDSR once; if WRCMDREQ is
   set, clear it and write NDCB0 three times, otherwise **`udelay` and try
   again**. So it's a slow poll, not a tight one.
3. **Then it unmasks** the interrupts for this command in NDCR (for a read:
   RDDREQ, CORERR, UNCERR) and **sleeps in `wait_for_completion_timeout()`**
   (20 jiffies).
4. **The ISR** reads NDSR once and handles one condition:
   - RDDREQ (with UNCERR/CORERR as errors): mask bits 1, 3, 4;
   - or WRDREQ: mask bit 2;
   - or CMDD/BBD: mask 0x140.

   Then it clears NDSR (writing the value read back) and completes.
5. **Back in the caller, for a read:**
   - `__raw_readsl` of the data from NDDB;
   - one NDSR read for UNCERR;
   - write it back to clear;
   - done. **No CMDD poll after a read.**

**So the vendor reads NDSR about 4–6 times per page and never polls it
while the controller works.** Ours polls it ~150 times per page in the
RDDREQ wait, plus tight `POLL_PERIOD 0` polls for WRCMDREQ and CMDD. Upstream
marvell_nand polls the same way. That's fine on the PXA/Armada NFCs it was
written for, but evidently not here.

### Patch 0016: RDDREQ by interrupt (m1-nandboot-nandirq)

`kernel/m1/patches/0016-mtd-rawnand-marvell-mv61x0-rddreq-irq.patch`:
- **The wait:** bch_v1 reads now unmask RDDREQ and UNCERR before sending
  the command, sleep in `wait_for_completion_timeout()` (100 ms), and read
  NDSR once afterwards.
- **The ISR** completes on RDDREQ/UNCERR, as well as on R/B as before.
- **Unchanged:** the error handling (an early UNCERR means "no data, read
  again"; a timeout is counted) and the trace. `rdd` now logs `1` in its
  second value; the interrupt shows as an `isr` step between `rdd` and
  `rdd-end`.
- `marvell_nand.rdd_irq=0` (0644, also at run time) brings the busy-poll
  back, for an A/B run.
- **Default on**, in every later build. The short WRCMDREQ and CMDD polls
  (~2 µs each in the trace) are unchanged for now. If hangs remain, the
  trace will show whether they move there; the vendor's slow WRCMDREQ poll
  and its missing CMDD wait are the next step.

`HANGTEST=nandirq` builds nanddbg + 0016: watchdog, ramoops and the trace,
the same reserved areas (`variants/nandboot-nandirq.config`, `.dts`).
**Built 2026-11-07, not booted:**
- `m1-nandboot-nandirq.uimg` md5 `1f33eb4394d3dea7f132215f481d0fe6`
  (2,821,612 bytes);
- modules tar `c0185b50c3886192699924d3b2e253d7`;
- the config is nanddbg's; the code differs by patch 0016 (`rdd_irq` is in
  the kernel; nanddbg e6cdb8a6 doesn't have it).

**RAM-boot it from the 4GB-SD gap first**, then judge by hours of NAND root
against hangs at 26 s–23 min.

**pstore:** boot 2's console shows ramoops registered ("Registered ramoops as
persistent store backend", "using 0x100000@0x1e000000"). The "unknown
filesystem type 'pstore'" error most likely came from a mount under the
normal mtd0 kernel, which has no PSTORE. Under nanddbg/nandirq, use `mount -t
pstore pstore /sys/fs/pstore`.

## Hang 8: nandirq (interrupt-driven reads) froze outside any NAND step (2026-11-07)

nandirq (1f33eb43) was RAM-booted with the NAND root and ran
`tools/nand_read_soak.sh` (drop_caches + a full root `tar` every 2 min):
- Two passes went fine (155–229 s, 350–424 s).
- The heartbeat ran until 490.75 s, with no NAND reads after pass 1.
- It froze at ~490–495 s, in the idle sleep before pass 3. The watchdog
  reset it into nanddbg (mtd0), which printed the ring.

**The ring ends on a complete read:** `cmd` → `rdd` → `isr` (~155 µs) →
`rdd-end` → the two PIO bursts → the CMDD poll and `poll-end`, ~66 s
before the freeze. All 126 steps are on cpu0, every step type balanced, and
only reads.

**What this changes:**
- **Patch 0016 works as designed** (the read waits on the interrupt), and
  it **doesn't stop the freezes**.
- **The freeze doesn't come from the NAND controller being driven at that
  moment.**
  - Every command the driver issues goes through `marvell_nfc_send_cmd()`
    (all 11 call sites), which logs `cmd`: reads, programs, erases,
    resets, status reads.
  - Program data goes through the traced PIO-out, erases through the
    traced R/B wait, and every NFC interrupt through the traced ISR.
  - Not traced on their own are only the short polls inside a step
    (ND_RUN, WRCMDREQ, `bch_v1_wait_prog`). Each of them comes right
    after a logged `cmd` or `stop`.
  - The ring entries are written through an uncached mapping, in order.
  - So for ~66 s before the freeze, nothing issued a NAND command: no UBIFS
    program, no UBI erase, nothing.
- **Hang 7's ring**, which ended inside the RDDREQ wait, was most likely
  just the read in flight when the stall hit, during the boot read storm.
- **The write window and guard** (`marvell_nfc_write_allowed`) only run in
  `send_cmd`, for program/erase commands. With no command, they don't run.
  An open window does nothing on its own.
- **A non-NAND bus master** (USB/Wi-Fi, GMAC, SDHCI) can't be excluded by
  the ring. But all of them ran in the card-root soaks too (84 and 82 min,
  Wi-Fi up).

### What is NAND-root-specific, if not the controller?

The difference is the **state the NAND root leaves in memory and the MMU**,
not controller activity:
1. **Page-cache pages filled by the CPU.**
   - On the NAND root, every file page (and so every executable and
     library page) is written by the CPU: PIO from NDDB into a buffer,
     then a memcpy into the page.
   - On the card root, SDHCI DMA writes it, and the DMA API's
     maintenance invalidates the CPU caches.
   - CPU-written pages that are then executed need a D-cache clean to the
     point of unification, plus an I-cache invalidate seen by both cores.
   - The soak's `drop_caches` makes every running program refault its
     text from NAND every 2 min.
2. **UBI/UBIFS's vmalloc buffers.** UBI reads go through LEB-sized vmalloc
   buffers. `vfree()` is lazy: the kernel page-table entries and the TLB
   flush for them are purged in batches later, from a worker. That's
   kernel-TLB maintenance on both CPUs at arbitrary later times. Whether
   it goes by IPI depends on this PJ4B's ID_MMFR3 (not read yet; see the
   logger notes).
3. **Both of these lean on the PJ4B errata area that isn't ported yet:**
   - page-table cleaning: the vendor cleans PTE writes, while mainline
     trusts the table walker on SMP;
   - the vendor's PoUIS clean;
   - `BZ_833` / `BZ_664`.

### Splitting it: tests in order

1. **Card root, UBIFS on mtd6 mounted rw, the same read soak on the mtd6
   mount** (drop_caches + `tar` of the UBIFS mount every 2 min, then
   idle). This is the main session's option 2, plus load.
   - **Hangs:** UBI/UBIFS/NAND activity alone is enough, with executables
     still from SD. Look at UBI's vmalloc and TLB side and at the
     controller.
   - **No hangs over ≥ 1–2 h:** it's *running from* NAND that matters
     (CPU-filled executable pages). Look at D/I-cache and TLB coherency.
2. **NAND root with the window closed** (option 1). It needs a writable
   overlay for Klipper/Moonraker, otherwise they fail, so it's harder to
   set up. It separates programs from reads, but the ring already shows
   no programs near the freeze, so it's lower value.
3. **A full register trace** (option 3) adds little now: the controller
   was idle. What's needed is *what the CPUs were running*. Hence:

### Patch 0017: PC samples of both CPUs (m1-nandboot-nandpcs)

`kernel/m1/patches/0017-mtd-rawnand-marvell-mv61x0-pc-samples.patch`, on top
of 0016, only active with `marvell_nand.trace_phys`:
- **A pinned hard hrtimer on each CPU, every 10 ms**, records the
  interrupted PC, LR, SP, CPSR, jiffies and µs time.
- The samples go into the 4 KB page after the NAND ring (0x1e101000): 60
  per CPU, uncached.
- A CPU stalled in a bus access takes no more interrupts, so its last
  sample is from ≤ 10 ms before it stopped. The other CPU's last samples
  show what it was doing too, e.g. spinning on a lock or waiting for an
  IPI.
- **The next boot of a 0017 kernel prints the last 8 samples per CPU**
  ("pcs boot N cpuX #seq ... pc ... lr ...").
- **Under any other kernel that leaves the page alone** (nanddbg maps only
  the first 4 KB), `kernel/m1/tools/pcs_dump.py` reads it from /dev/mem,
  read-only.
- Resolve the PCs with `m1-nandboot-nandpcs-System.map`.

`HANGTEST=nandpcs` = nandirq + 0017:
- `m1-nandboot-nandpcs.uimg` md5 `3ec9c45b26d47be26e43bc9b84a1bcd4`
  (2,824,116 bytes);
- modules `c181d7beebc48f067837f53acb496c53`;
- the config is nandirq's. Built, not booted.

**Run plan:**
1. RAM-boot it first. Check that `pcs: PC samples every 10 ms` and the
   trace line appear, and that the board stays up for a few minutes (the
   sampler runs inside the existing 10 ms tick; it adds no interrupts,
   see the nandpcs soak below).
2. Then either:
   - with the owner's OK, put it in mtd0, so the reset lands in it and it
     prints both the ring and the samples;
   - or keep nanddbg in mtd0, and right after the reset run
     `python3 -I pcs_dump.py` (root) before anything else.

### More nanddbg (polling) rings, 2026-11-07 (passive serial capture)

| Boot that printed it | Ring ends at | CPU | Last steps |
|---|---|---|---|
| 12 | 21.09 s | cpu1 | `cmd` (read, page 0x2bfe6), `rdd`, no `rdd-end` |
| 13 | 69.31 s | cpu1 | a **program**: `pio-out` 0x800 / end, `pio-out` 0x20 / end, then nothing |
| 14 | 30.15 s | cpu1 | `cmd` (read, page 0x3bb45), `rdd`, no `rdd-end` |
| 15 | alive at 121 s (capture stopped) | | |

In boot 13 the ring stops after the program data. The program-done wait
(`bch_v1_wait_prog`, bounded at 200 ms) isn't a traced step, so the stall
was in or after it, before the next command.

**Reading:**
- With the polling driver, the freezes come 20–70 s after boot, during the
  startup I/O, on either CPU (hang 7 was cpu0).
- With interrupt-driven reads (nandirq), the one freeze came at ~490 s,
  with the NAND idle.
- That fits **a stall source independent of the NAND step, which catches
  whatever is on the bus.**
  - The polling driver is on the bus nearly all the time during boot, so
    the ring usually shows a NAND step.
  - The stall rate is highest during heavy boot I/O: NAND, SD and the
    Wi-Fi start at once.
- The PC samples (patch 0017, nandpcs) and test 1 above (card root, UBIFS
  rw on mtd6, the read soak) are the next steps.

## nandpcs: 4 h of NAND-root read soak without a freeze (2026-11-07)

nandpcs (3ec9c45b: nandirq + the 10 ms PC sampler) was RAM-booted with the
NAND root and ran the read soak for 14163 s (3 h 56 min):
- 70 full `tar` passes of `/` after `drop_caches`;
- NAND stats `7968475,5,1532,0,0,0,0,0,0,1532`: 5 corrected, no fail,
  timeout or uncorrectable;
- UBI max_ec 129;
- dmesg: no oops, lockup, NAND or UBI errors; only the boot-time mwifiex
  `CMD_RESP 0x242/0x23f result=2` lines.

The owner counts the soak as passed. No freeze, so no PC samples.

| Build | Reads | Sampler | Result |
|---|---|---|---|
| nanddbg e6cdb8a6 | busy-poll | – | froze in 20–70 s (≈ 6 times) |
| nandirq 1f33eb43 | interrupt | – | froze at ~490 s (once, hang 8) |
| nandpcs 3ec9c45b | interrupt | 10 ms | 14163 s, no freeze |

### How much does one nandirq freeze say?

nandirq has one freeze in one run, so its freeze rate is barely known. If
its mean time to a freeze were *T*, the chance of 4 h without one is
e^(−236 min / *T*):

| *T* | 8 min | 30 min | 1 h | 2 h |
|---|---|---|---|---|
| P(no freeze in 4 h) | ~10⁻¹³ | 0.04 % | 2 % | 14 % |

So the sampler very likely matters if nandirq freezes about as often as
hang 8 suggests, but a run of nandirq without the sampler is still needed
before calling it a heisenbug.

### What the sampler changes (and what it doesn't)

- **It adds no interrupts.** The config is `HZ_PERIODIC`, `HZ=100`, with
  no `HIGH_RES_TIMERS`. Without high-resolution mode, hrtimers run from
  the tick (`hrtimer_run_queues()`), so the "10 ms" sampler fires inside
  the existing 10 ms tick. It can't keep a CPU out of WFI any longer than
  the tick already does. (The nandpcs run plan said it adds 200
  interrupts/s; that was wrong.) So "nohlt" tests WFI itself, not the
  sampler.
- **What it does add, per tick and CPU:** `get_irq_regs()` and eight
  uncached stores into the reserved page at 0x1e101000. The last store is
  a `writel()`. On this SoC (`ARM_HEAVY_MB`, `mach-mv61x0/mv61x0.c`)
  `writel()` runs `wmb()`, which is `dsb(st)` **plus `soc_mb`: a write of
  0x01010101 to the DDR controller's +0x530**, the vendor's "cache sync",
  most likely a write-buffer drain for the controller's ports.
- **The tick path itself is all `_relaxed`** (timer-mv61x0.c), and the
  NAND trace only writes while the NAND works. So with the sampler off, an
  idle CPU hardly ever runs a DSB or drains the DDR write buffers. With it
  on, both CPUs do every 10 ms. Hang 8 came after ~66 s with no NAND step,
  in the idle sleep.
- **Against a simple "drains protect" story:** the trace's own `writel()`s
  (two per NAND step, so thousands per second during reads) didn't help
  the polling kernels. nanddbg froze in 20–70 s, often in the boot read
  storm, which dc3b5f20 (same polling, no trace) survived every boot,
  freezing only after ~20–30 min. So the switches below measure instead
  of guessing.

### Patch 0018: run-time switches (m1-nandboot-nandab)

`kernel/m1/patches/0018-mtd-rawnand-marvell-mv61x0-pcs-idle-switches.patch`,
on top of 0017. Three `marvell_nand` parameters, all 0644, so one image
covers every A/B without a reboot (the command line is forced):

| Parameter | Default | Values |
|---|---|---|
| `pcs_ms` | 10 | sampler period in ms (10 ms steps, from the tick); **0 stops it** on both CPUs, a value > 0 restarts it |
| `pcs_mb` | 2 | barrier before each sample's last store: **2** `wmb()` = DSB + DDR drain (as 0017), **1** `dsb(st)` only, **0** none |
| `idle_poll` | 0 | **1**: idle CPUs spin in `cpu_idle_poll()` instead of WFI (what `nohlt` does); 0: WFI again |

With the defaults it behaves as nandpcs. For example:

```
echo 0 > /sys/module/marvell_nand/parameters/pcs_ms
cat /sys/module/marvell_nand/parameters/pcs_ms /sys/module/marvell_nand/parameters/pcs_mb /sys/module/marvell_nand/parameters/idle_poll
```

`HANGTEST=nandab`, the config is nandpcs's (watchdog, ramoops, trace, the
same reserved areas). DEBUG IMAGE: it arms the hardware watchdog, so each
run needs the owner's OK. RAM-boot it first, as always. **Built
2026-11-07, not booted:**
- `m1-nandboot-nandab.uimg` md5 `557a3939d6db8998a38c86198dd92aa6`
  (2,822,724 bytes);
- modules tar `e44e008f58247be4492dcc559f6c10d9`;
- the boot line now reads `pcs: PC samples every 10 ms to 0x1e101000
  (pcs_ms)`.

The switches also compile into the default image the next time it is
built, but do nothing there: the sampler needs `trace_phys`, and
`idle_poll` defaults to 0. mtd0's dc3b5f20 is unchanged.

### Runs, in order

Set the switches as soon as there is a shell (the boot read storm runs
with the defaults; hang 8 came in the idle phase), then the same read soak,
up to 2 h each:

1. **R1: `pcs_ms=0`** (= nandirq). The replication.
   - **No freeze in 2 h:** hang 8 was a rare event, and 0016 alone has
     ~6 h with one freeze. Then run long soaks with the sampler on
     (defaults), so that the next freeze comes with samples.
   - **A freeze:** the sampler protects (one freeze each in 490 s and R1,
     none in 4 h with it). Go on with R2–R4.
2. **R2: `pcs_ms=10 pcs_mb=0`**: the sampler without the barrier. A
   freeze means the barrier (DSB or drain) is the protecting part; no
   freeze means it's the tick-time work or timing.
3. **R3: `pcs_mb=1`** (only if R2 froze): DSB alone vs DSB + DDR drain.
4. **R4: `pcs_ms=0 idle_poll=1`**: no WFI, no sampler. No freeze points at
   WFI/idle (the PJ4B WFI errata area).

After a freeze the reset lands in mtd0 (nanddbg e6cdb8a6), which prints
the NAND ring; with the sampler on, `pcs_dump.py` reads the samples there.
Resolve them with `m1-nandboot-nandab-System.map`.

**Optional, on the board as it is now (nandpcs, idle):** `python3 -I
pcs_dump.py` twice, a few seconds apart, shows whether cpu1's samples
advance at ~100/s. If they don't, CPU1 gets no tick of its own (there is
only one clockevent, timer 1, and no TWD), and the sampler only ever ran
on cpu0.

## Hang 9: nandpcs froze too, with samples (2026-11-07, ~22:30)

The same nandpcs image (3ec9c45b), written to mtd0 with the owner's OK and
booted by U-Boot from NAND, **froze at ~143 s**, in the read soak's idle
gap. The watchdog reset it into the same image, which printed the ring and
the samples (console: `hang9_mtd0_nandpcs_serial.txt` in the shared
notes).
- **So the sampler doesn't stop the hang.** The 4 h run above was luck or
  the boot path (it came from the SD-gap mmc boot). The boot path alone
  doesn't explain it: nanddbg's boot 2 (hang 7, 26 s) and nandirq (hang 8,
  490 s) were RAM boots from the gap too. **R1–R4 above are dropped**; the
  switches stay in nandab and in every later build.
- **The ring:** the last NAND step is a complete read, ~24 s before the
  freeze, as in hang 8.
- **The samples** (resolved with `m1-nandboot-nandpcs-System.map`):
  - cpu0, last #14327 at 142970944 us: `do_idle+0x88`, the return from
    WFI (`lr ct_kernel_enter+0x40`). Before it, the same idle point, one
    user-mode sample and `filemap_map_pages+0xfc`.
  - cpu1, last #14321 at 142970930 us: `xas_next_entry+0x80` (a page-cache
    fault-around, SVC mode, IRQs on), after a run of idle samples.
  - Both take one sample per jiffy, the two within 13–67 µs of each other
    on the same jiffy.

### The samples fit a lost tick as well as a stalled bus

There is only one clock event device: timer 1 (GIC SPI 21), with no TWD.
CPU0 owns it, and **CPU1's tick is a broadcast IPI from CPU0's timer
interrupt** (`tick_do_broadcast()` sends the IPI, then runs CPU0's own
handler). The paired samples on every jiffy are that broadcast. So:
- **Both CPUs stopping on the same tick is no evidence that both
  stalled.** It's what happens if CPU0 stops taking timer 1's interrupt.
- **A lost timer 1 interrupt** (the timer stops, its status isn't cleared
  in time, or SPI 21 stays active/pending in the GIC) stops every timer on
  both CPUs:
  - the console heartbeat and every sleep;
  - the hang watchdog's kicks (a delayed work), so timer 0 resets the
    board 30 s later;
  - the buddy hard-lockup detector, which runs from hrtimers, so the
    tick, on the other CPU. That's why no detector ever fired.

  The CPUs would still take other interrupts (Ethernet, USB, UART) and
  run their softirqs.
- **A bus stall** looks the same from the console, the watchdog and the
  samples.

Every hang so far fits both. The NAND-root link would then be in what
makes timer 1's interrupt get lost (an irq-off or masked window, or a GIC
active state never ended), not only in a bus access.

### Telling them apart

1. **Free, with the image in mtd0 now:** during the soak, `ping -t` the
   board's Ethernet address from the PC with timestamps, and leave a
   serial terminal open.
   - When the heartbeat stops, are there still ping replies for the ~30 s
     until the watchdog resets it? Does a key on the serial console still
     echo? (tty echo and ICMP need no timer.)
   - **Replies:** the CPUs are alive and the tick is lost.
   - **No replies:** a stall, or both CPUs stuck with interrupts off.
2. **m1-nandboot-nandtick: an independent tick watchdog**
   (`timer_mv61x0.tick_check=MS`, in `timer-mv61x0.c`, 0 = off by
   default):
   - Timer 3, otherwise unused and only acknowledged, runs every 100 ms,
     with its interrupt (SPI 23) routed to **CPU1**. It watches the count
     of timer 1 interrupts.
   - **After 200 ms without one**, it prints, at `KERN_EMERG`, then once a
     second:
     - timer 1's ctrl/load/count, the timer status, timer 2;
     - SPI 21's GIC enable/pending/active bits, target and priority,
       GICD_CTLR;
     - CPU1's GICC ctlr/PMR/RPR/HPPIR;
     - jiffies;
     - how many of its IPI pings CPU0 has answered.
   - **At 2 s:** `trigger_all_cpu_backtrace()`, which gives CPU0's stack
     if CPU0 still takes IPIs.
   - **At 3 s:** a panic, so the log lands in pstore (dmesg-ramoops)
     before the watchdog's 30 s.

   What the output means:
   - **Nothing printed** (the watchdog resets as before): CPU1 stalled too,
     on its first register read. That's a bus stall.
   - **Reports with timer 1 still counting and status set, or SPI 21
     pending/active:** the interrupt was lost between the timer, the GIC
     and CPU0. The pongs and the backtrace show whether CPU0 runs, and
     where.
   - **Timer 1 stopped (ctrl without enable, count still):** something
     wrote the timer, or it was never re-armed.

`HANGTEST=nandtick` = nandab + `timer_mv61x0.tick_check=100`
(`variants/nandboot-nandtick.config`, the same reserved areas). DEBUG
IMAGE: it arms the hardware watchdog, and it panics on a lost tick, so
each run needs the owner's OK. RAM-boot it first. **Built 2026-11-07, not
booted:**
- `m1-nandboot-nandtick.uimg` md5 `9586a6d3c30dcb8b4310b2a5431c1c2d`
  (2,825,020 bytes);
- modules tar `37b536ff355f8889cc459b8f7754943a`.

The boot log should show `mv61x0-timer: tick check every 100 ms on timer 3
(irq N, cpu1)`. In a running system, nothing more: timer 1 never misses
200 ms. After a freeze, read `/sys/fs/pstore/` (mount it under nandtick or
nanddbg) as well as the console. nandab (557a3939) was built before this
change and has no tick check. The default image is unaffected until it
is rebuilt (the check is off without the parameter).

**Time units in the ring and the samples:** both store
`ktime_get_mono_fast_ns() >> 10`, i.e. units of 1.024 µs, not µs. Multiply
by 1.024 to get uptime. That's the "~3 s offset" against the SD hang log
in hang 9. The last samples (142970944) are at **146.40 s** uptime, and the
log's last line (146.13 s) came just before them. So nothing kept running
after the samples stopped. The last NAND step (118983074) is at 121.84 s,
the end of TAR 0 (121.86 s).

## Hang 10: nandtick froze silently, a real stall (2026-11-07, ~23:25)

nandtick (9586a6d3) was RAM-boot checked, then booted by U-Boot from mtd0
with the NAND root. It froze at ~825 s uptime, and the watchdog reset it.
- **Tick check:** printed nothing and didn't panic. pstore's console ends
  at 752 s.
- **Ping (1 Hz) and the serial probe** both stopped at the same second.
- **The PC samples** stop together at 825.4 s.
- **NAND** was idle for 73 s before it.

So this was **not a lost tick**. CPU1's timer-3 interrupt, the network
and the UART all stopped together: **a stall of the whole interconnect
(or of both CPUs with interrupts off), as first assumed.** Hang 9's
samples fit that too.

The last samples:
- cpu0: mm work (`__mmap_region`, `filemap_map_pages`) and the UVC isoc
  decode (`uvc_video_decode_isoc`/`_end`);
- cpu1: page-fault and VMA code (`lock_vma_under_rcu`, `vma_prepare`,
  `do_PrefetchAbort`).

**ustreamer** was streaming the USB camera (MJPEG, isoc) all the time. So
the EHCI controller's DMA and interrupts were busy, and a CPU was copying
out of its isoc buffers.

Next, no build needed: **the same soak with ustreamer stopped**, from
mtd0, for ≥ 2 h.
- With freezes every 20 s–30 min so far, 2 h clean is strong evidence
  (e^−4 to e^−8 if nothing changed).
- If it stays clean, start ustreamer again in the same boot, and see
  whether the freezes come back within ~1 h.
- Check first whether ustreamer ran during the card-root soaks (84/82 min
  clean). If it did, the camera alone isn't enough, and it's the camera's
  DMA together with the NAND root.

## Hang 11: the camera is ruled out; a page-table lead (2026-11-07, ~23:57)

nandtick from mtd0, with ustreamer killed at 55 s, froze at ~683.15 s,
during TAR 3. It was silent again (no tick check, no panic, ping and probe
lost), as in hang 10. **So the camera isn't needed for the hang.**
- **NAND was active this time:** the ring ends with `cmd` (page 0x3c674),
  `rdd`, and the ISR's entry (`isr 00001802`, RDDREQ) at 683.148 s, and
  no `rdd-end` after it.
- **cpu1 was 2 ms earlier in `set_pte_range+0x2c`** (from
  `filemap_map_pages`, `set_ptes`).

**Across hangs 9–11, one CPU's last sample is in the page-fault
fault-around / PTE path:**
- hang 9: `xas_next_entry` under `filemap_map_pages`;
- hang 10: `lock_vma_under_rcu`, with the other CPU in `__mmap_region`;
- hang 11: `set_pte_range`.

The hang logger forks every second, so faults are common, but this is the
gap listed under "What the errata work doesn't cover yet": mainline on
SMP doesn't clean PTE writes out of the L1 D-cache ("MP extensions imply
L1 PTW"), while the vendor's 3.2 kernel does.
- If this PJ4B-MP's walker reads memory rather than L1, a newly written
  PTE can be missed, and the walk uses a stale entry. The PTE pages are
  recycled page-cache/anon pages, so a stale entry can name any physical
  address, and an access nothing decodes can stall the interconnect.
- Fault-around writes up to 16 PTEs per fault. On the NAND root every
  page-cache refill (`drop_caches` + `tar` + forks) goes through it.
- A stale *valid* entry mostly gives a wrong page, not a stall. So this
  is a lead to test, not a proof.

### Patch 0019 and m1-nandboot-nandpte

`kernel/m1/patches/0019-arm-pj4b-mv61x0-pte-clean.patch`: the option
`CONFIG_PJ4B_MV61X0_PTE_CLEAN` (off by default), as the vendor kernel and
mainline UP do:
- `cpu_v7_set_pte_ext`: `mcr p15, 0, r0, c7, c10, 1` (clean the hardware
  PTE's line to PoC) on SMP too;
- `cpu_v7_dcache_clean_area`: the clean loop on SMP too;
- `v7wbi_tlb_flags_smp` gets `TLB_DCLEAN`, so `flush_pmd_entry` and
  `clean_pmd_entry` clean on SMP too.

`mach-mv61x0/mv61x0.c` now also prints ID_MMFR0/1/3, TTBR0 and TTBCR at
boot (in every build):
- MMFR3[23:20] is "coherent walk";
- MMFR3[15:12] is maintenance broadcast;
- TTBR0's low bits are the walk's cache attributes.

That answers the walker question directly, and the TLB-IPI question from
the logger notes.

`HANGTEST=nandpte` = nandtick + the option. DEBUG IMAGE (hang watchdog,
tick-check panic): the owner's OK, then RAM-boot first, then mtd0.
**Built 2026-11-08, not booted:**
- `m1-nandboot-nandpte.uimg` md5 `7ee63c264489235143df6a3a49b84133`
  (2,823,620 bytes);
- modules tar `8f06a39f825458ee733892c7a2eaaf9a`;
- the config differs from nandtick only by `CONFIG_PJ4B_MV61X0_PTE_CLEAN=y`.
- The boot log should show `mv61x0: ID_MMFR0 ... page-table writes
  cleaned`.

### m1-nandboot-nandup: the same without CPU1

`HANGTEST=nandup` = nandtick with `maxcpus=1`: no second core, so no
cross-core coherency, no TLB/cache broadcast, no IPIs. The old `up` image
(0eff2431, test 1 of the first plan) was never run and has none of the
debug tooling. With only CPU0, the tick check runs on CPU0 too, so it can
only tell a lost tick from a CPU0 that stopped taking interrupts. **Built
2026-11-08, not booted:** `m1-nandboot-nandup.uimg` md5
`d7861757df1dd8ddd8f7f88fc62fd3a5` (2,823,212 bytes), modules tar
`dd208ffb00fe03e7fbec94c64c4a11e9`. It has the MMFR print, not the PTE
clean. The same DEBUG-IMAGE rules apply.

### Order

Freezes now come every ~2–14 min from mtd0 (hangs 9–11: 143, 825, 683
s), so 2 h without one is strong evidence (e^−8 or better).
1. **nandpte, 2 h of the same soak from mtd0.** First read the MMFR3/TTBR0
   line.
   - **No freeze:** the PTE clean is both the diagnosis and the fix; it
     goes into the default config.
   - **A freeze:** go to 2.
2. **nandup, 2 h.**
   - **No freeze:** an SMP problem other than PTE cleaning (TLB/cache
     broadcast, the 6011 area, the vendor's PoUIS clean).
   - **A freeze:** not SMP. Go back to the controller (hang 11 was in the
     NAND ISR), and to the DMA masters without the camera.

**nandpte's ID registers** (RAM boot, 2026-11-08):
`ID_MMFR0 01100103 MMFR1 40000000 MMFR3 00102211, TTBR0 0000406a TTBCR 00000000`.

| Register | Value | Meaning |
|---|---|---|
| MMFR3[23:20] | 1 | coherent walk: PTE updates need no clean for the walker |
| MMFR3[15:12] | 2 | cache, branch-predictor and TLB maintenance broadcast in hardware, so `tlb_ops_need_broadcast()` is false and the ~150/s function-call IPIs on CPU1 are remote wakeups, not TLB IPIs |
| MMFR3[11:8], [7:4], [3:0] | 2, 1, 1 | BP invalidate all and by MVA; cache maintenance by set/way and by MVA |
| MMFR1[31:28] | 4 | the branch predictor needs no flushing |
| MMFR0 | VMSAv7, 1 shareability level, ACTLR | |
| TTBR0 0x406a | | tables at phys 0x4000, walks inner WBWA (IRGN 01) and outer WBWA (RGN 01), shareable, inner shareable (S, NOS): mainline's `TTB_FLAGS_SMP` |

So by its ID registers, mainline is allowed to skip the clean. If nandpte
stops the freezes, this part's coherent-walk claim doesn't hold (at
least not under this load), which the vendor kernel's cleaning would
then be working around. If it doesn't stop them, the ID registers make
the PTE path an unlikely cause, and nandup comes next.

## Hang 12: nandpte froze in 98 s; the PTE clean is ruled out (2026-11-08)

nandpte (7ee63c26) from mtd0 froze at 97.83 s, during TAR 0. It was
silent, as in hangs 10–11 (no tick check, ping and probe lost together).
- **So cleaning page-table writes doesn't help**, as the ID registers
  (coherent walk) predicted. Patch 0019 stays as an option, off.
- **The ring ends like hang 11's:**
  - the read was issued on cpu1 (`stop`, `cmd` page 0x27b3a, `rdd`);
  - the last step is cpu0's `isr 00001802` (RDDREQ) at 97.833 s.
- **The last samples**, ~9 ms before:
  - cpu0: `set_ptes` (fault-around);
  - cpu1: `first_zones_zonelist`, after `__raw_readsl` in the PIO read and
    `ubi_eba_read_leb`.

**What the ISR does after the logged step** (`marvell_nfc_isr`): `bt_log`
writes the entry with two `writel()`s, each followed by the DDR drain
(below). Then:
1. an NDCR read;
2. an NDCR write (masking RDDREQ);
3. `complete()`, which wakes the reader on cpu1: an SGI, i.e. a GIC
   distributor write.

Any of these, or the drains, can be the access that never completes.

**Why not trace the ISR step by step first:** hangs 9 and 10 froze with
the NAND idle for 24 and 73 s, in the same silent way. The stall doesn't
need the NAND ISR. In hangs 11–12, cpu0 just happened to be in the ISR,
doing MMIO, when the interconnect stopped. A finer ISR trace would say
which access, but not what stopped the bus.

### One candidate the tracing itself feeds: the DDR drain

On this SoC every `mb()`/`wmb()`, and so every `writel()`, also writes
0x01010101 to the DDR controller at 0xfa300000 + 0x530 (`soc_mb`, the
vendor's "cache sync", `mach-mv61x0/mv61x0.c`). The drain rate and the
freeze rate seem to go together:

| Build | Drains, beyond the drivers' own `writel()`s | Freezes |
|---|---|---|
| dc3b5f20 (no trace) | none | after ~20–30 min |
| nanddbg (trace, busy-poll) | 2 per NAND step, thousands per second during reads | in 20–70 s, often in the boot storm |
| nandirq / nandpcs / nandtick / nandpte | trace, and the sampler: 200/s | 143 s – 14 min, once 4 h clean |

The card-root soaks drain heavily too (`sdhci_writel` is a `writel()`)
and didn't freeze in 82–84 min. So if the drain matters, it matters
together with the NAND root's traffic: CPU-filled pages and PIO from
NDDB. That's a guess, but a cheap one to test. The drain-off A/B of
2026-10-29 (`mcsync_ab_test.md`) showed no functional difference, on
the card root and for a short time only.

**`mv61x0.mc_drain`** (new, in `mv61x0.c`, every build, 0644, default 1 =
stock): 0 skips the drain write in `soc_mb`. It can be switched at run
time in `/sys/module/mv61x0/parameters/mc_drain`. The boot line says
`..., off (mc_drain=0)` when it starts off.

**`HANGTEST=nandmb`** = nandtick with `mv61x0.mc_drain=0` on the command
line. DEBUG IMAGE: the owner's OK, a RAM boot first, then mtd0.
**Built 2026-11-08, not booted:**
- `m1-nandboot-nandmb.uimg` md5 `5f696673782f10446ee2eefa4464da19`
  (2,823,092 bytes);
- modules tar `1a6ec314f2c121e3c061ea7a4990665d`.

The config is nandtick's (plus the new, unset `PJ4B_MV61X0_PTE_CLEAN`
symbol). nandup (d7861757) was built before `mc_drain` existed and
doesn't have it.

### Order

1. **nandup (maxcpus=1), 2 h from mtd0**, as planned. It's the cleanest
   split.
   - **A freeze:** it's not SMP. Go to nandmb.
   - **No freeze:** it's SMP. nandmb then tells whether the drain is the
     SMP part (two CPUs draining the same controller).
2. **nandmb, 2 h from mtd0.**
   - **No freeze:** the drain write is part of the trigger. Next: does the
     vendor drain at all on the NAND path, and does it serialise the
     drain between the CPUs?
   - **A freeze:** the drain is cleared too. Next the ISR-step trace and
     the DMA masters (EHCI with Wi-Fi only, GMAC).

## nandup: one CPU, 2 h from mtd0 without a freeze (2026-11-08)

nandup (d7861757, `maxcpus=1`, modules dd208ffb) from mtd0, on the NAND
root, with the camera on:
- 27 full passes (`IRQSOAK DONE 27 passes` at 7281 s), still up at 7730 s;
- NAND: 3055430 reads, 27 corrected, no fail, timeout or unc;
- no oops, lockup, tick-check or panic line, and no reset;
- the probe answered throughout, and ping lost only 9 single packets of
  ~7660 (the PC's usual drops).

The two-CPU builds from mtd0 froze in 98 s – 14 min (hangs 9–12). If one
CPU froze as often, 2 h clean would have odds of e^−8 or less. **So the
freeze needs both CPUs.**

What remains on the SMP side:
1. **nandmb** (next): both CPUs writing the DDR controller's drain
   register.
2. **What the vendor sets up differently for the second core:**
   - the SCU control register (speculative linefills, standby);
   - ACTLR (SMP/FW bits);
   - the PJ4B auxiliary function modes (CP15 c15), against mainline's
     `__v7_pj4b_setup`;
   - how `platsmp.c` brings up CPU1 compared with the vendor's
     secondary start.

   That's offline reading of the vendor image, no board time.
3. **The 6011 erratum and cache-wrapper area** is already in every build.
   The vendor's PoUIS clean and `BZ_833`/`BZ_664` are still unported.

**Workaround if the hunt drags on:** `maxcpus=1` in the default nandboot
config is a stable NAND-root kernel today, at the cost of the second
core. Klipper's host process doesn't need two cores, but the owner
should decide on that.

## Hang 13: the drain is ruled out; the CPU setup differs from the vendor's (2026-11-08)

nandmb (5f696673, `mc_drain=0`) from mtd0 froze at 172.1 s, silent as
before.
- **The last samples:** both CPUs on the same tick in mm code. cpu0 was in
  `___slab_alloc`, cpu1 in `do_page_fault` from a prefetch abort.
- **The NAND** was idle for 22 s. The last step is a page program's data
  (`pio-out-end`). The program's completion wait (`bch_v1_wait_prog`)
  isn't traced, but the SD log shows its write-back finished (dirty down to
  4 kB, writeback 0).

**Two CPUs from mtd0: 5 of 5 froze (98 s – 14 min). One CPU: 2 h clean.**
Ruled out so far: the camera, the PTE clean, the DDR drain, a lost tick.

### The vendor kernel programs the PJ4B differently

The vendor 3.2 image has its own proc_info entry for this CPU (match
`560f5840`/`ff0ffff0`; ours is MIDR 562f5841) with its own setup function
(at 0xc041ae60, before `__v7_ca9mp_setup`). Mainline matches the same CPU
with `__v7_pj4b_proc_info` and runs `__v7_pj4b_setup`, which was written
for the Armada XP. The two differ in every register they touch:

| Register | Vendor 3.2 (both CPUs) | Mainline `__v7_pj4b_setup` |
|---|---|---|
| Aux Debug Modes 0 (`p15,1,c15,c1,0`) | set bit 12 | set bit 22 (`PJ4B_WFI_WFE`: WFI/WFE serve DVM) |
| Aux Debug Modes 1 (`c15,c1,1`) | clear bit 25 | set 16 (`CLEAN_LINE`), 8 (`INTER_PARITY`); clear 2 (`STATIC_BP`) |
| Aux Debug Modes 2 (`c15,c1,2`) | set 29 (`OUTSDNG_NC`); clear 23 (`FAST_LDR`) | set 25 (`SNOOP_DATA`), 27 (`CWF`), 29, 30 (`L1_REP_RR`); clear 23 |
| Aux Functional Modes 0 (`c15,c2,0`) | clear bit 7 | set 1 (`SMP_CFB`: join the coherency fabric), 2 (`L1_PAR_CHK`), 8 (`BROADCAST_CACHE`) |
| ACTLR (`p15,0,c1,c0,1`) | set bit 6 (SMP); set bit 0 (FW) if ID_MMFR3 says broadcast (it does: 2) | not touched |

- The vendor also reads 0xf8000000 and compares bits 7:4 with 2, but
  nothing uses the result.
- These are the bits that decide how a core joins the coherency fabric,
  snoops, and serves DVM (broadcast TLB/cache maintenance) while it
  idles. Only SMP freezes. That makes this the strongest lead yet, more
  than any one driver.

### Patch 0020 and m1-nandboot-nandvs

`kernel/m1/patches/0020-arm-pj4b-mv61x0-vendor-setup.patch`: the option
`CONFIG_PJ4B_MV61X0_VENDOR_SETUP` (off by default). With it,
`__v7_pj4b_setup` runs the vendor's sequence instruction for instruction
instead of mainline's, on both CPUs: CPU0 at boot, CPU1 from
`secondary_startup` through the same proc_info.

`mach-mv61x0/mv61x0.c` now prints, in every build, each CPU's ACTLR, aux
function 0 and aux debug 0/1/2 at late init:
`mv61x0: cpuN ACTLR ... aux func0 ... dbg0 ... dbg1 ... dbg2 ...
(vendor|mainline PJ4B setup)`. Under any mainline-setup image, these lines
also show what U-Boot/the boot ROM left plus mainline's bits.

`HANGTEST=nandvs` = nandtick (DDR drain on, as stock) + the option. DEBUG
IMAGE: the owner's standing OK for these tests, a RAM boot first, then
mtd0, 2 h.
**Built 2026-11-08, not booted:**
- `m1-nandboot-nandvs.uimg` md5 `1dd5f02cd8bec758b01348cd5291f4d8`
  (2,824,420 bytes);
- modules tar `f7a9453d9cafc22f398719ede3685fd1`.

The config is nandtick's plus the option. The compiled
`__v7_pj4b_setup` (0xc0022dd4) has the vendor's encodings instruction for
instruction (`orr #0x20000000`, `bic #0x2000000`, `bic #0x80`,
`bic #0x800000`, MMFR3 test, ACTLR `orreq #1`, `orr #0x40`).

**Run:** RAM boot, send the two `mv61x0: cpuN ACTLR ...` lines, then mtd0
and 2 h.
- **No freeze:** the CPU setup is the cause. Bisect the five differences
  afterwards (ACTLR SMP/FW against `SMP_CFB`/`BROADCAST_CACHE` first,
  then `WFI_WFE`, `SNOOP_DATA`/`CWF`/`L1_REP_RR`), and make the vendor
  setup the nandboot default.
- **A freeze:** next the SCU setup (the vendor's `scu_enable` against
  mainline's) and the unported PoUIS clean and `BZ_833`/`BZ_664`.

**nandvs's register lines** (RAM boot, both CPUs the same):
`ACTLR 00000041 aux func0 00000132 dbg0 60001100 dbg1 00000927 dbg2 20008208 (vendor PJ4B setup)`.

| Register | Bits set | Of mainline's bits |
|---|---|---|
| ACTLR 0x41 | SMP (6), FW (0) | mainline doesn't write ACTLR |
| aux func0 0x132 | 1, 4, 5, 8 | `SMP_CFB` (1) and `BROADCAST_CACHE` (8) are already on without mainline's code; `L1_PAR_CHK` (2) is off; bit 7 cleared by the vendor |
| aux dbg0 0x60001100 | 8, 12, 29, 30 | `WFI_WFE` (22) is off |
| aux dbg1 0x927 | 0, 1, 2, 5, 8, 11 | `STATIC_BP` (2) stays on (mainline clears it), `INTER_PARITY` (8) is on, `CLEAN_LINE` (16) is off |
| aux dbg2 0x20008208 | 3, 9, 15, 29 | `OUTSDNG_NC` (29) is on; `SNOOP_DATA` (25), `CWF` (27), `L1_REP_RR` (30) are off |

For the mainline values, nandtick was rebuilt with the print: md5
`37dc2feda4ae445273b1ebf760f046fe`, modules
`e231a24c5a8c3b2e0e619645c7da6219`. Its config is unchanged; it
replaces 9586a6d3 in the out directory. A RAM boot to the two
`mv61x0: cpuN` lines is enough, no soak. The most interesting value is
ACTLR: if mainline leaves SMP/FW at 0, the cores may not be coherent the
way the A9-style SCU expects.

## Hang 14: nandvs froze in 60 s; the vendor CPU setup is ruled out (2026-11-08)

nandvs (1dd5f02c, the vendor PJ4B setup; both CPUs read ACTLR 0x41,
func0 0x132, dbg0 0x60001100, dbg1 0x927, dbg2 0x20008208 from mtd0 as
well) froze at 60.04 s, five seconds into TAR 0, silent as before.
- **The ring:** cpu0 issued a read (`cmd` page 0x310f1, `rdd`), went idle
  (last sample `do_idle`, 4 ms before), and its ISR entry
  (`isr 00001802`) is the last step. That's the same ending as hangs 11
  and 12.
- **cpu1's last sample:** `folio_add_file_rmap_ptes+0x38`, inside an
  atomic (`arch_atomic_add_return_relaxed`), in fault-around. The one
  before was `folio_trylock` from `next_uptodate_folio`.

**Two CPUs from mtd0: 6 of 6 froze (60 s – 14 min).**
- Ruled out: the camera, the PTE clean, the DDR drain, a lost tick, the
  vendor PJ4B setup.
- In 3 runs the ring ends at a read's ISR entry (11, 12, 14). In 3 the
  NAND was idle (9, 10, 13).
- **In all 6, one CPU's last sample is in the page-fault fault-around
  path:** `filemap_map_pages`, `next_uptodate_folio`, `set_pte_range`,
  `set_ptes`, `folio_add_file_rmap_ptes`, `xas_next_entry`,
  `lock_vma_under_rcu`.

### Fault-around: the one thing the vendor kernel never ran

Fault-around (`do_fault_around`) came in Linux 3.15; the vendor kernel is
3.2. Per file fault it maps up to 16 page-cache pages at once. That's a
burst of folio lock/refcount/mapcount atomics (`ldrex`/`strex`), up to 16
PTE writes, and `__sync_icache_dcache` (hang 12's lr), i.e. a D-cache
clean and an I-cache invalidate that the hardware broadcasts to the other
core (MMFR3 MaintBcst 2, ACTLR FW).
- On the NAND root, every one of those pages was just written by the CPU
  (PIO from NDDB, then memcpy). Its lines are dirty in one core's L1 when
  the other core maps and runs it.
- On the card root, SDHCI DMA filled the pages, and the lines aren't in
  any cache.

**Patch 0021** (`mm/memory.c`, only with `CONFIG_ARCH_MV61X0`):
`memory.fault_around_pages`, a module parameter (0644; 1 = off, or a
power of two; 16 is the default) to replace the debugfs file we don't
build. It can be switched at run time in
`/sys/module/memory/parameters/fault_around_pages`.

**`HANGTEST=nandfa`** = nandtick (mainline PJ4B setup, drain on) with
`memory.fault_around_pages=1`. **Built 2026-11-08, not booted:**
- `m1-nandboot-nandfa.uimg` md5 `fd2eb360153311e9fda7164c125b7b8e`
  (2,824,388 bytes);
- modules tar `7126f652f370c6ba038f3f677cc8d4f7`.

The boot also prints both CPUs' PJ4B registers under the *mainline*
setup: that's the comparison wanted after hang 13.

**Run:** RAM boot, check `cat /sys/module/memory/parameters/fault_around_pages`
→ 1, then mtd0, 2 h.
- **No freeze:** fault-around's pattern is the trigger. Then turn it back
  to 16 in the same boot and see whether the freeze returns. A fix could
  keep fault-around off on this SoC, or find which part of it matters
  (the I/D-cache sync of CPU-written pages first).
- **A freeze:** the trigger is the page-cache/fault path in general.
  Next: the **card-root SMP soak with this same image** (no build). If the
  card root also freezes with two CPUs, it isn't the NAND root at all.
  If it doesn't, the CPU-filled (PIO) pages are the key, and the cache
  maintenance of dirty lines across the cores is where to look.

### Correction: the vendor PJ4B setup was in every build (patch 0001)

nandfa (mainline-labelled) printed the same registers as nandvs:
`ACTLR 00000041 aux func0 00000132 dbg0 60001100 dbg1 00000927 dbg2 20008208`
on both CPUs.
- **The reason:** patch 0001 (from the first bring-up) already adds
  `__v7_pj4bmp_proc_info`, which matches this CPU (`560f5840`/`ff0ffff0`)
  before mainline's `__v7_pj4b_proc_info`. Its `__v7_pj4bmp_setup` is the
  vendor's sequence, ACTLR SMP/FW included.
- **So mainline's Armada XP `__v7_pj4b_setup` has never run on this
  board.** Patch 0020 only changed that dead path, and nandvs was in
  effect a rerun of nandtick. I missed 0001 when I compared; the hang 13
  table above compares the vendor code with mainline's dead path, not
  with what ran.
- **What hang 14 does show:** with the vendor's CPU register state (as
  in every run so far), two CPUs freeze. The CPU setup doesn't differ
  from the vendor's, so it isn't a candidate.
- **Removed:** patch 0020, `CONFIG_PJ4B_MV61X0_VENDOR_SETUP` and the
  nandvs variant. The register print stays, without the
  "vendor/mainline" label.

## Hang 15: nandfa froze in 70 s; fault-around is ruled out (2026-11-08)

nandfa (fd2eb360, `fault_around_pages` 1, checked on the running system)
from mtd0 froze at 69.64 s, 15 s into TAR 0, silent as before.
- **The ring ends at a read's ISR entry** (`isr 00001802`, all on cpu0),
  as in hangs 11, 12 and 14. **That's 4 of 7 two-CPU runs.**
- **The last samples:**
  - cpu0: `wake_up_new_task` (a fork), after a PIO read;
  - cpu1: VMA code (`vma_iter_store_overwrite`, `vma_complete`; before
    that `do_wp_page`, `unmap_vmas`).

  So the other CPU is in mm code in general (fork, COW, exec teardown),
  not in fault-around in particular.

**Ruled out with two CPUs:** the camera, the PTE clean, the DDR drain, a
lost tick, fault-around. The CPU setup is the vendor's in every build.

**Next, no build: the card-root two-CPU soak with nandfa** (UBI not
attached, so after the boot reads nothing touches the NAND controller).
- **It freezes:** NAND isn't needed. It's an SMP problem of the SoC under
  this kernel's load: look at the SCU/GIC setup against the vendor's, and
  at the unported PoUIS clean and `BZ_833`/`BZ_664`.
- **No freeze in 2 h:** NAND is needed. Then the original test 1: card
  root, UBI attached, the same read soak on an mtd6 mount. It separates
  NAND controller traffic (with executables still from SD) from running
  from NAND. Then a build that traces the ISR step by step (`isr` after
  each of its NDCR read, NDCR write and `complete()`), since 4 of 7 runs
  stop right there.

## Hang 16: the card root freezes too (2026-11-08)

nandfa (fd2eb360) from mtd0 on the **card root** (`/dev/mmcblk0p1`, UBI
detached, NAND untouched after its boot reads at 9.4 s) froze at 105.7 s,
51 s into TAR 0, silent as before.
- **The last samples:**
  - cpu0: user mode, after `folio_wake_bit`;
  - cpu1: `pcpu_alloc_noprof`, after `ehci_urb_enqueue` (USB host
    submission).
- **Two CPUs: 8 of 8 froze, NAND or card root. One CPU: 2 h clean.**
  - The NAND root isn't needed, and neither is NAND traffic.
  - Rings ending at the NAND ISR (4 of 7) only showed that NAND reads are
    the busiest I/O on the NAND root.
- **But the card-root soaks of 11-06/07** (5b17e2ec, dc3b5f20: no trace,
  sampler, tick check or ramoops) ran 82–84 min clean. The debug images
  now freeze in 60 s – 14 min. If that rate had held, 84 min clean would
  have odds of e^−6 or less. **So something added since raises the rate
  sharply.** On the NAND root it was the same: dc3b5f20 hung after 20–30
  min, nanddbg in 20–70 s.

What the debug images add, beside code that's inert without its
parameter:
- the NAND trace (inert on the card root);
- ramoops/pstore, with the 2 MB no-map pair at 0x1e000000;
- the hang watchdog;
- since nandpcs, the 10 ms sampler on both CPUs;
- since nandtick, the timer-3 tick check.

**`HANGTEST=nandwdt`** = the plain nandboot image (all patches, at their
defaults) plus only `timer_mv61x0.hang_wdt=30`: no trace, sampler, tick
check, ramoops or reserved areas. Against dc3b5f20 it adds `rdd_irq` (on
by default since 0016) and code that's inert without its parameter.
**Built 2026-11-08, not booted:**
- `m1-nandboot-nandwdt.uimg` md5 `cf897cd804ba26e9857d242ec6ea8808`
  (2,813,868 bytes);
- modules tar `d7bd2ee2ea1208c30bf2b86a03bd1d76`.

**Run on the card root** (the same setup as hang 16, a direct A/B), 2 h.
It has no ring, samples or pstore, so a freeze shows only as ping/probe
loss and the reset.
- **It freezes:** the debug additions aren't the cause. Compare the
  configs of 5b17e2ec/dc3b5f20 with today's, and rerun dc3b5f20 itself
  longer: the 84 min may have been luck.
- **No freeze:** one of the additions raises the rate. Add them back one
  at a time: ramoops with its reserved areas first (common to every fast
  freezer since nanddbg), then the sampler, then the tick check.

## nandwdt: two CPUs, card root, 2 h clean (2026-11-08)

nandwdt (cf897cd8: the plain image plus the hang watchdog), from mtd0,
card root, camera on, **Wi-Fi up and associated**:
- 12 full passes in 7682 s;
- no reset, oops, lockup or mmc error;
- the probe answered throughout;
- ping lost 32 of ~7640, at most 3 in a row, in clusters every ~20 min
  (most likely Wi-Fi rekeys; the probe never missed).

The same setup froze in 106 s with nandfa (hang 16). **So the debug
additions raise the freeze rate a lot; two CPUs with Wi-Fi up aren't
enough on their own in 2 h.**

**Next, the owner's test (no build): nandfa on the card root with
mwifiex blacklisted**, everything else as in hang 16, camera included.
- The 11-06/07 clean card-root runs had the old mwifiex_usb (before
  0013), which often didn't bring the adapter up, so Wi-Fi may not have
  run in them.
- Hang 16's cpu1 was in `ehci_urb_enqueue`.
- **A freeze:** Wi-Fi isn't needed. Go on adding back the debug pieces to
  nandwdt.
- **2 h clean:** Wi-Fi/USB traffic is part of the trigger, and the debug
  pieces make it fire sooner. Then find which piece, with Wi-Fi on.

**Add-back step 1, built for either outcome: `HANGTEST=nandram`** =
nandwdt + ramoops/pstore and nanddbg's two no-map 1 MB areas at
0x1e000000. No `trace_phys`, so no trace, sampler or tick check. The
config differs from nandwdt's only by PSTORE (and REED_SOLOMON for its
ECC). **Built 2026-11-08, not booted:**
- `m1-nandboot-nandram.uimg` md5 `e2fb8c988db1687c88228f471bfefa62`
  (2,823,812 bytes);
- modules tar `39cf9a1aab0031a38dbc1f13bd24a6d8`.

After it, if it's clean: nandram + `trace_phys` (the trace ring, inert
on the card root, and with it the sampler and the tick check), then each
of those switched off at run time (`pcs_ms=0`).

## Hang 17: no Wi-Fi, card root, still freezes (2026-11-08)

nandfa from mtd0 on the card root with no mwifiex loaded (no `mlan0`),
camera streaming, froze at ~329.1 s, 74 s into TAR 0, silent as before.
**So Wi-Fi isn't needed.**
- **The last samples**, both at 329.13 s:
  - cpu0: `sdhci_request_done+0x178`, the SD host's request completion;
  - cpu1: `xas_load`, a page-cache lookup (after `arm_copy_to_user`).
- **The shape matches the NAND root:** one CPU in the storage I/O
  completion (the SDHCI done path here, the NFC ISR in hangs 11, 12, 14,
  15), the other in page-cache/mm code.
- The ring and sample counters started again at "boot 1". The nandwdt
  boots in between have no reserved areas, so Linux used that RAM and
  the magic was gone. Nothing to fix.

**Tally:**
- **Debug builds, two CPUs:** 9 of 9 froze, NAND or card root, with or
  without Wi-Fi or the camera.
- **nandwdt** (plain + watchdog, two CPUs, card root) and **nandup** (one
  CPU, NAND root): 2 h clean each.

**Next: nandram** (e2fb8c98, add-back step 1: ramoops/pstore and the
reserved areas), on the card root with Wi-Fi on as in the nandwdt run,
2 h.

## Hang 18: ramoops and its reserved areas bring the freeze back (2026-11-08)

nandram (e2fb8c98: nandwdt + ramoops/pstore and the two no-map 1 MB
areas at 0x1e000000) froze at ~175 s on the card root, two CPUs, Wi-Fi
and camera on. That's the setup in which nandwdt ran 2 h clean. pstore's
console from the frozen boot ends at 115.96 s (a mwifiex `CMD_RESP`
line), 60 s before the freeze.

| Build | Same setup, two CPUs, card root | Result |
|---|---|---|
| nandwdt | plain + hang watchdog | 2 h clean |
| nandram | + ramoops/pstore + the two no-map areas | froze at 175 s |

Every fast freezer since nanddbg has had both.

Two splits, both built:
- **(a) `HANGTEST=nandres`:** nandwdt with the two no-map areas reserved
  in the DT, but no PSTORE. Nothing maps or writes them, only the memory
  map has the 2 MB hole.
  - `m1-nandboot-nandres.uimg` md5 `70bcc0cf9da578387d740a2627af0e95`
    (2,814,388 bytes);
  - modules `78de482955bc62e9019b86e0b050fb00`.
- **(b) `HANGTEST=nandrnc`:** nandram with ramoops' `console-size` and
  `pmsg-size` 0. ramoops still maps its area (`ioremap_wc`: Normal
  non-cacheable), and its ECC and dmesg zones get set up at boot, but
  nothing writes there while the system runs (only on a panic or oops).
  - `m1-nandboot-nandrnc.uimg` md5 `4cdb167620e6116de9c038bcb115f3fe`
    (2,823,596 bytes);
  - modules `46bed1f17c9c59b0076b5ffb7718bfd2`.

Both DTBs were checked (`dtc -I dtb`): the same `reg`/`no-map`, and the
console and pmsg sizes as described.

**Order:** (a) first, the same setup, 2 h.
- **It freezes:** the hole in the memory map (or the layout shift it
  causes) is enough. Next, (c): the areas moved elsewhere in DDR, and a
  hole of the same size with nothing reserved at 0x1e000000.
- **No freeze:** it's ramoops. (b) then tells whether its run-time
  console writes matter, or just its mapping and setup.

The pstore console ending 60 s before the freeze already argues against
the writes alone.
