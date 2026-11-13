# DP200 - larger projects and decisions

One entry per project: goal, status, the decisions that stand, what is
next, and where the detail lives. Day-to-day open items are in
[TODO.md](TODO.md); the state of the printers is in
[docs/STATUS.md](docs/STATUS.md). Keep entries short: background and
options that were weighed go to `docs/history/` (the earlier, longer
version of this file is
[docs/history/PROJECTS_archive_2026-11-13.md](docs/history/PROJECTS_archive_2026-11-13.md)).
The numbers are stable; other documents refer to them.

**Rules for anyone picking one up:**
- No heat and no motion unless the owner is at the printer and agreed.
- Never write the NAND, the cartridge chip or the user's `printer.cfg`
  without the owner's OK. NAND rules: [docs/nand_layout.md](docs/nand_layout.md).
- Downloaded files are untrusted: own directory, read with `python -I`.
- Where to write things down: [docs/README.md](docs/README.md).

| # | Project | Status |
|---|---|---|
| 1 | Kernel | Mainline 6.18 runs on the dev printer from NAND; work printer on stock 3.2 |
| 2 | SD-card boot by DIP switch | Low priority, after the release |
| 3 | Internal NAND install | USB stick install done; end-goal stages 1-5 of 9 done |
| 4 | Object-on-bed camera check | Planned, not started |
| 5 | Faster stepping | Done 2026-11-03 |
| 6 | Other Sindoh models | Research; firmware decrypted except the 30X |
| 7 | Spaghetti / failure detection | Idea: document an external host |
| 8 | Cartridge chip read/write | Low priority; read-only so far |
| 9 | JTAG | Parked |
| 10 | Before a release | Open: features, Wi-Fi priority |
| 11 | G-code and log storage | Decided; to build with the end-goal install |
| 12 | Wi-Fi chip firmware study | Low priority; a side session has started |

---

## 1. Kernel

**Goal:** get past the vendor 3.2 kernel's limits (no Thumb, so Debian
armel; no swap, no devtmpfs, no USB CDC-ACM).

**Status:**
- **Mainline 6.18.59 with our device tree and drivers runs on the dev
  printer from NAND**: two CPUs, NAND root, Wi-Fi, motion (2026-11-12).
  No vendor source was needed: [docs/no_gpl_plan.md](docs/no_gpl_plan.md).
  The two-CPU freeze and its fix:
  [docs/kernel/smp_freeze_summary.md](docs/kernel/smp_freeze_summary.md).
- **Modules for the stock 3.2 kernel** can be built without Marvell's SDK
  (`install/kernel_modules/`): `cdc-acm.ko` loads and a USB accelerometer
  appears as /dev/ttyACM0 (2026-10-30). The same recipe works for other
  missing modules (ch341, cp210x).
- The GPL source request to Sindoh/Marvell was drafted and not sent; the
  main path no longer needs it.

