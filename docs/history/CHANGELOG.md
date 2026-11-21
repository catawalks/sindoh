# Changelog

Newest first. One or two lines per item, with the commit where there is
one. The detail for everything up to 2026-11-12 is in
[TODO_archive_2026-11-12.md](TODO_archive_2026-11-12.md) and the other
files in this folder; `git log` has the rest.

## 2026-11-20
- **1X mapped live over SSH** (docs/1x.md "Live map"): two UPC cores
  (ITCM 0xF9800000/0xF9810000, shared DTCM 0xF9880000) running small
  helper firmware; stepping on six Marvell `stepper-mod` blocks; TMC2224
  drivers on one single-wire UART (ttyS2) with a 3-bit motor select.
  Read-only.
- **Remote shell stick for the 1X** (`tools/remote_shell/`): starts the
  stock dropbear on port 2222, key login only, everything in RAM; writes
  the address to the stick. **Works on the owner's 1X** (11-20): key
  login as root over Wi-Fi, host key matched the stick's fingerprint;
  the stock watchdog left dropbear running and the stock app untouched.
  Key pair kept outside the repositories.
- **Beeper stock pitch left as is** (owner): the work printer's beeper is
  faulty, so it can't give the stock pitch (TODO 13). The owner measured
  a stock 1X's beep at 4 kHz: the same as our pick (1250 ticks).
- **2X ("Prime") recovery SD card read** (docs/prime_sd.md), on the dev
  printer, read-only: a factory NAND recovery card for the 2X r1 (boot
  header + MiniLoader + U-Boot + recovery Linux; LUKS partition opened
  with the board-derived key from its own script) with `PRIME_190726_2`,
  the 2X r1 mtd layout and a factory karas.db. Factory motor row NO=4 =
  -15/+20/+30/+50, the dev printer's values; the 1X's row 4 is
  -15/+40/+40/+50. Image and contents kept on the PC only. The Prime
  board has DIP switch pads but no switch. Dev printer's 4GB card back in.
  Board photos (prime_sd.md "The board"): the DP200's NAND chip, a fitted
  microSD socket, an unfitted 8-way "sLoR SET" switch, PC_DEBUG1/2
  headers, a JTAG footprint and TMC2224 motor drivers.
- **SD boot: a new lead documented** (sd_boot_plan.md): Sindoh's card has
  the boot table in sector 0, sharing it with the MBR; our DIP test 3 used
  sector 1. A five-step test for later, on a spare card. On the DP200
  the two can't share the sector (mtd0 0x1BE-0x1FF is U-Boot data), so
  the test card has no partition table.
- **Model survey v1.1 released** (catawalks/sindoh-model-survey): runs in
  the background with no screen messages. On the owner's 1X, taking over
  the stock screen left it stuck at "Booting" after the hand-back (power
  cycle needed). Four 1X runs; reports in `survey_reports/` on the PC
  (not published: they come from the owner's printer).
- **1X findings** written up in docs/1x.md: 88PA6270 with 4 x Cortex-A53,
  1 GB, 8 GB eMMC (ext4 root, 413 MB free; recovery system in p5), UPC
  loaded and started by the stock engine, Marvell stepper/dcmotor drivers,
  `ttyS2` held by the engine, motor offsets -15/+15/+30/+50.
- **v0.1.0 payload, first candidate** (`c04476d0`, build `12b9481`): fork
  9b174ab, fm `d7e9e872` and io `2982dfc1` from the build box (the
  printer's own build failed: Windows line endings in the fork tarball,
  now noted in dev_printer_testing.md), `c_helper.so` `7380efa1`. Saved
  on the PC in `kernel/out/payload_20261120_v0.1.0`. The content audit
  withdrew it: Marvell's 8782 Wi-Fi firmware was inside (through Debian's
  merged `/lib`; the boot scripts copy it from the stock root anyway),
  plus the build printer's `recovery_info` and two `init.mainline.bak*`.
  `runtime.exclude` drops all three. Installer and remover `.she` packed
  and verified.
