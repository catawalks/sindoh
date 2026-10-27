# DP200 Klipper port - session handoff (2026-10-18)

Read this first, then README.md, docs/hardware_notes.md (measured facts) and
docs/stock_routines.md (decoded stock load/unload/clean/probe routines).

## Project goals and status (2026-10-19)

Goals: (1) Klipper on the stock DP200 hardware (UPC cores as MCUs, klippy/
Moonraker/Mainsail on the printer's Linux); (2) full printer function incl.
filament handling and a BL-touch-style bed mesh; (3) easy install for other
owners from a USB stick, entirely on internal NAND (stock printers have no
SD card); (4) USB revert to the OEM firmware.

Done: MCU port on both cores (gcc build on the printer), all axes/homing/
endstops, heaters/fans/thermistors, extruder + clutch, lever, encoder, probe
deploy/stow; filament path measured, LOAD/UNLOAD macros; Debian trixie armel
built on the printer; klippy READY, Mainsail on :80; G28, PROBE, bed mesh with
a stability guard; PAUSE/RESUME/CANCEL_PRINT; step limit found and capped; OEM
USB format decoded, installer/remove/pack scripts written; NAND image measured
(119 MB gz, fits mtd5).

Decisions / notes (10-19): keep the STOCK kernel 3.2 (88PA6170 has no
mainline support; upc.ko, 8782 WiFi, NAND, LCD are vendor-only). Only
worthwhile kernel work: rebuild the same 3.2 with ARM_THUMB/SWAP/HRT if
Sindoh's GPL source turns up. Klipper host is unmodified; ship a Klipper
FORK with src/upc merged (for Moonraker update_manager) + a separate repo
for configs/installers. Other Sindoh models (3DP101, Model 1 ST3DP1, 3DF1,
RDLL...) share the platform/update mechanism: per-model configs + a model
check in the installer. Install options for owners: (a) internal NAND via a
USB stick, (b) SD-card boot via DIP switches + U-Boot mmc boot
(mv61X0_mmcboot / bootcmd_mmc, root=/dev/mmcblk0p2) with no flash writes.
User's GitHub has a SINDOH fork to check (need its URL; no gh CLI here).
Added [respond] (M118 was an "Unknown command").
Z CALIBRATED 10-19: z_offset 2.530, Z position_endstop 2.275 (Z0 = nozzle on bed, paper confirmed);
probe x_offset 15, y_offset -30 (pin 5 mm dia.); mesh X20-190 / Y30-170 (front grip handle!).
5x5 mesh: range 0.276 mm (low back-left), SAVE_CONFIG'd as profile "default" (autosave block in the
printer's printer.cfg). PRINT_START BED= EXTRUDER= (G28, 4x4 mesh profile "print", CLEAN_NOZZLE
purge/wipe) and PRINT_END added - the BED HEATER IS UNTESTED under Klipper: test before printing.
CONFIG LAYOUT (done 10-19, verified with a real SAVE_CONFIG of probe z_offset): printer.cfg = the USER's
file ([include dp200_printer.cfg] + [include dp200_macros.cfg] + per-printer values: stepper_z
position_endstop, probe x/y/z_offset, extruder/heater_bed PID, plus Klipper's autosave block).
dp200_printer.cfg / dp200_macros.cfg = port-owned, contain NONE of the SAVE_CONFIG-able options
(Klipper rejects "conflicts with included value"). DEPLOY RULE: copy dp200_*.cfg freely; NEVER
overwrite the printer's printer.cfg (edit it in place if needed). The old printer_dp200.cfg is gone;
the printer's pre-split copy is printer.cfg.pre_split. Build/USB installers updated accordingly.
WEBCAM ARTIFACTS FIXED 10-20: the camera ends frames with junk instead of FF D9 -> ~22 % broken frames
(white bar / black flashes). The shim now repairs every frame on DQBUF (0 broken in 230). Lamp macros
LAMP_ON [BRIGHTNESS=], LAMP_OFF, LAMP_TOGGLE, M355 S/P added and tested. webcam.conf: WEBCAM_CTRLS.
WEBCAM + LAMP DONE 10-20 (unattended, no motion/heat): lamp = io:pwm7 ([output_pin lamp], on by default);
ustreamer MJPEG 640x480@15 passthrough as an rc.dp200 service (klipper user, v4l2_time32_shim LD_PRELOAD,
--device-timeout 5), Mainsail rotation 270, ~8 % of one core (stock YUYV way: 92 %). Load numbers in
hardware_notes. Tunables: /etc/dp200/webcam.conf + rc.dp200 restart-webcam.
10-26 NIGHT (unattended): 4GB-SD was 100 % FULL - nginx access.log 600 MB (Mainsail polls the webcam
snapshot ~1/s; no logrotate in the chroot) -> truncated snapshots, failed writes. Fixed: access_log off,
proxy_buffering off for /webcam/ (sites-available/mainsail deployed, nginx reloaded, 574 MB free, snapshot
OK). Check `df -h /mnt/sd` if anything odd happens. JTAG: CN3 = 3.3 V pins 1/20, signals pins 2-8 (via
RN3 330R), pin 8 = RESET (leave off), GND 10-19; no TAP answers on any pin (likely fused off); details
docs/jtag_prep.md. JTAGulator at V 0 (its state after every COM4 open) holds reset if pin 8 is connected.
Power button: GPIO5 pin 27; hardware cuts power after ~2 s hold; POWER page + dp200-powerkey.sh.
10-27 DAY (user present): NO MOTION since the boot hook - fixed. The stock app sets up the step engines
(+0x00/+0x10/+0x14/+0x2c, CFG bit4) and Klipper relied on that; smot_claim now does it (hardware_notes).
FM image rebuilt on the printer (tools/fm_rebuild.sh, old one kept as /opt/dp200/fm.bin.prev) and verified
after a hook boot. The JTAGulator was unplugged from CN3 (not the cause). The stock app ran once for the
comparison (heated nozzle to ~88 C / bed 50 C on its own); /DEBUG_MACHINE is back. Bed is ~20 mm lower than
this morning. regsnap_klipper/stock.txt + regdiff.txt are on the card in /mnt/sd. prebuilt/ rebuilt (zig) and
the USB payload rebuilt with the fixed fm.bin (release_check PASSED 21:12 printer time).
10-27 NIGHT (unattended): repo copy on the card (/mnt/sd/usr/src/dp200/klipper_port) refreshed from git;
all deployed files == repo (copied the missing dp200-wifi-from-stockdb.sh). USB payload rebuilt
(/mnt/sd/payload). NAND restore images (ECC-corrected nanddump of mtd0-6) in D:\DP200\backup\nand_images,
see docs/nand_restore.md - copy them to 2GB-SD /restore when that card is in. Clock: printer was in 2013;
dp200-start.sh now runs one-shot ntpd + hwclock -w (tested: Klipper unaffected by the jump). Logs: Klipper
and Moonraker rotate themselves (12 MB), stock /var/log 0.8 MB, NAND root 52 MB free - nothing else grows.
Large transfers to the printer with nc can truncate: always compare md5.
10-22 NIGHT (unattended, no heat/motion) - TEST PRINT PREP: action list docs/test_print_plan.md (work it
in order). Deployed dp200_printer.cfg: [exclude_object], [gcode_arcs], PRIME_LINE, PRINT_START re-primes
the 15 mm CLEAN_NOZZLE retract and ends at X100 Y100 Z10 (not over the front handle). Test files on the
printer: dp200_first_layer.gcode, dp200_box_20mm.gcode (tools/gen_test_prints.py). PrusaSlicer profile
install/slicer/. tools/rescale_sensor.py for the nozzle TC fit. OPEN: clutch state during printing (E
with clutch off never tested) = item 2. Nozzle read 26.3 C vs bed 19.0 C at room temp (nozzle ~7 C high?).
SD cards: 4GB-SD = working card (in the printer), 2GB-SD = rescue card (boot block now ALSO at sector 1).
DIP SD boot: mode 6 confirmed but the boot ROM hangs in SD init -> next session: user hooks a JTAGulator
to CN3 (JTAG) to see where. Boot ROM dump: D:\DP200\backup\bootrom (not in git). docs/sd_boot_plan.md.
10-22 RESCUE SD CARD (plan A WORKS, user present, spare 2 GB card; old contents backed up to
D:\DP200\backup\spare_sd_backup\spare_sd_card.tar): p1 ext2 "RESCUE" from sector 32768 with the stock root
(profile.stock, no hook, /etc/dp200-rescue marker, banner + PS1 "RESCUE# "), signed U-Boot block raw at
sector 0x80, kernel uImage raw at 0x800, /restore/{README.txt,mtd0.bin}. FINDING: U-Boot's SD driver sees
nothing (mmcinfo: 0 bytes on mvsdh0 AND mvsdh1, mmc rescan no help), so U-Boot can't load from the card.
Working start = NAND kernel + SD root: run load_nand; setenv bootargs console=ttyS0,115200n8 ${mtdparts}
root=/dev/mmcblk0p1 rootfstype=ext2 rootwait ${bootargs_mv61X0_other} synopGMAC_Mem.ethaddr=${ethaddr_sdh};
bootm ${downld_addr}. Booted: / = mmcblk0p1 ext2, NAND root mtd6 not attached (only stock /backup ubi1).
Consequence for plan B: U-Boot can't test for the card, so an automatic "SD if present" bootcmd isn't
possible from U-Boot; it has to be decided in Linux (initramfs / early /etc/profile) - open question.
DIP-switch SD boot of U-Boot (sector 0x80) still untested; doubtful if the boot ROM can read the slot either.
Full raw NAND dump with OOB: NAND_Dump/MX30LF4G18AC@TSOP48.BIN (T48 programmer) - source for restore images.
U-Boot env is NAND-only (env_nand.c), so the DIP-switch SD boot alone still boots the NAND root.
10-22 (user present): printer booted from U-Boot (run bootcmd; there is no "boot" command). WiFi was NOT
connected after killing the stock app early: the stock app is what joins the network. Now our own WiFi:
docs/wifi.md (dp200-wifi.sh import from karas.db, dp200_wifi.py over the control socket, screen pages
System->WIFI with scan/keyboard/hidden/forget). DON'T restart wpa_supplicant (driver then scans 0 BSS;
driver reload fixes it). Deployed live + tested by simulated taps (25/25) - real taps by the user pending.
Full boot path (dp200-start -> dp200-wifi.sh -> bind mount -> rc apply) not yet tested by a reboot.
10-21 NIGHT (unattended, PC only - printer parked at U-Boot):
- Cartridge format decoded from the stock app (tools/elfdis.py): raw pages -> fields, TotalFilament p0+28 (m),
  Used ePulse p2+4 (x 500/458.83 mm), six params p3, fuses = cleared bits in pages 6-7. docs/cartridge_chip.md.
