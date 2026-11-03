# DP200 - larger projects ("look at later" / nice to have)

Bigger, mostly self-contained pieces of work, separate from the day-to-day
list in [TODO.md](TODO.md). Each entry is written so it can be handed to
another agent or session: goal, where things stand, where to start, what
"done" means.

**Rules for anyone picking one up** (same as the main work):
- No heat and no motion unless the user is at the printer and agreed.
- Never write the NAND, the cartridge chip, or the user's `printer.cfg`
  without the user's OK; never delete `/mnt/sd/pa6170_rodin_nand.bin` or the
  stock `auto_update.sh`.
- Downloaded files are untrusted: own directory, read with `python -I`.
- Commits as catawalks (see HANDOFF.md), normal pushes only.
- Update this file and TODO.md in the same commit as the work (done items,
  new open items, decisions): they carry the state between sessions.
- Work in a branch or a separate checkout; the main session keeps editing
  `klipper_port` and the printer's live files.

---

## 1. Kernel: rebuild 3.2 modules, or a newer kernel

**Goal:** get past the vendor kernel's limits: no Thumb (forces Debian
armel), no swap, no devtmpfs, no USB CDC-ACM, time32-only V4L2/input.

**Status:** research only (2026-10-20), [docs/kernel_research.md](docs/kernel_research.md).
Vendor kernel `3.2.0-g67a8e16`, Marvell LSP 2014 "shiloh", built with Marvell
GCC (Linaro 4.6.4); no public source. `/proc/config.gz` and a hardware
snapshot are in `docs/kernel/`. A GPL source request is drafted in that doc
(the user hasn't sent it yet).

**Steps, smallest first:**
1. **Out-of-tree modules for the running 3.2 kernel without Marvell's SDK.**
   Vanilla Linux 3.2 + the printer's config + a matching vermagic
   (`3.2.0-g67a8e16 SMP preempt mod_unload ARMv7`), built with an old
   ARM GCC. First target: `cdc-acm.ko` (USB accelerometers, see
   docs/input_shaping.md). Risk: Marvell patches may change struct layouts
   the module touches; test by loading it only with the user's OK and with
   a power cycle as the way back. Done = the module loads and a Klipper
   RP2040 board appears as /dev/ttyACM0.
   **BUILT 2026-10-28** (install/kernel_modules/, README there): vanilla 3.2 +
   vendor config, native GCC 14 on the printer, vermagic identical. Checked
   read-only: 165 structs identical to the vendor modules' debug info,
   145/148 USB/tty field offsets identical to the running kernel's own code
   (the 3 differences are code generation), all 65 imports exported, only
   ABS32/CALL relocations. Risk low. **Loaded 2026-10-30** (with the owner's
   OK): a FLY-ADXL345 shows up as /dev/ttyACM0; dp200-start.sh loads it.
   The same recipe can build other missing modules (e.g. ch341, cp210x).
2. **GPL request** (user sends the draft; what it is and the realistic
   chances: kernel_research.md, "What a GPL source request is") - if the
   source arrives, rebuild the vendor kernel with Thumb, swap and CDC-ACM.
3. **Mainline kernel (6.x) with a new device tree**, booted from RAM via
   U-Boot first (milestone 1: UART + GIC + timer). Weeks of work; see the
   "routes" section of kernel_research.md. Needs SD boot (project 2).

## 2. SD-card boot (low priority: after the end-goal release)

**Goal (owner, 2026-11-03):** boot from the SD card by the DIP switch,
without the NAND. An extra recovery path if the NAND is ever completely
corrupted, and maybe a way for NAND-only installs to stop depending on mtd5,
freeing its ~200 MB.
**Status** ([docs/sd_boot_plan.md](docs/sd_boot_plan.md)): U-Boot from NAND
can read the card once the two SD pin selects are set (0xf8041080/84 =
0x1002, RAM only: `uboot_cmd.py --pinmux-sd`), and boots our kernel from raw
card sectors by hand (`tools/sd_raw_boot.sh`, 2026-10-31). The DIP-switch
boot (the boot ROM loading U-Boot from the card) hangs silently; open lead:
the SD pad settings the ROM uses in mode 6.
**Not the daily boot path:** that is our kernel in mtd0 (#3).

## 3. Internal NAND install (stock printers have no SD card)

**DONE 2026-11-02** ([docs/usb_installer.md](docs/usb_installer.md)): the
USB stick installs the runtime into `/klipper` on the stock root (mtd6, not
mtd5: that would erase the factory recovery set), removing Sindoh's app
(backed up to the stick per printer and firmware) and Qt WebKit. Install,
upgrade, cancel and remove (stick backup or the mtd5 fallback) tested on
the test printer; installs on the work printer from 160505 and 191210
firmware. Open: our kernel in mtd0 (step 3c, not approved), NAND space for
upstream updates (#10).
End goal (our kernel in mtd0, our root in mtd6, mtd5 untouched): revert by
plugging in a Sindoh update stick (decided 2026-11-03, TODO 11d).
The sequence to get there: [docs/end_goal_install_plan.md](docs/end_goal_install_plan.md)
(all stages approved 2026-11-03; start after the weekly token refresh).

## 4. Object-on-bed check with the camera

**Goal:** before a print, warn or stop if something is still on the bed.
**Plan:** fixed bed pose + lamp on -> snapshot from ustreamer -> compare with
a reference of the empty bed (downscaled difference + blob size) in a small
Klipper extra; PRINT_START stops with "Object on the bed?", the screen offers
CONTINUE / CANCEL. Camera looks down at the bed from close above
(hardware_notes, 2026-10-27).
**Needs the user for:** the pose that shows the whole plate, the reference,
tests with real leftovers (thin first layers are the hard case).
**Pose problem (2026-10-28):** the check must run BEFORE G28 - Z homes
upward, so a tall leftover (or a spool left from the dryer) would be pushed
into the head/gantry. So the bed can't be moved to a fixed pose first.
Plan: PRINT_END, CANCEL_PRINT and the dryer end with the bed at the bottom
(Z 190, fixed Y) and record that in save_variables; PRINT_START checks the
picture at that pose before homing. Unknown pose (power cycle, manual move):
find the plate's edges in the picture and compare in plate coordinates, or
ask on the screen. A Z sweep (camera/bed_pose_sweep.sh) shows how the view
changes with height.

## 5. Faster stepping in the UPC firmware

**Goal:** raise the step-rate ceiling. Each step is one hardware engine move
now; the engines can do multi-step moves with their own ramp (stock firmware
does), which would cut per-step overhead.
**Status:** plan for review: [docs/faster_stepping_plan.md](docs/faster_stepping_plan.md)
(2026-11-02). Today's limits are fine for the stock speeds. Also open: what step-engine registers +0x10 / +0x14 /
+0x2c mean (copied from the stock app, 2026-10-27).
**Done =** drift test (scratchpad drift_test.py) still 0.000 mm at higher
speeds, emulator regression passes.

## 6. Other Sindoh models

**Goal:** the same Klipper port on the 3DWOX 1X, 2X (dual extruder) and 30X.
**Status:** [docs/other_models.md](docs/other_models.md); OEM firmware for all
models decrypted (oem_models, oem_3dwox1); the 30X key is unknown.
**Next:** 1X testing; 2X second extruder; 30X key.

## 7. Spaghetti / failure detection

Not on the printer (CPU/RAM). Document how a main Klipper host running
Obico (or similar) can watch this printer through its Moonraker.

## 8. Cartridge chip writing

Read-only today (docs/cartridge_chip.md). Writing (e.g. resetting the
remaining length) stays off unless the user explicitly agrees.

## 9. JTAG

CN3 header prepared, no TAP answered (likely fused off), [docs/jtag_prep.md](docs/jtag_prep.md).
Parked.

## 10. Before a release

**Release decision (owner, 2026-11-03):** the current installer (stock
kernel, Klipper in /klipper on mtd6) becomes the first public release, but
not yet: the screen app and features are still being refined, and the
faster stepping is still being tested. The work printer has completed a
long print on it.

- **Homing speed:** DONE 2026-11-02: X/Y at stock's 208 mm/s seek, Z
  stays at 5 mm/s (stock 5.05; 10 stalls lifting the bed).
  [docs/homing_speed_plan.md](docs/homing_speed_plan.md).
- **Stick backups and firmware versions:** DONE 2026-11-02: each backup
  stores the firmware version; a mismatch offers a new backup and keeps
  the old one as `<MAC>_<firmware>`.
- **Updates and NAND space: DECIDED 2026-11-03** (with the storage tiers,
  #11): on a NAND-only install Mainsail and Moonraker update from upstream
  (git, shallow), Klipper (host + UPC firmware) from our releases; with an
  SD card everything updates from upstream and builds on the printer.
  Our Klipper fork is public, so anyone can build the images if our
  releases stop. Background below (written for the ~40 MB of the current
  /klipper install; the end-goal root leaves ~140-150 MB):
  Goal: Klipper and
  Moonraker update from their upstream main branches through Moonraker,
  without the port having to publish images. Facts: Klipper's host side is
  upstream plus three add-on modules (dp200_cartridge, upc_clockcheck,
  upc_stats: installable as plugins); Moonraker is unmodified. On the
  printer, upstream updates need git + a shallow history (~15 MB), pip,
  and a C compiler (Klipper rebuilds chelper; some Python packages have C
  parts, no armel wheels): ~50 MB of flash, ~40 MB is free. The UPC
  firmware (fm.bin/io.bin, ARM cross-compiler) can't be built on the
  printer: an upstream MCU protocol change would need a rebuild.
  Options: A) the stable base (Debian, Python, git, compiler) in a
  read-only squashfs+xz image (needs squashfs.ko for 3.2; loop.ko ships),
  the apps as writable git checkouts: ~25-35 MB free; B) no image, remove
  more stock files (unused modules, /test/web, OpenCV; stick-only
  restore) and add git/pip/compiler: ~15-20 MB free; C) git + pip only:
  Moonraker/Mainsail from upstream, Klipper pinned. USB/SD storage is out
  (no extra hardware).
- **Wi-Fi drops to the other saved network (2026-11-02, twice):** cause:
  power saving (the 8782 missed key handshakes, reason 15). Power saving
  is now off at boot and on every connection: 0 drops in ~6 h (68 before).
  The screen's WiFi -> SAVED page sets the first choice; the watchdog goes
  back to it. Still watching for a day, then on the work printer.

## 11. G-code and log storage (2026-11-03, decided: see the end)

**Problem:** the NAND install leaves ~40 MB free on mtd6. A 23-min cube is
0.4 MB, but long prints run 15-25 MB (the owner's USB stick) and detailed
multi-hour ones 50-200 MB; Moonraker never deletes G-code by itself.
**Owner's direction:** an SD card added once inside the case (the microSD
slot is on the mainboard, not reachable from outside), then forgotten;
any size. Our own kernel may add whatever filesystem support is needed
(the stock 3.2 kernel has vfat, ext2/3/4 and an NFS client; no exFAT, no
SMB).
**Pieces:**
- Detect the card at boot, mount it (ext4; FAT32 too), use it for
  printer_data/gcodes and logs; NAND as before without one. Offer to
  format a new card from the screen.
- NAND space safety for printers without a card: refuse uploads that
  don't fit, offer/auto-delete the oldest finished G-codes, show free
  space on the screen and in Mainsail.
- Alternatives considered: a USB stick on the front port (shared with the
  accelerometer: hub), an NFS share (unlimited, but a network drop ends a
  print), and, as the owner's last resort, Klipper/Moonraker on a separate
  host with the printer as bridge + screen (upctool bridge over TCP).
**Decided 2026-11-03: optional, with tiers.** No card is required to
install. Boot path stays the agreed one: our kernel in mtd0, our system in
mtd6, mtd5 recovery untouched, no U-Boot env change. With our system
replacing the stock root, ~140-150 MB of mtd6 should be free (estimate:
~106 MB on flash for today's runtime). Tiers:
- NAND only: managed G-code space (upload check, auto-delete oldest
  finished jobs, free space shown), logs in RAM, Mainsail/Moonraker
  updates from upstream, Klipper from our releases if space is tight.
- SD card inside (or a USB stick on the front port): G-code and logs on
  it, full upstream updates (git/pip/compiler), timelapse, swap, backups.
- Our kernel detects a card/stick marked for the printer at boot; the
  screen offers to format one; the installer reports what it found.
**Next:** build it with the mtd0 kernel install (step 3c, pending OK).