- **v0.1.0 payload, second candidate** `0ee46f50` (build `3940525`; also
  without `opt/dp200/*.prev`): content audit clean. Release folders and
  `SHA256SUMS` in `kernel/out/release/v0.1.0`; on the USB stick
  (`_update_rodin_KlipperInstall`, `_KlipperRemove`), checked by SHA-256.
  The work printer's 11-16 install log saved to
  `kernel/out/payload_20261115/`. Not installed yet.
- **Model survey stick**
  ([catawalks/sindoh-model-survey](https://github.com/catawalks/sindoh-model-survey),
  owner-approved for publishing 11-20): a read-only stick for every Sindoh
  model that saves a masked hardware report to the stick. Commit `bbdebc4`
  adds a lock and stick-mount checks, because the 1X's `media.connect` runs
  `auto_update.sh` twice per stick. Tested on the PC only; the first run on
  hardware is to be a 1X. Linked from other_models.md.
- `release_check.sh`'s dry run can no longer run on the dev printer (our
  kernel in mtd0; the installer needs stock 3.2): the work printer's
  install covers it (release_checklist.md).
- **A second 3DWOX 1 source:** the top-level dumps of catawalks/sindoh are
  Sebastian Schmidt's 3DWOX 1 (yath/sindoh, 2021, the repo it was forked
  from): the DP200's partition table exactly, gluebi for mtd7/8, 57 MB free
  then; credited in docs/3dwox1.md. `Model_1_Converter/` is the owner's
  (usb_installer.md said "community"). The top level of catawalks/sindoh
  is GPLv3 too, except Sebastian's files (no license, his).
- **Release 1 decisions** (owner): v0.1.0; DP200 family only (RODIN_200730_2);
  pre-packed `.she` files; GPL-3.0-or-later (`LICENSE`, README "License";
  `kernel/` stays GPL-2.0). The installer now refuses a non-RODIN firmware
  line by name (a 3DWOX 1 passed every earlier check); syntax-checked and
  the version parsing tested on both update files, not run on a printer.
- **Release 1 started** (owner): [release_checklist.md](../release_checklist.md)
  written (decisions, build, content audit, hardware tests, documents,
  publish). TODO 26 is no longer a release blocker: the drops are put down
  to the dev printer's home network (owner); only the watchdog's cached
  scan is left. Home network names taken out of the current docs.
- **3DWOX 1 partitions from the update files:** the update script is the
  DP200's, byte for byte; the kernel is a rebuild of the same source; the
  extra mtd7/8 are most likely gluebi. What only a real unit can tell is
  listed in TODO 38.
- **Each firmware line is its own target** (owner): other_models.md,
  3dwox1.md and TODO 38 no longer assume the 3DWOX 1 (RODUP_) shares the
  DP200's (RODIN_) mainboard.
- **INSTALL.md brought up to date:** no public release yet (decided
  11-03); Klipper goes to `/klipper` on the stock root, the Sindoh app and
  WebKit are backed up to the stick, mtd5 is untouched (it still described
  the old mtd5 install); the remover deletes `printer.cfg` with `/klipper`.
- **3DWOX 1 notes credited and extended** (docs/3dwox1.md): a source section
  (Fredrik Gustafsson's PR #1 and his klipper-sindoh repo; nothing measured
  by us), his later findings (the 2x travel was his firmware build, per-unit
  motor offsets of 99, a TMC2224 driver board, stock homing values, model
  tag, Wi-Fi start timing), and "no microSD seen" no longer read as "no slot".
- **Installer reads each printer's motor currents** from its karas.db
  (CONF_ENGINE_PWM NO=4) into `dp200_machine.cfg`, which dp200_printer.cfg
  includes (wildcard: no file, no error). Not yet run on a printer (TODO 38).
  The config comment had the dev printer's Y offset as +15; it is +20.
