# Status (overwrite in place; last updated 2026-11-15)

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

## Dev printer is on STOCK since 2026-11-17 (temporary, for the Wi-Fi test)

**Read this first: the "Dev printer" section below describes the system
that is saved on the PC, not what runs now.** Owner-approved 11-16: four
NAND writes as one job (mtd0 and mtd6 to stock, later both back).

- **Now in NAND:** stock kernel 3.2.0-g67a8e16 in mtd0 (blocks 2-63; U-Boot
  block still `dac6729a`), factory stock root + apps in mtd6, both written
  11-17 from the card root with `dp200-revert.sh --part root` and
  `--part kernel` (the script and checks of 11-07; 0 ECC failures). Stock
  booted by itself: UIManager up, karas.db rebuilt from mtd4, Ethernet
  10.10.0.147 with the right MAC. It is the factory version (no Sindoh
  USB update applied).
- **Wi-Fi on stock:** not joined; stock has no saved network. The owner
  joins on Sindoh's screen. **11-17 morning: stock cannot join
  Niholedotcom.** Every try is dropped about 3 s after association with
  "Deauthenticated (reason 0xf)" (4-way handshake timeout, the password
  step); the screen shows "saving network settings" and then no saved
  network. The AP is plain WPA2-PSK/CCMP at -20 dBm, and our kernel joins
  it with the same password, so the stock screen's password entry is
  the suspect (owner to check for symbols, spaces, capitals). Stock also
  joined the other SSID by itself once (from settings it keeps itself),
  and the Wi-Fi was dead after the night until a power cycle (owner).
  Watcher: `tools/stock_wifimon.sh`, run as /tmp/wifimon.sh, logs
  wpa_state / AP changes each second to /var/log/wifimon.log (on the
  root, survives power cycles; the script itself does not, so start it
  again after each boot from the PC's HTTP server,
  `deploy/usb/t/wifimon.sh`). The stock kernel log also persists, in
  /var/log/messages. Stock mounts the 4 GB card at /mnt/sd (journal
  replay after each power cycle).
- **Saved on the PC** (`D:\DP200\backup\nand_images\stock_test_20261116\`,
  never published: Wi-Fi passwords inside):
  - `dev_root_20261116.tar`, 346920960 B, md5 1d60d93b: the whole NAND
    root as files, taken with the Klipper stack stopped (15331 entries).
  - `mtd6_raw_oob_dev_20261116_b.bin`, 317644800 B, md5 1fc61187 (= the
    printer's own md5): raw + OOB. The first copy (`..._20261116.bin`,
    b6229c1e) differs in one bit of page 19956, an unstable raw bit.
  - The kernel is `D:\DP200\kernel\out\m1-nandboot-bank3.uimg`
    (7eae8600), and the 4 GB card's gap holds the same image (checked).
- **The 4 GB card carries `/.dp200-root`** now, so our kernel boots the
  card's root. The card's root differs from the saved NAND root only in
  the two mwifiex modules (older).
- **Way back (owner present, needs the OK that is already given):**
  1. `tools/sd_raw_boot.sh D:/DP200/kernel/out/m1-nandboot-bank3.uimg`
     (RAM boot from the card's gap; root = the card).
  2. `tools/mtd0_kernel_update.sh` with the bank3 image.
  3. mtd6: window 1741,4091, `ubiformat /dev/mtd6 -y -O 2048`,
     `ubiattach`, `ubimkvol -N filesystem -m`, mount, untar
     `dev_root_20261116.tar` from the PC (nc), sync, unmount, window
     none: as end-goal stage 5 (docs/end_goal_install_plan.md).
  4. Remove `/.dp200-root` from the card, `busybox reboot`, check
     Klipper, the input shaper section and the mesh settings.
  Then print `dp200_x_shaper_compare.gcode` (it is inside the tar under
  printer_data/gcodes and in `D:\DP200\kernel\out\ringing\`).

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
