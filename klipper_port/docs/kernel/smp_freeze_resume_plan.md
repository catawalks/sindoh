# SMP freeze: where it stands and the plan to resume (2026-11-09)

**Superseded 2026-11-11:** the freeze is fixed and the default nandboot runs two CPUs again (smp_freeze_summary.md, "The fix"). The plan below is kept as history.

From the kernel analysis side session. The full record is in
docs/kernel/nandboot_hang_analysis.md (hangs 4–25 and the splits after them).

## Facts

- **Two CPUs:** a silent hard freeze. Both CPUs, ping, UART and the tick
  check stop together, and the timer-0 watchdog resets the board. It
  happens on the NAND root and on the card root, with or without Wi-Fi
  or the camera.
- **One CPU** (`maxcpus=1`): clean. nandup ran 2 h, nandupw 10 h. mtd0
  now holds the default 0bcb101e with maxcpus=1.
- **Base rate, plain kernel, two CPUs:** roughly one freeze per 1–3 h on
  the card root (nandsz at 49 min; nandwdt, nandres, nandpad, nandpad2,
  nandps2, nandrs, nandps4, nanddrv and nanddrv2 ran 45 min – 2 h clean).
  On the NAND root it was about 20–30 min (dc3b5f20).
- **Fast reproducer (20 s – 7 min):** `platform_driver_register(&ramoops_driver)`
  at postcore, even with no device to bind (nandps3 237dde13, 2 of 2),
  or the real ramoops probe (nandram and others). Not reproduced by: a
  generic dummy driver, a "ramoops"-named dummy whose probe fails, image
  size, kernel layout (padded to nandps0's addresses), Reed-Solomon, or
  pstore's fs registration.
- **Ruled out as the fix:**
  - PTE cleaning;
  - the DDR drain (`mc_drain=0`);
  - fault-around off;
  - the PJ4B aux setup (patch 0001 already runs the vendor's sequence:
    ACTLR 0x41, func0 0x132, dbg0 0x60001100, dbg1 0x927,
    dbg2 0x20008208);
  - interrupt-driven NAND reads;
  - the camera;
  - Wi-Fi.
- **The last samples** always have one CPU in mm/page-cache code
  (fault-around, VMA, set_ptes, atomics) and the other in I/O completion
  (NFC ISR or sdhci_request_done) or idle.

## Plan when usage resets (after 2026-11-13 19:00 UTC)

1. **Use nandps3 (237dde13) as the reproducer**, RAM boot, card root,
   45 min. It freezes in minutes, so each candidate fix costs one short
   run.
2. **Candidate fixes still untested**, cheapest first:
   - the vendor's SCU setup, compared with mainline's `scu_enable`;
   - the vendor's `v7_clean_dcache_to_PoUIS` (unported);
   - the `BZ_833`/`BZ_664` options (identify them in the vendor image
     first);
   - `ARM_ERRATA_*` that apply to A9-style SCUs: 764369 (SMP data-cache
     maintenance), 775420, and the SCU/GIC ones;
   - `CPU_IDLE`/WFI: `idle_poll=1` (patch 0018) on nandps3;
   - the exclusive-monitor work (6011) checked against the vendor's full
     list, e.g. the kuser helpers and the futex/cmpxchg64 paths.
3. **A fix that survives nandps3 for 45 min** then needs long soaks on the
   plain kernel (≥ 2 h on the card root, the NAND root overnight) before
   it replaces maxcpus=1.

## Update 2026-11-09

- **nandwdt (cf897cd8, plain + watchdog, two CPUs) on the NAND root**,
  RAM boot from the gap: froze at about 20 min. On the card root it had
  run 2 h clean. So **the NAND root raises the plain kernel's rate** to
  dc3b5f20's 20–30 min. That makes it the long-soak reproducer for the
  plain kernel, besides nandps3 as the fast one.
- **Open (owner):** the boot source. nandpcs ran 3 h 56 min clean from
  the gap and froze in 143 s from mtd0. Queued: a nandpcs gap rerun and a
  nandsz card-root rerun.