- **`MESH_ADAPTIVE`** (opt-in, idea from klipper-sindoh): adaptive mesh from
  the slicer's first-layer G-code; `PRINT_START MESH=0` skips the start mesh.
  The default (4x4 mesh, bed-empty question) is unchanged.

## 2026-11-18
- **Beeper in Klipper** (TODO 13): fork sindoh-dp200 9b174ab (klipper/FORK),
  `[output_pin beeper]` (io:pwm10), M300 at 36 % (owner: sounds like
  stock), the dryer's end signal on the beeper; rc.dp200 gives the pad
  its stock function before loading the firmware. Deployed on the dev
  printer.
- **Beeper pad from the kernel:** m1-nandboot-beeper (md5 232c743a, build
  box 75743ea: bank3 7eae8600 + `5 15 0x000c1001`) RAM-booted from the
  card's gap: "UPC pads: 63 set", pad 0x000C1001, M300 heard (owner).
  rc.dp200's devmem step removed again.
- **Beeper kernel in mtd0** (owner's OK): mtd0_kernel_update.sh from the
  RAM-booted kernel, KUPDATE OK (232c743a, U-Boot unchanged, ecc_failures
  0). Booted from NAND: 63 pads set, beeper pad 0x000C1001, 2 CPUs, ubi0
  root, Wi-Fi up, Klipper ready, M300 heard (owner).
- **Bank 3 pad fix in main** (TODO 20 closed): 7dd0f21 from the build box
  applied as c72b89e (mv61x0-upc.c + the DTS), so the next kernel build
  has what mtd0 runs.
- **Closed (owner):** cold-boot Wi-Fi (TODO 1: up after every boot and
  manual reset); work-printer Wi-Fi stability (TODO 11: the stock driver
  it runs held the AP on the dev printer, 67 min, no drop).
- **Camera streamer closed** (TODO 26a): no exit since 11-14 over several
  boots. rc.dp200 now logs only an exit (not ustreamer's output); deployed
  on the dev printer (md5 22ea55e4).
- **Wi-Fi drops are back** (TODO 26, still open): power save on held
  the AP for 2 h only; reason 7 drops every ~95 s since 11-18 00:59 UTC.
- **Beeper mapped** from the stock app (TODO 13, docs/hardware_notes.md):
  passive piezo, block 10, 4 kHz, volume 3/6/36 %. `tools/beep_test.sh`
  for a listening test; fork branch `upc-beeper` (8ae38c1), untested.
- **Beeper heard** (owner at the dev printer): silent until GPIO bank 5
  pin 15 got its stock pad function (0x000C1001), which our kernel never
  sets; beep_test.sh now sets it and follows the stock pwm_on order. The
  stock 250-tick period only ticks. Measured with the owner's spectrum
  analyzer: the timebase ticks at 5 MHz, not the 1 MHz stock assumes;
  1250 ticks = 4 kHz at 36 % sounds like stock (owner). Fork
  `upc-beeper` 9b174ab uses that period; beep_test.sh takes real Hz.
- **3DWOX 1 hardware notes** from catawalks/sindoh#1 (Fredrik Gustafsson,
  11-11) added as docs/3dwox1.md, linked from other_models.md and the
  docs index.
- **TODO 20 checked** by the build-box sessions: the bank 3 fix is
  7dd0f21 on `upc-bank3-pads` in the motor clone, not pushed, not in main.
- **Benchy corner damage is not the seam** (TODO 18): the seam was on the
  other stern corner; the G-code is the same at both corners.
- **TODO:** the accelerometer setup leftovers are their own item (19);
  the screen's INPUT SHAPING page test is owner item 5.

## 2026-11-17
- **First fast Benchy** (12 mm3/s, accel 2500, 1h 16m): shape and bottom
  good; stringing hairs, illegible stern text, a rough stern corner
  where the aligned Z seam sits (TODO 12a, 18).
- **TODO has a Printer tuning section** (owner, 11-18): speed, pressure
  advance, retraction, seam, mesh and probe items moved there.
- **Max flow measured** (dev printer, PLA 205 C): clean to 14 mm3/s,
  duller at 16-18, extruder clicks at 20; slicer limit about 12 (TODO 12a).
- **Dev printer max_accel 2500** (owner; its printer.cfg; shipped config
  stays 1500).
- **Wi-Fi power save is on by default** (owner):
  on every printer and both kernels (init.mainline,
  dp200-wifi-action.sh, the USB stick's dp200-start.sh);
  /etc/dp200/wifi_power_save overrides. Deployed on the dev printer;
  the work printer gets it with the next payload.
- **X shaper set to `2hump_ei` 87.4** on the dev printer, the fastest
  band (max_accel 8094); the X ripple (about 20 Hz) comes from play in
  the magnet/dovetail head mount and stays with any shaper.
- **Dev printer back on our system** (mtd0 7eae8600 and the saved root in
  mtd6, both verified, 0 ECC failures; booted from NAND, Klipper ready).
- **Wi-Fi power save on stops the 91 s drops** on our kernel: no
  disconnect in 1 h 45 min (before: every 91-95 s). Opt-in flag
  /etc/dp200/wifi_power_save in `dp200-wifi-action.sh` (TODO 26).
- **X shaper comparison print:** six shapers, no visible difference; the
  X ripple is not the measured 38 Hz peak (docs/input_shaping.md).
- **Stock holds the preferred network** (dev printer, Sindoh update
  200730_2 applied by the owner, /app only; U-Boot and env checked
  unchanged): 67 min on the AP that drops our kernel every 91-95 s, no
  state change, 0 of 3600 pings lost. The Wi-Fi drops are on our side
  (TODO 26). The factory version before the update could not join
  (handshake timeout, reason 15).
- **Dev printer reverted to stock for the Wi-Fi comparison** (owner's
  OK for the four writes): root saved to the PC as tar and raw image,
  card root booted, `dp200-revert.sh` root then kernel, stock boots.
  Wi-Fi watcher started; stock has no saved network, the owner joins.
  State and the way back: docs/STATUS.md, first section.

## 2026-11-16
- **Ringing test read by the owner:** Y clean to 2750; X rings after
  sharp corners in every band, after soft turns above 2500. An X shaper
  comparison print is prepared (docs/input_shaping.md).
- **Ringing test print started** on the dev printer with the shapers
  on: Klipper's ringing tower, acceleration 1500 to 4250 in 5 mm bands.
  Recipe in docs/input_shaping.md. Result open.
- **Input shaper saved on the dev printer** (owner's OK): X `3hump_ei`
  82.6 Hz, Y `2hump_ei` 39.0 Hz in printer.cfg. `max_accel` unchanged
  (1500). Sensor config off again. No print with it yet.
- **Head mount version 4 printed and proven:** X homes with the board
  and cable on. Third X run: `3hump_ei` 82.6 Hz, max_accel <= 4500, in
  line with the first two. Unplugging the board with Klipper running
  shuts Klipper down; recovery is in docs/input_shaping.md.
- **Input shaping, Y axis measured** on the dev printer with the printed
  bed bar (it fits): `2hump_ei` 39.0 Hz recommended, max_accel <= 1500;
  wide Y peak at 27-40 Hz. Z was homed with the head at the back center,
  away from the sensor. Not saved. docs/input_shaping.md.
- **Screen: custom MACROS page** opens and lists the macros (owner).
- **The screen's OBJECTS page works on a real print:** owner printed both
  ADXL mounts together and canceled the head mount from the touch screen;
  the bed mount went on.
- **ADXL bed mount** (`adxl_bed_bar.py` writes the STL): a bar in place
  of one front grip of the build plate, by the owner's caliper readings.
  Replaces the `adxl_bed_clamp.scad` draft. Not printed yet.
- **Input shaping, X axis measured** on the dev printer (FLY-ADXL345 on
  the version 3 mount): `3hump_ei` 80.8 Hz recommended, max_accel <=
  4300; X peak at 44-47 Hz. Needed: numpy by hand, `rate: 800`, port
  permissions. Not saved. docs/input_shaping.md.
- **Mesh with the front row at Y 5 ran clean** on the dev printer (30
  points). First-layer test at the front still open (TODO 15).
- **ADXL head mount version 4:** version 3 blocked X homing (hit the
  Bowden tube at the right end; "No trigger on stepper_x"). Front 10 mm
  removed, posts moved to the left end, posts 5 mm high. Not printed.
- **Mesh front limit Y 30 -> Y 5, six rows** in dp200_macros.cfg (repo
  and dev printer). Not tested yet (TODO 15).
- **TODO cleanup with the owner:**
  - 24 (initramfs), Ethernet MAC part: done since 11-07. init.mainline
    sets it from the U-Boot env in mtd1; the dev printer's boot log shows
    the same MAC (..:10:13) on every boot. The log and write-window parts
    stay open.
  - 25: `iw` is in the root build's package list; Wi-Fi power save stays
    off (owner).
  - 30 (prebuilt zig UPC images untested with motion): dropped, owner;
    the printers run the gcc builds.
  - 31 (bed took 9 min to 60 C once, 11-12): dropped; not seen again.
  - 32 (`map_front.py` rework): dropped; the front was mapped on 11-12
    and the script is not in the repo.
  - 33 (why a long LOAD request's reply never came): dropped; the screen
    releases the busy state by itself and LOAD watches the encoder
    (d2565c7). The cause was never seen.
- **Work printer on the 11-15 payload confirmed** (TODO 9): build line
  `a112379 2026-11-15`, first print good, prime line in the new place.
  First run of the rebased Klipper on the stock 3.2 kernel.
- **UPC load in Mainsail's MCU panel** (TODO 5): owner watched it live
  during that print. Done.
- **ADXL head mount version 3 printed** (PLA) and test fitted on the
  work printer's head: snaps on tightly. Board not screwed on yet.
- **Bank3 kernel soak done** (TODO 21): mtd0 image 7eae8600 up 3 days
  12 h 44 min on 11-16 15:18 UTC, through the 11-14/15 test prints; no
  freeze, no reboot.
- **TODO 22 dropped** (the one-CPU kernel's reboot of 11-11): owner, that
  kernel is no longer needed.
- **Camera** (TODO 26a): no streamer exit in 57 h since the restart loop
  went in; the loop has not had to act.
- **Work printer updated to the 11-15 payload** (`3e5e43ce`, build
  `a112379`) from the stick by the owner; a print started on it.
- **FLY-ADXL345 head mount, version 3** (`71d8a6b`): head width 55.8,
  posts 15.5 apart, M3 screws (board holes 3.2), all by calipers; slots
  by calipers since version 2. Not printed yet.

## 2026-11-15
- **FLY-ADXL345 head mount, version 1** (`adxl_head_clip.py` writes the
  STL; replaces the placeholder `.scad`). Dimensions from the owner's
  ruler photos. Not printed yet.
- **Fork: three stepping commits merged into `sindoh-dp200`**
  (fast-forward 8203a7d7 -> ee0c7f8e; `upc-fast-step` deleted): no timer
  read after a step, fewer timer reads in the dispatch path, and
  `UPC_STEP_ARM` (default off). 193 -> 138 instructions per stepped step
  in the emulator (119 with the ARM option). Dev printer, owner present:
  default build and ARM build each passed homing, the drift test (shifts
  0.000 to 0.040 mm, the usual switch scatter) and the 20 mm box (420 s
  and 419 s; box 20.0 x 19.80 x 10.0 mm); clock estimate steady.
  `klipper/FORK` pins ee0c7f8e; the dev printer runs the default build.
- One mesh was discarded by the reference check during these tests
  (-0.112 mm): probe settling plus a bed still warming, not the firmware
  (40-touch runs on both builds level off). TODO 28a.
- **Dev printer on the fork's branch tip** 8203a7d7: fm `9834d57f`, io
  `90441e04`, `c_helper.so` `7380efa1`, built on the printer with the
  card's toolchain (`tools/fork_build_on_printer.sh`). Ready; not
  motion-tested.
- **Stick payload built and written to the USB stick** (userspace only):
  `3e5e43ce`, build `a112379 2026-11-15`, verified (key files match the
  repo, no Wi-Fi networks, no kernel). Not installed yet. The old payload
  `5f3336e1` is saved on the PC. How: docs/dev_printer_testing.md.
- **Fork: `sindoh-dp200` replaced by the clean history** (owner's OK):
  force-pushed 289952f9 -> 8203a7d7 (= tested tag `dp200-clean-c` plus
  two line-wrap commits). The old tip is kept as tag
  `sindoh-dp200-before-clean`; the `dp200-clean` branch is deleted, its
  tags `dp200-clean-a/b/c` stay. `klipper/FORK` pins 8203a7d7,
  `common/upc_hw.h` synced, `tools/fork_check.sh` passes.
- **Probe's false left-right slope found and compensated** (dev printer).
  With a mesh the first layer was too high on the left and squashed on
  the right. Paper test, mesh off, bed X 25/100/175 at Y 30: nozzle
  -0.175/-0.175/-0.150; settled probe 2.437/2.418/2.299. Added
  `[axis_twist_compensation]` (`z_compensations: -0.061, -0.042, 0.103`)
  to the dev printer's printer.cfg; afterwards the probe read
  2.375/2.340/2.421.
- First-layer check with both fixes (150 mm L, owner): "much better";
  still slightly more squish on the right. The owner needed -0.05 mm on
  the whole layer, so the dev printer's probe `z_offset` went from 2.580
  to 2.630 (Z_OFFSET_APPLY_PROBE, SAVE_CONFIG).
- **Five warm-up touches before every mesh** (`_SINDOH_MESH_WARMUP`): ten
  touches after a deploy read 2.464 2.449 2.444 2.438 2.437 2.435 ...
- **X/Y scale is right:** `dp200_xy_scale_150mm.gcode` (new in
  `gen_test_prints.py`) measured X 149.60, Y 149.40, widths 14.90 and
  9.90: PLA shrinkage, not a step error.
- New: `docs/dev_printer_testing.md` and the scripts it uses
  (`tools/drift_test.py`, `print_watch.py`, `probe_settle.py`,
  `klippy_switch.sh`, `klippy_build_chelper.sh`).

## 2026-11-14
- **`dp200-clean` tested on the dev printer** (owner present). Stage B
  (f01effd8) and stage C (0607ba28), each: Z/X/Y homing; drift test, 100
  zig-zags per speed (X: B -0.040 mm once at 30 mm/s then 0.000, C 0.000;
  Y: B 0.000, C -0.020 at 100 and 10 mm/s; no-move repeatability up to
  0.020); the 20 mm box with mesh and prime line, completed (421 s and
  417 s). Box B measured about 20.0 x 19.8 x 10 mm. klippy's
  `c_helper.so` was built on the printer for each stage.
- **Camera streamer: log and auto-restart** (`rc.dp200 webcam-loop`),
  after it died on the dev printer with no trace. Deployed there (rc.dp200
  9a605e09, old one kept as rc.dp200.bak-1114); a test kill was logged as
  exit 139 and the stream was back in 5 s. Temporary, until the cause is
  found (TODO 26a).
- **Wi-Fi: 2.4 GHz only** (`dp200_wifi.py` FREQS_24): every saved
  network gets `freq_list`/`scan_freq` for channels 1-14 and 5 GHz is left
  out of the scan list. The module (LG Innotek TWFM-M311D) has no usable
  5 GHz antenna. Deployed on the dev printer (1143a67e; .bak-1114 kept):
  no more 5 GHz attempts. It does not stop the AP's 91 s drops.
- **Wi-Fi fallback traced** (TODO 26): the main home access point
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
