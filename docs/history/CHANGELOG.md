# Changelog

Newest first. One or two lines per item, with the commit where there is
one. The detail for everything up to 2026-11-12 is in
[TODO_archive_2026-11-12.md](TODO_archive_2026-11-12.md) and the other
files in this folder; `git log` has the rest.

## 2026-11-14
- **Camera streamer: log and auto-restart** (`rc.dp200 webcam-loop`),
  after it died on the dev printer with no trace. Deployed there (rc.dp200
  9a605e09, old one kept as rc.dp200.bak-1114); a test kill was logged as
  exit 139 and the stream was back in 5 s. Temporary, until the cause is
  found (TODO 26a).
- **Wi-Fi fallback traced** (TODO 26): the Niholedotcom access point
  drops the printer 91 s after each association (reason 34); the
  switch-back watchdog reads stale scan results. Not fixed.

## 2026-11-13
- **Fork branch `dp200-clean` built** (stepping session; emulator-tested
  only). A: 25 commits reshaped into 9, diff against 289952f9 empty. B:
  rebased onto upstream 29d4ec2d, no conflicts, kemu regression passes.
  C: 8 commits; `stepper.c`/`sched.c` carry generic hooks
  (HAVE_STEPPER_HW_PULSE, HAVE_STEPPER_HW_BURST, HAVE_IRQ_WAIT_TIMERS)
  instead of UPC `#if`s, test configs and reference docs added; step
  timing identical to B on 11 inputs. No sign-off lines.
- **Klipper fork tidied, one home per file.** Fork: `fast-stepping`
  deleted (fully contained in `sindoh-dp200`), `master` synced to upstream
  29d4ec2d, the printer configs removed from it (da0660ea, 289952f9). Port
  repo: the copies of `src/upc`, the host modules, the build configs,
  `install_port.sh`, `make_fork.sh` and `patches/` removed; builds check
  out the pinned fork (`klipper/FORK`, `get_fork.sh`); `tools/fork_check.sh`
  guards against drift; rules in `klipper/README.md`. The UPC load change's
  sched.c half was already in the fork (5194e292).
- **PROJECTS.md cut to status + decisions** (287 -> ~200 lines with a
  status table); the long version is PROJECTS_archive_2026-11-13.md.

## 2026-11-12
- **Docs reorganised:** TODO.md is open items only; STATUS.md, this
  changelog, docs/README.md (map + rules), nand_layout.md; history moved
  to docs/history/.
- **Motor fix in mtd0 (dev printer).** No holding torque on nandboot since
  11-09: GPIO bank 3 was left as U-Boot sets it. The mv61x0-upc driver now
  sets it at probe (motor repo 7dd0f21). Image `m1-nandboot-bank3`
  7eae8600: RAM-boot pass, written to mtd0 with the owner's OK, boots from
  NAND, X/Y hold and home (c2eb875).
- **Prime line moved to the front edge, Y 0** (61d219b). Probe map: the
  plate is flat to Y -2, edge at Y ~-3. Full test print passed.
- **Paused-print safety:** LOAD/UNLOAD/CLEAN never raise the bed while
  paused (d2565c7), home only X/Y and never Z (4e85d0a); Y homing moves off
  a pressed switch first (54a8e5b).
- **LOAD jam check** (encoder must keep moving), nozzle target restored
  after load/unload, new `EMPTY_BIN` (d2565c7). Empty-inlet test passed.
- **RESUME re-primes** after a load or a cooled nozzle; the idle timeout no
  longer drops the motors during a pause (ee7896e). Pause test passed:
  pause, unload, load, empty bin, resume, print finished.
- **PRINT_START "starting" state** (ad60eaa) so the screen shows
  "Starting print", not PRINT PAUSED.
- **Screen app** (6247365, f5113d1, 2831970, 494918a, bb965a6, 72bfe38,
  0cc6a77): HOME while paused, load running/error pages, EMPTY BIN page,
  custom MACROS page, starting-print checklist.
- **Wi-Fi 6 h soak passed** on C3 + 0028: 513 cycles, 103/103 downloads,
  3.2 % ping loss, no disconnect (c595cc1). Upstream submission of the 8782
  fix tabled by the owner (0b86b42).

## 2026-11-11
- **Two-CPU freeze FIXED by candidate 3** (every barrier `dsb sy`, patch
  0025, on top of the erratum-6011 IRQ window and clrex): first clean 10 h
  two-CPU NAND-root soak. C3 `a4e0cb33` written to mtd0 (b0c3a8c);
  maxcpus=1 gone.
- **Wi-Fi reload fixed:** unbind = FUNC_SHUTDOWN then USB reset (0027/0028,
  5d3d2c1, f8d890f); 0028 installed, 10/10 warm boots (e0e003b). Part C:
  the unread INIT_DONE was the boot failure; the probe is optional
  (6352e4c). Rule: never reset an 8782 whose last load failed.

## 2026-11-08 to 11-10
- The freeze hunt: hang tests nandps3/4, nanddrv, nanddrv2, nandupw;
  one-CPU default in mtd0 as a stopgap (1fd266d); candidate 1 alone fails
  (eb67b78). UPC load now visible in Mainsail's MCU panel (0b9e4d2).
- 11-09: no motion on nandboot found while mapping the front edge (23efdc9).

## 2026-11-06 to 11-07
- **End-goal stages 1-5 done on the dev printer:** mtd0 kernel area
  rewritten from our kernel, mtd6 revert from mtd5, then our kernel
  (errata build) in mtd0 and our UBIFS root in mtd6; NAND-only boot works.
- Back-to-stock popup and hold prompt in the screen app (e288896, 3433ac5).
- Work printer's failed print diagnosed: UPC_STEP_BATCH bug, fixed in fork
  8d4fb4d8. Payload 5f3336e1 built (no Wi-Fi networks in it).
- Hard hangs 1-11 on the NAND root recorded (kernel/nandboot_hang_analysis.md).

## 2026-11-01 to 11-04
- **USB installer:** Klipper on the stock root (mtd6) under the stock 3.2
  kernel; install, upgrade, cancel, remove tested (f20fcce, f5991c3).
- **Faster stepping:** UPC_STEP_BATCH is the default (050e233); cube
  20.0 / 19.9 / 20.3 mm.
- Plans reconciled 11-03: end-goal sequence approved, update and storage
  decisions (31d9916). Homing at stock speeds. Shutdown screen (851c330).

## 2026-10-29 to 10-31
- **Mainline 6.18 milestone:** Klipper, Moonraker, Mainsail and the webcam
  run from the Debian root (9ee9b8d); touch, RTC, Wi-Fi, Ethernet work.
- **NAND write path** in the mainline driver with the write guard
  (c156adf, 9d81790, bb876e5). Correction: mtd5 is the factory recovery
  set (8b20df2). Fast RAM boot from raw SD sectors (7a6217f).

## 2026-10-18 to 10-28
- First bring-up on the stock 3.2 kernel: UPC probe, Klipper firmware on
  both UPC cores, Debian chroot on microSD, first motion, heating and
  prints. Initial import 10-20 (ded3471).
- Touch screen app, Wi-Fi setup, bed level page, filament dryer, stock
  load/unload/clean routines as macros, levelling probe.
- 10-28: a part was crushed by Z homing; BED_CLEAR before every Z homing
  since (a762802).
- JTAG (no TAP found on CN3), SD boot and rescue card investigations.
