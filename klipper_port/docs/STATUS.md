# Status (overwrite in place; last updated 2026-11-17)

The project: Klipper on the Sindoh DP200, on the printer's own SoC. Two
setups exist, and they are different on purpose.

## The two printers

| | **Dev printer** (Stanley Model 1 converted to DP200Q) | **Work printer** |
|---|---|---|
| Role | All kernel and hardware testing | End-user stand-in; real prints |
| Kernel | **Our mainline 6.18.59**, in mtd0, two CPUs | **Stock vendor 3.2** |
| Root | Our Debian root, UBIFS in mtd6 (`ubi0:filesystem`) | Stock root + our runtime in `/klipper` (USB stick install) |
| Installed by | Hand, over serial | The USB stick (`docs/usb_installer.md`) |
| Reach | Serial COM3 on the dev PC; Ethernet 10.10.0.147; Moonraker :7125 | No link from the dev PC; the owner carries the stick and logs |

**The USB stick carries userspace only** (Klipper, Moonraker, Mainsail, the
screen app, macros, UPC firmware). It never carries a kernel. Kernel work
reaches the work printer at the end-goal install
([end_goal_install_plan.md](end_goal_install_plan.md)), when that printer
becomes the full kernel-swap test machine.

## Dev printer back on our system since 2026-11-17 night