**Decision:** the work printer and the USB stick stay on stock 3.2 until
the end-goal install (#3).

**Next:** the kernel items in TODO; then #3.

## 2. SD-card boot (low priority: after the end-goal release)

**Goal (owner, 2026-11-03):** boot from the SD card by the DIP switch,
without the NAND: a recovery path for a fully corrupted NAND.

**Status** ([docs/sd_boot_plan.md](docs/sd_boot_plan.md)): U-Boot from
NAND reads the card once two SD pin selects are set (RAM only) and boots
our kernel from raw card sectors (`tools/sd_raw_boot.sh`); that is how new
kernels are RAM-booted. The DIP-switch boot (the boot ROM loading U-Boot
from the card) hangs silently. Open lead: the SD pad settings the ROM uses
in mode 6.

**Decision:** not the daily boot path; that is our kernel in mtd0.

**Later option it would open:** merging mtd5 + mtd6 (about 330 MB free
instead of about 150). It needs the recovery set saved to the user's stick
first, and a recovery card for the way back. The numbers and conditions
are in the archive, section 2.

## 3. Internal NAND install (stock printers have no SD card)

**Goal:** install from a USB stick, with no added hardware, revertible to
stock.

**Status:**
- **USB stick install: done 2026-11-02**
  ([docs/usb_installer.md](docs/usb_installer.md)): our runtime in
  `/klipper` on the stock root (mtd6) under the stock 3.2 kernel. Install,
  upgrade, cancel and remove are tested on both printers.
- **End goal** (our kernel in mtd0, our root in mtd6, mtd5 untouched):
  [docs/end_goal_install_plan.md](docs/end_goal_install_plan.md). All 9
  stages were approved 2026-11-03. Stages 1-5 are done on the dev printer.

**Decisions:**
- No U-Boot or environment change. mtd5 (the factory recovery set) is
  never written.
- **Revert = plug in a Sindoh update stick** (2026-11-03): our system
  restores stock from mtd5, then Sindoh's update runs
  ([docs/kernel/revert_to_stock_plan.md](docs/kernel/revert_to_stock_plan.md)).
- No per-printer backup is required: karas.db rebuilds from mtd4.
- Accepted risk: a power cut during the mtd0 write needs the serial
  console, as with Sindoh's own updates.

**Next:** stage 6, installer v2 (TODO).

## 4. Object-on-bed check with the camera

**Goal:** before a print, warn or stop if something is still on the bed.

**Plan:** lamp on, a snapshot from ustreamer, compare it with a reference
of the empty bed in a small Klipper extra. PRINT_START stops and the
screen offers CONTINUE / CANCEL.

**Constraint (2026-10-28):** the check must run before G28, because Z
homes upward. So prints, cancels and the dryer end with the bed at a known
pose (bottom, fixed Y), saved in save_variables, and the check runs at
that pose. For an unknown pose: find the plate's edges in the picture, or
ask on the screen.

**Needs the owner for:** the pose, the reference picture, and tests with
real leftovers (thin first layers are the hard case).

Until it exists, BED_CLEAR asks before every Z homing.

## 5. Faster stepping in the UPC firmware

**Done 2026-11-03**
([docs/faster_stepping_plan.md](docs/faster_stepping_plan.md)):
`CONFIG_UPC_STEP_BATCH` (constant-rate blocks as engine moves) is the
default. A batching bug found on the work printer was fixed in the fork
(8d4fb4d8, 2026-11-06). The UPC load shows in Mainsail's MCU panel since
2026-11-09.

**Open:** what step-engine registers +0x10 / +0x14 / +0x2c mean (the
values are copied from the stock app).

## 6. Other Sindoh models

**Goal:** the same port on the 3DWOX 1X, 2X (dual extruder) and 30X.

**Status:** [docs/other_models.md](docs/other_models.md). The OEM firmware
is decrypted for all models except the 30X (key unknown).

**Next:** 1X testing; the second extruder of the 2X; the 30X key.

Note (owner, 2026-11-06): the 1X shows a shutdown screen on a long press
of the power button. Look in its firmware for how it does that.

## 7. Spaghetti / failure detection

Not on the printer (CPU and RAM). To do: document how a separate host
running Obico or similar watches this printer through its Moonraker.

## 8. Cartridge chip read/write (low priority)

Independent of everything else: never wait on it unless the owner makes it
the current task. Read-only so far
([docs/cartridge_chip.md](docs/cartridge_chip.md)). Any write, such as
resetting the remaining length, needs the owner's explicit OK. The
cartridge sensing does not work on the dev printer, so a "no cartridge"
reading there means nothing.

## 9. JTAG

The CN3 header is prepared; no TAP answered (likely fused off).
[docs/jtag_prep.md](docs/jtag_prep.md). Parked.

## 10. Before a release

**Decisions:**
- **The first public release is the USB stick install** (stock kernel,
  `/klipper` on mtd6), but not yet: the screen app and features are still
  being refined (owner, 2026-11-03). The end-goal install is a later
  release.
- **Updates (2026-11-03):** NAND only: Mainsail and Moonraker from
  upstream, Klipper (host and UPC firmware) from our releases. With a
  storage card: everything from upstream, built on the card and copied to
  NAND (#11). Our Klipper fork is public, so anyone can build the images.
  The options that were weighed are in the archive, section 10.
- The root stays **armel** through the end-goal release, so the stick
  install and our kernel share one root (owner, 2026-11-06).
- Never publish a payload that contains Wi-Fi networks, or Marvell or
  Sindoh images.

**Open before a release:** the saved-network priority bug (TODO); the next
payload with the 2026-11-12 fixes, and a real print on it; the release
checklist itself, which is still to be written.

## 11. G-code and log storage

**Problem:** long prints are 15-200 MB of G-code, and NAND has about
140 MB free with our root. The microSD slot is inside the case.

**Decided 2026-11-03: optional storage, in tiers.** No card is needed to
install.
- **NAND only:** managed G-code space (refuse uploads that don't fit,
  delete the oldest finished jobs, show the free space), logs in RAM.
- **SD card inside, or a USB stick:** G-code and logs on it, full upstream
  updates, timelapse, swap, backups. The screen offers to format one.
- **The card is storage, never the root** (owner, 2026-11-07). mtd6 is
  always the root, so a dead or pulled card can't stop the boot. The
  `/.dp200-root` marker (a card that is the system) is for development
  and recovery only; storage gets its own marker.
- **Updates with a card (direction set 2026-11-07, to discuss again):**
  build on the card, copy the result into NAND, keep the previous version
  until the new one starts. Open: A/B space, how a pending deploy is
  shown, rollback.

**Next:** build it with the end-goal install. The alternatives that were
considered (NFS, a separate host) are in the archive, section 11.

## 12. Wi-Fi chip firmware: decompile / clean-room rewrite (low priority)

The owner's idea (2026-11-07): take apart the 88W8782's firmware and maybe
write a clean-room replacement. It is a "fun path", not a fix for
anything: the boot and reload failures were in the host driver and are
solved ([docs/kernel/wifi_88w8782.md](docs/kernel/wifi_88w8782.md)).

**Status:** a side session on the build box has started on the decompile.
- It covers only the 8782; other DP200 batches may have another module.
- A decompile for understanding is the realistic first step. A full
  rewrite (RTOS, 802.11 MAC, radio calibration) is a research project.
- Nothing from the vendor binary gets published.
