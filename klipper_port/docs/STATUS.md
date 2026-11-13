# Status (overwrite in place; last updated 2026-11-12)

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

## Dev printer, as of 2026-11-12

- **mtd0:** `m1-nandboot-bank3.uimg`, md5 `7eae8600a4872619711b3e891df129ca`
  = C3 (the SMP freeze fix) + the GPIO bank 3 pad setup (the motor fix).
  Rollback: C3 `a4e0cb33...` on the build box (10.10.0.68:8098).
- **Command line:** `console=ttyS0,115200n8 marvell_nand.write_window=1741,4091 panic=10 consoleblank=0 timer_mv61x0.hang_wdt=30`
- **Wi-Fi module:** `mwifiex_usb.ko` 0028 (`6645762a`): reload-safe.
- **UPC firmware in /opt/dp200:** fm `c313d379`, io `dbc8e40d`.
- **Config and screen app** (deployed 11-12): `dp200_macros.cfg` `22e88b5f`,
  `dp200_printer.cfg` `180033a5`, `dp200_screen.py` `561d5ee1`.
- **4 GB card** is inside as storage; its gap (sector 64) holds the bank3
  image for RAM boots. The 2 GB card is the rescue card: never write it.
- **Works:** boot from NAND, two CPUs (10 h soak on C3), NAND root, Wi-Fi
  (6 h soak), motion, heating, a full print with pause / unload / load /
  empty bin / resume.
- **Not yet:** a long soak on the bank3 kernel; Wi-Fi cold boots (part D);
  the end-goal installer (stages 6-9).

## Work printer, as of 2026-11-12

- Latest USB stick install (the 11-07 payload), stock 3.2 kernel. Printing.
- It does **not** have the 11-12 changes (macros, prime line at Y 0, the
  screen app's paused-print and load pages). They go in the next payload.

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
| UPC stepping firmware | the Klipper fork `catawalks/klipper` branch `sindoh-dp200`; `docs/faster_stepping_plan.md` |
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