- klipper/extras/dp200_cartridge.py drafted (read-only, threaded, CARTRIDGE_READ) + i2c-3 group klipper in
  dp200-mounts.sh + build scripts. NOT deployed/tested and NOT in the configs yet -> test with the user.
- TODO on the printer: deploy dp200-start.sh (gemstone kill fix) + dp200-mounts.sh, rebuild the USB payload
  (release_check.sh), then publish (tools/publish_to_sindoh.ps1) once the user agrees.
10-21 (user present, then unattended overnight):
- BED: sensor rescaled to surface (TC: 19/32/49/65 C at stock 24/40/60/80; surface = 0.824*stock - 0.77,
  verified 60=60); bed max_power 0.6 -> 1.0 (0.6 tripped verify_heater going to 80); bed PID 74.532/1.252/1109.592;
  nozzle PID 20.223/1.143/89.487 (max_power 0.6) - all SAVE_CONFIG'd. Use SET_IDLE_TIMEOUT for long soaks.
- UNLOAD done (548 mm); UNLOAD_FILAMENT now turns the heater off unless printing. Printer has NO filament.
- SD card was accidentally unlatched by the user (I/O errors, disappeared); reseated, e2fsck -f clean,
  e2fsprogs now in the chroot. dp200-start.sh now also kills the stock gemstone app (killall can't).
- CARTRIDGE: DS2465 (i2c-3 @0x18) -> DS28E22 (overdrive only). Full read-only dump: docs/cartridge_chip.md.
  Release latch = solenoid (4 s pulse). Cartridge is INSERTED (empty).
- U-BOOT: boot ROM loader prints at ~120000 baud, U-Boot/Linux 115200; boot ROM authenticates U-Boot.
- !! PRINTER LEFT AT THE U-BOOT PROMPT (no Linux, no heaters) so the stock app's heater self-test can't run
  unattended. Morning: power-cycle -> stock boot -> start Klipper (sh /mnt/sd/dp200/dp200-start.sh) as before.
10-20 EVENING (unattended, no motion/heat; user listed 8 tasks, order 1,7,2,3,4,5,6,8):
- (1) TOUCH UI DONE: install/display/dp200_screen.py = rc.dp200 service "screen" (root; fb0/event0 added to
  dp200-mounts.sh). Screens home/print/filament/preheat/move/system/error, confirm dialogs, STOP = 1 s hold,
  blank after 10 min idle (first tap only wakes). Backlight NOT controllable (fb blank only blanks; user OK).
  ~1 % CPU idle, 22 MB. test_dp200_screen.py 14/14 (simulated taps). Real presses untested -> with user.
- (7) KERNEL RESEARCH: docs/kernel_research.md (+ docs/kernel/ config + hw snapshot). Vendor LSP 2014 "shiloh",
  no public source; GPL request draft for the user; mainline port feasible but weeks (SD boot first).
- (2+3) INSTALLER -> NAND: mtd5 UBI volume "klipper" (ubi2, /klipper), stage-1 /etc/dp200-boot.sh,
  mtd5 backup to stick (nanddump -o -b) + restore in the remove stick. make_payload.sh = runtime image
  (134 MB gz / 374 MB, under the 160 MB check). DRY_RUN rehearsal mode. NOT flashed - needs user OK.
- (4) FORK: klipper/make_fork.sh -> branch sindoh-dp200 (3 commits on upstream 9cb9975), klipper/patches/.
  Both images build from it. Not pushed (user decides where).
- (5) MCU-SPEED WARNING FIXED: klipper/extras/upc_clockcheck.py + [upc_clockcheck] (live): withdraws the
  start-up warning after 30 s if the settled clock is fine (tested: 2 of 3 restarts warned, both withdrawn).
- (6) SD BOOT: docs/sd_boot_plan.md (U-Boot env has mv61X0_mmcboot: uImage raw @ sector 0x202, root mmcblk0p2
  ext2/3 - ext4 is a module). Needs a U-Boot prompt session with the user.
- (8) docs/INSTALL.md owner guide (preview).
- tools/serial_cmd.ps1 (COM3 fallback; the serial MCP server died mid-session), tools/fb_grab.py.
TOUCH PANEL INVESTIGATED 10-20 (docs/touchscreen_options.md): fb0 800x480 RGB565, touch BU21029 on
/dev/event0 (MT-ABS only, time32 input_event). KlipperScreen rejected (X11+GTK3 100-150 MB, no udev,
NAND space). Recommended: own Python framebuffer UI (install/display/fb_status_poc.py draws a status
screen; needs Debian python3-pil - installed - not the moonraker-env Pillow). ~0.4 s CPU per full
redraw after the RGB565 fix. Not autostarted. Panel is PORTRAIT 480x800 (draw portrait, rotate 90 CW;
user-confirmed); touch calibrated (axes swapped, x inverted, formula in the doc). NEEDS USER: backlight control. GuppyScreen (LVGL, armel rebuild) = alternative.
tools/serial_cmd.ps1 = console fallback when the serial MCP server is down; tools/fb_grab.py = screenshot.
LATER OPTIONS (user 10-19): (a) webcam (DONE 10-20, see above) - user saw stock mjpg_streamer at ~10 fps put a massive load on
the CPU last year (YUYV camera -> software JPEG); test load before choosing ustreamer / MJPEG mode.
(b) "split" setup: UPC firmware on the printer, klippy/Moonraker/Mainsail on a separate host (Pi/PC)
via the bridge's TCP ports (upctool bridge -f tcp:9100 -i tcp:9101) - fallback if the board is too slow.
Main path stays all-on-board.
BED HEATER VERIFIED 10-19 (40 and 60 C reached and held at the 0.6 cap). Klipper reads well above the
surface (TC: 24.6/18.5, 40.2/28.5 soaked, 60/45 at ~1 min, kapton). NEXT: re-measure 40/60 with the taped TC
and a 10 min soak, correct the bed table, then PID. Heaters were left OFF (user away).
Heater plan: bed smoke test 40 C (optional K-type thermocouple on the bed to verify the thermistor table),
bed PID_CALIBRATE 60, nozzle PID_CALIBRATE 210 (max_power 0.6 cap), SAVE_CONFIG.

To do: paper test (z_offset, Z position_endstop), probe X/Y offsets, PID
(nozzle and bed), travel limits and steps/mm check, LOAD/UNLOAD through
klippy, first print; step-rate root cause (UPC_STEP_STATS test), webcam
(ustreamer), transient probe offset (watch it); NAND root on mtd5 plus boot
from NAND, end-to-end USB install and OEM revert tests, other firmware
versions, user docs.

## Printer state right now
- Stock firmware booted (no NAND changes besides none - /DEBUG_MACHINE NOT set).
  The stock Sindoh app (UIManager + marvell_lspsdk elf) was killed for this boot.
- Our Klipper firmware is loaded on both UPC cores, unconfigured (drives nothing).
  `upctool bridge -f tcp:9100 -i tcp:9101` runs on the printer (log /tmp/bridge.log).
- Heater, clutch and fans are off; MCUs reset after the last test. The bed is about 120 mm below its top
  (Z switch; lowered 100 mm for the purge bin). X is at 229 mm (right of the switch at 216). The probe
  plunger is latched in (stowed, dsens8 = 1). Head at X 110 / Y 100, nozzle at Z 10.0 (config coords;
  the bed is 6.9 mm below the Z-switch height), ready for the paper test. Fresh filament (PLA) is LOADED to the nozzle; the purge bin is in.
- Lever xena46 is now un-taped (user's choice).
- Filament: the tube is cleared and fresh filament has been fed and retracted cold
  (tools/ktest_feed.py). The user is reattaching the bowden tube. **xena46 is the
  cartridge-detect lever** (tools/kwatch.py). Filament alone can hold it up (0 after
  the retract with nobody touching it), so it stays UN-TAPED and is used as the filament
  sensor (0 = present) for now. Watch for false triggers. Inlet -> gear-train exit ~100 mm.
- After a power cycle: stock app runs again (incl. its heater self-test). To get back:
  `cd /mnt/sd/dp200; killall UIManager; killall marvell_lspsdk_3dp_gemstone-debug_stripped.elf;`
  `./upctool --force load klipper_io.bin klipper_fm.bin; (./upctool --force bridge -f tcp:9100 -i tcp:9101 > /tmp/bridge.log 2>&1 &)`
  Safe stop at any time: `./upctool --force stop` (holds cores, all outputs off).

## Access
- Serial console: COM3 (CH341), 115200 8N1, root shell. Use the serial MCP tools.
  Keep each read short (<= 8 s) - a timed-out read drops the connection.
  BusyBox: `timeout -t N`, `devmem`, `nc -l -p PORT` (no -q). No base64; uudecode exists.
- Network: printer WiFi 10.10.0.21 (Fios-kVGD7). If it has no IP after boot:
  `udhcpc -i mlan0 -n -q -t 5 -T 2`. PC is 10.10.0.85 (Windows firewall blocks inbound,
  so push files: on printer `nc -l -p 9001 </dev/null > FILE &`, on PC
  `python -I tools/net_send.py 10.10.0.21 9001 FILE`).
- Files on printer: /mnt/sd/dp200/ (upctool, probe_*.bin, klipper_fm.bin, klipper_io.bin).

## Tools on this PC (absolute paths; previous session scratchpad)
S = C:\Users\TEMP~1.DES\AppData\Local\Temp\claude\D--DP200-backup\76623204-70a7-4636-98e6-f2dae1da921f\scratchpad
- Python libs (unicorn, capstone, pyelftools, cffi, jinja2, pyserial): set `PYTHONPATH=$S\pylib`
- zig cross compiler: `$S\zig\ziglang\zig.exe`
- Klipper master tree used for builds/tests: `$S\kl\klipper-master`
- Build both MCU images (Thumb):
  `python $S\tools\kbuild.py $S\kl\klipper-master D:\DP200\backup\klipper_port klipper\configs\dp200_fm.config $S\build\kfm -Wno-unknown-attributes -mthumb`
  (same with dp200_io.config -> $S\build\kio). Output klipper.bin must stay <= 16384 B
  (now FM 15824, IO 15920 - IO has ~460 B left).
- Emulator regression: `python $S\tools\kemu.py $S\kl\klipper-master $S\build\kfm\klipper.bin fm`
  (env TICK=40, T1INIT=0x9abcdef0)
- Config checks: tools/cfglint.py (Jinja templates), $S\tools\cfgcheck.py (pins vs dict)
- Hardware test clients (klippy msgproto over the TCP bridge), all in tools/:
  khost.py (base + read-only test), ksense.py (pin states), kreset.py, ktest_move.py,
  ktest_xyz.py, ktest_home.py (X/Y/Z homing via trsync), ktest_lvtoggle.py (probe toggle),
  ktest_fans.py, ktest_heat.py, ktest_unload.py, ktest_feed.py (cold E feed/retract + clutch),
  ktest_load.py (heat + slow feed/purge), ktest_probe.py (home all, deploy, dual-stop probe),
  ktest_zgo.py (paper test: nozzle to an exact Z, approach from below; uses kmove.py helpers), kwatch.py (watch all 96 inputs for changes),
  kbuttons.py (inputs via the buttons module, as filament sensors use them). Usage in each file's docstring.
  Pattern: `$env:PYTHONPATH="$S\pylib"; python tools\X.py $S\kl\klipper-master 10.10.0.21 ...`
- Stock analysis: tools/fmseq.py (emulate FM microcode cmds with real karas.db params),
  tools/stockparams.py, tools/dbcols.py, RE snapshot D:\DP200\backup\RE_analysis\DP200_RE_snapshot.zip
  (decompiled stock code; extracted copy at $S\snap\out).

## Verified on hardware
Timer1 timebase 395.8 MHz; Thumb; both Klipper MCUs over WiFi; E/X/Y/Z motion and directions;
X/Y/Z endstops (all 1 = triggered: xena42/43/44), X and Z homing via trsync; fans pwm1 hotend,
pwm2 part, pwm4 exhaust (pwm3 unused); nozzle heater (27->60 C, 27->210 C); thermistor tables;
filament sensor xena46 (0 = present); level probe dsens8 (0 = extended/deployed, 1 = latched in),
motorised toggle via X into the left wall works; heated unload retracts (filament snapped - old).

## Next steps (in order)
1. DONE 10-18: load with fresh filament (inlet -> nozzle ~518 mm; macros updated).
2. DONE 10-18: filament encoder = dsens7 (~16.5 mm/pulse). FM firmware with buttons is LOADED
   (klipper_fm.bin on the printer = buttons build; klipper_fm_nobtn.bin = previous). Verify encoder
   edges through buttons (tools/kbuttons.py) during the next filament move.
   Serial gotcha: send commands ending in a real "\n" in the data (the newline option sent a
   literal backslash-n).
3. DONE 10-18: Y homing (bed now at the Y switch, Y min).
4. Probe: Z trigger + repeatability DONE 10-18 (tools/ktest_probe.py; trips 1.28 mm before the Z switch,
   0.0006 mm repeat). STILL NEEDS THE USER: paper test for nozzle zero -> z_offset and
   position_endstop; X/Y offsets by the bed-edge method (plan in PROGRESS.md). Then bed_mesh.
5. PID_CALIBRATE once real klippy runs; bed heater test (pwm24/adc1; note stock SPMODE ifBedNotUsed=1).
6. Debian rootfs: this PC has NO WSL (enabling it needs admin + reboot). NEW 10-18:
   install/build_rootfs_native.sh + rootfs_inside.sh build it ON THE PRINTER. Kernel has no
   CONFIG_ARM_THUMB -> Debian armhf (Thumb-2) cannot run; the armhf tree was removed (verified).
   NOW: Debian 13 trixie ARMEL (debuerreotype dist-arm32v5; bookworm armel is no longer published),
   sha256 verified, at /mnt/sd/rootfs_armel.tar.gz, extracted to the SD root (/mnt/sd). BUILD DONE
   2026-10-18 (EXIT 0; log /mnt/sd/build_rootfs.log): /usr 1.5 GB, /home 408 MB; Klipper + Moonraker
   (SKIP_CYTHON) + Mainsail; upctool built natively; UPC firmware built with Debian arm-none-eabi-gcc:
   /mnt/sd/opt/dp200/fm.bin 11580 B, io.bin 11764 B (much smaller than zig). LOADED on the cores now
   and verified read-only with khost.py (identify/reset/clock/endstops/both ADCs OK); motion/heat
   not re-tested on them yet. TCP bridge running (upctool from /mnt/sd/dp200).
   DONE 10-18: stack started by hand (`setsid sh /mnt/sd/dp200/dp200-start.sh </dev/null`):
   bridge/klipper/moonraker running, klippy "Printer is ready" (Klipper 9cb9975, both MCUs gcc
   14.2.1, whole printer.cfg + macros accepted), Moonraker :7125 no warnings, **Mainsail at
   http://10.10.0.21/**. Live: nozzle 24.9 C, bed 22.6 C, lever not detected, encoder enabled.
   Moonraker memavail shows 0 (kernel 3.2 has no MemAvailable). Nothing homed/heated via Klipper yet.
   Hook NOT installed: a reboot brings back the stock firmware. Emergency stop: M112 in Mainsail, or
   on the serial shell `chroot /mnt/sd /etc/dp200/rc.dp200 stop` (holds the UPC cores, outputs off).
   G28 X/Y/Z through klippy DONE 10-18 (via Moonraker API; X216 Y5.5 Z3.1; then G1 Z10).
   USB installer (user goal: plug-in stick flash for other owners): docs/usb_installer.md +
   install/usb/ (install/remove .sh, pack_she.sh, make_payload.sh). The .she packing is verified
   on the printer; not run end-to-end yet. OEM update format decoded (auto_update.sh, update.sh).
   BED MESH (10-18): probe wrappers (BED_MESH_CALIBRATE/PROBE/PROBE_ACCURACY deploy->base->stow),
   [homing_override] stows a deployed pin before Z homing, LV_PROBE_CALIBRATE(+_SAVE) for z_offset.
   Works on hardware: PROBE centre z=4.437; 3x3 and 3x5 meshes done. The mesh shows a band at
   Y~105-142 about 1.5 mm high across all X (other rows agree within 0.1) - user to check the bed
   for an object / lifted plate. STEP-RATE LIMIT FOUND: UPC engines lose steps above ~20k steps/s
   (Z: ok to 19.2k, 25.6k lost 1.8 mm) -> max_z_velocity 5, max_extrude_only_velocity 40.
   Klipper parser gotcha: macro names with digits mid-name (_DP200_X) are "Malformed command";
   renamed to _SINDOH_*; tools/cfglint.py now checks names.
   INTERNAL-STORAGE FIRMWARE (user: stock printers have no SD card): docs/internal_firmware_plan.md
   (mtd5 "recovery" 200 MB UBI, unused by boot -> candidate root; size measurement next).
   OVERNIGHT 10-18/19 (no motion): (1) runtime image measured: 367 MB raw, 119 MB gzip -> fits mtd5
   (docs/internal_firmware_plan.md, install/nand/). (2) Step-limit diagnostics: gpio.c smot_pulse now
   counts pulses + "busy hits" (pulse requested while engine +0x64 bit8 busy) and waits for the running
   pulse instead of overwriting it; new MCU cmd upc_step_stats (FM only); klipper/extras/upc_stats.py
   gives G-code UPC_STEP_STATS; printer_dp200.cfg has [upc_stats]. zig builds FM 15804 / IO 15920 B,
   emulator regression OK. gcc build ON THE PRINTER done: /mnt/sd/opt/dp200/fm_stats.bin (11756 B).
   DEPLOYED 10-19 (user approved): fm.bin = stats build (old: fm_nostats.bin), upc_stats extra,
   printer.cfg with [upc_stats] + PAUSE/RESUME/CANCEL_PRINT; UPC_STEP_STATS works (all 0, no motion).
   Mainsail: missing-macro banner gone; MCU-speed warning = cosmetic start-up artefact (hardware_notes);
   webcam broken (stock mjpg_streamer, plan ustreamer). OEM-revert stick: remove .she + OEM files
   (docs/usb_installer.md). Monitor Mainsail (built-in browser, http://10.10.0.21/) during work.
   (History: the deploy was first blocked by the permission classifier.) To deploy: copy
   upc_stats.py to /mnt/sd/home/klipper/klipper/klippy/extras/, the repo printer_dp200.cfg to
   printer_data/config/printer.cfg, fm_stats.bin over /opt/dp200/fm.bin (keep fm.bin as
   fm_nostats.bin), then `chroot /mnt/sd /etc/dp200/rc.dp200 restart-klipper` (setsid, </dev/null).
   Test (needs motion, user present): G28, G1 Z at 8 mm/s (temporarily raise max_z_velocity), then
   UPC_STEP_STATS: busy_hits > 0 => engine overwrite (fixed by the wait); 0 => motor stall.
   NEXT (with the user at the printer): LV_DEPLOY/PROBE, paper test
   (PROBE_CALIBRATE), PID_CALIBRATE, LOAD/UNLOAD macros, then hook_install.sh for boot.
   Hook NOT installed yet. The touchscreen appBrowser was killed for RAM (reboot restores it). Lessons: set the clock first
   (boots 2013); chroot needs its own /dev (stock nodes are 0660 root - dp200-mounts.sh); never run
   the build as a plain background job on the serial console (it stole tty input and got SIGTTOU).
   PC route build_rootfs.sh still says bookworm/armhf - must become trixie/armel.
   SD card: ext4, 3.6 GB, 2.9 GB free; it already holds alpine/ + alpine-minirootfs-3.9.0 (an earlier
   attempt, too old for Klipper), auto_update.sh (stock!) and pa6170_rodin_nand.bin (NAND backup -
   never delete). Stock curl 7.40/OpenSSL 1.0.1c: HTTPS works only with -k (no CA bundle).
   Then the hook (install/printer/hook_install.sh).
7. Camera: stock mjpg_streamer (:8080) leaks threads; /app/recovery.check.sh (started by /etc/profile
   even in DEBUG mode) restarts lighttpd every minute because of it (see hardware_notes). dp200-start.sh
   now stops that watchdog. Consider ustreamer from Debian for the Mainsail webcam.
Ask the user before any motion or heating; describe what to expect first.
