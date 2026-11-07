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