The stock Wi-Fi test is over (result: stock held the AP for 2 h with no
drop). Way back done 11-17 (owner-approved four-write job): RAM boot
from the card's gap, `mtd0_kernel_update.sh` (7eae8600, KUPDATE OK),
the saved root tar into mtd6 (md5 1d60d93b, 15331 files, 0 ECC
failures), card marker renamed to `/.dp200-root.off`, boot from NAND:
root ubi0:filesystem, Klipper ready with the saved shapers and mesh.
The section below is current again (Sindoh's 200730_2 update touched
only the stock root, which is replaced again), except that **Wi-Fi
power save is on** (the new default with our kernel, TODO 26) and X uses
`2hump_ei` 87.4 Hz (docs/input_shaping.md). Backups of the stock test:
`D:\DP200\backup\nand_images\stock_test_20261116\` (never published).

## Dev printer, as of 2026-11-15

- **mtd0:** `m1-nandboot-bank3.uimg`, md5 `7eae8600a4872619711b3e891df129ca`
  = C3 (the SMP freeze fix) + the GPIO bank 3 pad setup (the motor fix).
  Rollback: C3 `a4e0cb33...` on the build box (10.10.0.68:8098).
- **Command line:** `console=ttyS0,115200n8 marvell_nand.write_window=1741,4091 panic=10 consoleblank=0 timer_mv61x0.hang_wdt=30`
- **Wi-Fi module:** `mwifiex_usb.ko` 0028 (`6645762a`): reload-safe.
- **Klipper:** the fork's `sindoh-dp200` ee0c7f8e (the pin in
  `klipper/FORK`) since 2026-11-15: fm `fbc8c0db`, io `16afb0be` (built
  on the build box, default config), klippy and `c_helper.so` `7380efa1`
  from 8203a7d7 (the three commits since then change firmware source
  only). Tested: homing, drift test, 20 mm box. Kept on the printer:
  `fm.bin.tip`/`io.bin.tip` (8203a7d7) and `klippy.cur`, `fm.bin.cur`,
  `io.bin.cur` (the build from before the branch replacement).
- **Config and screen app:** `dp200_macros.cfg` `1154d13d` (11-15: five
  warm-up touches before a mesh), `dp200_printer.cfg` `180033a5`,
  `dp200_screen.py` `561d5ee1`. Its own `printer.cfg` has
  `[axis_twist_compensation]` and probe `z_offset` 2.630 (was 2.580)
  since 11-15 (the old file is
  `printer.cfg.bak-1115` next to it).
- **Other changes of 11-14** (old files kept with `.bak-1114`):
  `rc.dp200` `9a605e09` logs the camera streamer and restarts it;
  `dp200_wifi.py` `1143a67e` limits saved networks to 2.4 GHz.
- **How to test and switch builds:**
  [dev_printer_testing.md](dev_printer_testing.md).
- **4 GB card** is inside as storage; its gap (sector 64) holds the bank3
  image for RAM boots. The 2 GB card is the rescue card: never write it.
- **Works:** boot from NAND, two CPUs (10 h soak on C3), NAND root, Wi-Fi
  (6 h soak), motion, heating, a full print with pause / unload / load /
  empty bin / resume.
- **11-16 additions on the dev printer:** `[input_shaper]` in printer.cfg
  (X 3hump_ei 82.6, Y 2hump_ei 39.0; backup `.bak-1116-shaper`); numpy 2.2.4 for Klipper (copied
  from the card, with libblas/liblapack/libgfortran); `dp200_adxl.cfg.off`
  with `rate: 800`, `max_freq: 135`; `dp200_macros.cfg` with the mesh
  front row at Y 5 (backup `.bak-1116`). Sensor config is off.
- **Bank3 kernel soak:** up 3 days 12 h on 11-16 (booted 11-13), with
  about ten prints, no freeze or reboot.
- **Not yet:** Wi-Fi cold boots (part D);
  the end-goal installer (stages 6-9).

## Work printer, as of 2026-11-16

- Runs the 11-15 payload on the stock 3.2 kernel (installed from the
  stick by the owner on 11-16):
  `3e5e43ce1f2c063cf28aae663bfcee91`, 84,430,492 B, build
  `a112379 2026-11-15`. Userspace only. It carries the fork at 8203a7d7
  (klippy, helper, fm/io: the dev printer is three firmware commits
  newer, ee0c7f8e), the 11-12 and 11-15 macros, the screen app
  `561d5ee1`, the camera restart loop and the 2.4 GHz Wi-Fi limit. Its
  printer.cfg has no `[axis_twist_compensation]`. PC copies: this
  payload in `D:\DP200\kernel\out\payload_20261115`, the one before
  (`5f3336e1`, 11-07) in `D:\DP200\backup\usb_stick_copy_20261115_before`.
  Confirmed by the owner 11-16: SYSTEM -> INFO shows that build, the
  first print (the ADXL head mount, PLA) came out good, the prime line
  is in its new place, and Mainsail's MCU panel showed the UPC load
  live during the print.
- 11-16 is the first time this Klipper (on upstream 29d4ec2d) runs on
  the stock 3.2 kernel; before, only on the dev printer's mainline kernel.

## Who owns what

One session coordinates: it alone drives the dev printer (serial, deploys,
NAND writes), merges `TODO.md` and publishes to GitHub. The others write
and build in their own area and report files and md5s.

| Area | Where the work lives |
|---|---|
| Coordination, printer access, macros and config, install, docs | this repo (`klipper_port`), dev PC |
| Kernel and boot (SMP, NAND, build variants) | build box `~/SINDOH-DEV`, served on 10.10.0.68:8098; summary in `docs/kernel/smp_freeze_summary.md` |
| Motor / UPC driver | build box `~/SINDOH-DEV/motor`, branch `upc-bank3-pads` (7dd0f21, not yet merged into the kernel tree) |
| Wi-Fi (8782 driver, firmware study) | build box; `TESTPLAN.md` and `upstream/` there; facts in `docs/kernel/wifi_88w8782.md` |
| Klipper code (UPC MCU port, stepping, host modules) | the fork `catawalks/klipper`, branch `sindoh-dp200`; the pinned commit is `klipper/FORK`; rules in `klipper/README.md`; `docs/faster_stepping_plan.md` |
| Touch screen app | `install/display/` in this repo; `docs/touchscreen_options.md` |

Publishing: commit in `klipper_port`, then merge into the `sindoh_publish`
checkout (subtree `klipper_port/`, after merging `origin/main`) and push to
`catawalks/sindoh`. Never push from `klipper_port` directly.

## Standing rules (short; the reasons are in the docs they point to)

- NAND: [nand_layout.md](nand_layout.md). Every NAND write needs the
  owner's OK; RAM-boot a kernel first.
- **Never home Z with anything on the bed** (Z homes upward).
- Motion or heat only with the owner present.
- Check the printer is idle before restarting Klipper or the screen app.
- Never publish Marvell firmware or images, or Wi-Fi networks.
