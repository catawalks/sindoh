# 3DWOX 1: first hardware checks (2026-11-11)

## Where this comes from

**None of this was measured by us.** We have no 3DWOX 1; everything on
this page comes from two other owners and their printers, and none of it
has been repeated on our own machines (the dev DP200, a Stanley Model 1
converted to DP200Q, and the work DP200): **Fredrik Gustafsson** (GitHub
`jagheterfredrik`, 2026) and **Sebastian Schmidt** (GitHub `yath`, 2021).
Sources:

- **Sections "The printer" to "Open on the 3DWOX 1":** his notes from
  [catawalks/sindoh#1](https://github.com/catawalks/sindoh/pull/1)
  (2026-11-11), brought in as his commit 8b51091. Only the file location
  and two links were changed.
- **"Later findings from klipper-sindoh":** read by us on 2026-11-20 from
  his repo [jagheterfredrik/klipper-sindoh](https://github.com/jagheterfredrik/klipper-sindoh)
  (2026-11-13: `docs/model_audit.md`, `klipper/config/3dwox1/printer.cfg`,
  `image/stick/launch.sh`), and summarized in our words.
- **"Sebastian Schmidt's 2021 dumps":** the files in `3dwox1_2021/` of
  catawalks/sindoh (`dmesg.txt`, `proc_partitions.txt`, `df.txt`,
  `proc_version.txt`, the README's hardware notes), from his repo
  [yath/sindoh](https://github.com/yath/sindoh), which catawalks/sindoh was
  forked from. They are from his 3DWOX 1 (the repo is titled "Sindoh 3DWOX
  1"), on the 2018 RODUP kernel build.
- Lines marked **(our note)** are our own reading or inference from those
  sources, not measurements.

## His first checks

First run of the DP200 port's tools on a Sindoh 3DWOX 1. Until now the
3DWOX 1 was only known from its update files
([other_models.md](other_models.md)). Everything here was done on
one printer in one evening, on the stock firmware, with nothing installed
and no flash writes. A power cycle returns the printer to stock.

**Short version:** the prebuilt DP200 probe and Klipper firmware
(`prebuilt/`, built 2026-10-27) run unchanged on the 3DWOX 1. Endstops,
X/Y/Z motors, the part-cooling fan and both thermistor inputs behave as on
the DP200. Differences found so far are on the Linux side (access, DHCP,
port 9100, free space), plus a Z stall at 5 mm/s.

## The printer

| Item | Value |
|---|---|
| Firmware | `RODUP_200730_4` (`/snapshot_version.sh`), `RODIN_SUB=U` |
| Kernel | `3.2.0-g67a8e16` (the build the installer checks for) |
| `/app/upc.ko` | present; `/dev/upc0`, `/dev/upc1` exist after `module_load.sh` |
| Root | `ubi0:filesystem / ubifs`, 258.3 MB, **34.5 MB free** (DP200: 54 MB) |
| microSD | none (`/dev/mmcblk*` absent) |
| | **(our note)** this only says no card was seen; whether the mainboard has a slot (empty, or not fitted) is not known |
| Network | Wi-Fi (`mlan0`); `eth0` not connected |

`/proc/mtd`: mtd0-mtd6 have the DP200's names and sizes (mtd5 `0c800000`
"recovery", mtd6 `12660000` "filesystem", erase size `00020000`). Two more
entries appear, `mtd7` "filesystem" and `mtd8` "backup", with erase size
`0001f000`. They look like the UBI volumes of mtd6 and mtd4 exposed as MTD
devices (not confirmed). The installer's checks don't look at them.

NAND backup before any test: `nanddump -o -b` of mtd0, 1, 3, 4, 5, 6 to a
USB stick. mtd5 came out 2 erase blocks short and mtd6 5 short (bad blocks
omitted).

## Access and the stock boot (differs from the DP200 notes)

- **Root shell:** `3dwox1_2021/_update_rodin_up/update.she` (AES,
  `sindoh024601779U`) starts `nc -llp 2323 -e /bin/sh`. Files were pushed
  with TFTP to `/tmp`.
- **`/DEBUG_MACHINE` is not needed, and is a trap on Wi-Fi.** In this
  firmware's `/etc/profile` the flag only skips `UIManager` and
  `reset_monitor.sh`. `UIManager` is what starts
  `marvell_lspsdk_3dp_gemstone-debug_stripped.elf`, and that binary is what
  starts `udhcpc` for `mlan0`. `wpa_supplicant` starts either way, so a
  `/DEBUG_MACHINE` boot joins the Wi-Fi network but never gets an address.
  Ethernet (`ifplugd` on `eth0`) is unconditional.
- **What was done instead:** on a normal boot,
  `killall UIManager; killall marvell_lspsdk_3dp_gemstone-debug_stripped.elf`
  (the route in [HANDOFF](https://github.com/catawalks/sindoh-klipper/blob/main/docs/history/HANDOFF_2026-10-18_to_11-04.md)). The already-running `udhcpc` keeps the Wi-Fi
  lease. `reset_monitor.sh` looks for a different binary name and does
  nothing; there is no `/dev/watchdog`.
- **Port 9100 stays taken.** The surviving `udhcpc` inherits the motion
  binary's listening socket, so `upctool bridge -f tcp:9100` fails with
  "Address in use". The bridge ran on `tcp:9110` / `tcp:9111`, with the port
  numbers changed in copies of `khost.py`, `kmove.py` and `ktest_move.py`.
- **Stick handling order:** `media.connect` (and so `update.she`) runs at
  line 31 of `/etc/profile`, before `wpa_supplicant` and before the
  `/DEBUG_MACHINE` test. A stick script that waits for a touch holds up the
  rest of the boot.

## Probe firmware (`upctool load probe_io.bin probe_fm.bin`, `probe 2`)

| Measurement | DP200 (sindoh-klipper `docs/hardware_notes.md`) | This 3DWOX 1 |
|---|---|---|
| FM / IO CP15 ID | `0x56051012` / `0x56151012` | same |
| Control register, start CPSR | `0x1f74`, `0x600000d3` | same |
| Thumb | OK | OK on both cores, 0 aborts |
| Timebase | Timer1 `0x08001144`, down, 395.76-395.85 MHz | same register, down, 394.86 MHz |
| Inputs at rest | XIRD `0x10140000`, XIRD1 bit 10 = 1 | same |
| ADC sel 0 (nozzle), raw | 973-984 | 980 |
| ADC sel 1 (bed), raw | 838 at room temperature, 771 cooling | 754, then 790 an hour later |

The bed value rose from 754 to 790 over about an hour with no heating, so
the first reading was most likely a bed that was still warm. No thermometer
comparison was done.

Endstops by hand, probe running (XIRD1):

| Switch | Bit | Seen |
|---|---|---|
| X home | 10 | 1 with the head parked, 0 after sliding the head away |
| Y home | 11 | 1 while the axis was held at the back, 0 after |
| Z home | 12 | not reachable by hand; see the Z test below |
| Door, cartridge lever | - | no change in XIRD / XIRD1 (may not have been operated) |

## Klipper firmware (`prebuilt/klipper_io.bin`, `klipper_fm.bin`)

`tools/khost.py` from sindoh-klipper (read-only), over Wi-Fi through the bridge:

- identify OK on both cores (`upc_fm`, `upc_io`), no shutdown;
- clock FM 396.21 MHz, IO 395.80 MHz over 10 s;
- RTT about 200-225 ms (DP200 notes: 50-130 ms);
- xena42, 43, 44, 46 all 0 (head off the X switch, cartridge present);
- nozzle raw 982.0, bed raw 790.2.

Motion and outputs (owner watching the printer):

| Test | Command / settings | Result |
|---|---|---|
| Z up 5 mm | `ktest_move.py Z 0 5 3` (REF 0.65) | moved up |
| X 10 mm | `ktest_move.py X 0 10 10` (REF 0.425) | moved as expected |
| Y 10 mm | `ktest_move.py Y 0 10 10` (REF 0.575) | moved as expected |
| Part-cooling fan | `pwm2`, software PWM 50 %, 10 ms cycle, 3 s | ran |
| Z up, 6 x 20 mm at 5 mm/s | `kmove.Motion.guarded`, no ramp | **stalled**: the bed followed about 2 of 6 stages, with an odd noise; the firmware counted all steps |
| Z up at 3 mm/s | guarded stages of 10, 20, 10, 2 and 1 mm | moved cleanly, about 164 mm in total |
| Z endstop | guarded move, stop on xena44 = 1 | triggered; the stage was cut at 0.57 of 1 mm, so stop-on-trigger works |

The stock app had run on this boot before it was killed, so the step
engines were set up by stock as well as by the firmware (the 10-27 case in
sindoh-klipper's hardware_notes.md is not tested here).

## Open on the 3DWOX 1

- **Z switch height against the nozzle: inconclusive.** By eye the switch
  triggered with about 13 mm left to the nozzle (DP200: about 2.3 mm), but
  the bed plate had been removed for the test. Repeat with the plate on,
  then do the paper test.
- **Z travel: about 198 mm from the switch to the mechanical bottom**
  (DP200: ~195 mm). Measured by step count at 3 mm/s, starting with the
  bed on the switch (xena44 = 1): 190 mm in five stages, then 1 mm steps
  with pauses. The bed followed every step to 198 mm, stopped on the next
  one and buzzed after that, so the end is between 198 and 199 mm. One
  run, bed plate removed. `position_max: 194` is about 4 mm short of this
  printer's travel.
- **Z speed:** 5 mm/s from a standing start stalls; 3 mm/s works. Not
  tried: 5 mm/s with acceleration (as klippy does it), or a higher Z REF.
- **Not tested:** extruder motor and clutch, heatsink and exhaust fans,
  lamp, heaters, thermistors against a thermometer, the LV probe, the
  filament encoder, door and cartridge lever inputs, cartridge chip.
- **Installer:** not run. It would need the `_update_rodin_up` folder and
  AES packing, a firmware pattern that matches `RODUP_...` (the script reads
  `RODIN_...`), and it has less free space to work with (34.5 MB).
- **Persistent Klipper boot:** the boot hook uses `/DEBUG_MACHINE`. On this
  firmware that leaves Wi-Fi without DHCP unless the hook starts `udhcpc`
  itself; check what the DP200 hook does.

## Later findings from klipper-sindoh (2026-11-13)

From his repo (see "Where this comes from"); his findings unless marked.

- **The 11-12 "2x travel" was his own firmware build, not the printer.** He
  built `fm.bin` from a copy of our port that had the step-batching option
  on but not the matching `src/stepper.c` change, so every move ran at
  twice the distance. His audit therefore marks these as **to retest at
  1:1**: the Z stall at 5 mm/s, the "violent" X/Y homing, and the 198 mm Z
  travel (measured by step count). The 11-11 tests above used our
  `prebuilt/` firmware (2026-10-27), which predates that build. **(our
  note)** Whether the 11-11 Z stall was affected is not clear from his
  notes.
- **Motor current per unit.** His stock karas.db has
  `MOTOR_PWM_{X,Y,Z,E}OFFSET` = 99 on every axis, so stock drives the
  current reference at (100 + 99) / 200 = 0.995. The 11-11 tests ran with
  the dev DP200's values (Z 0.65, X 0.425, Y 0.575). **(our note)** Too low
  a current is another candidate for the Z stall. Our installer now reads
  these offsets from each printer's own karas.db (row `NO=4`, the row the
  stock app uses: [stock_routines.md](https://github.com/catawalks/sindoh-klipper/blob/main/docs/stock_routines.md)) into
  `dp200_machine.cfg`.
- **A different stepper driver board.** His unit has Trinamic TMC2224
  drivers, not the dev DP200's Allegro A4982. The stock app sets them up
  over a UART on `/dev/ttyS2` (CHOPCONF `0x14010053` = 16 microsteps;
  GCONF `0x141`, `I_scale_analog` set, so the VREF pin is believed to still
  scale the current). It tells the boards apart by GPIO bank 2 pin 0.
  His audit says either board may be in either model; **(our note)** that
  is his guess, and we treat the 3DWOX 1 (RODUP_) as its own line with
  possibly its own mainboard. Klipper ran unchanged on his unit
  only because the stock app had already configured the drivers; a boot
  that skips the stock app (our NAND install, `/DEBUG_MACHINE`) leaves a
  TMC2224 at its power-on defaults. **(our note)** Our
  [hardware_notes.md](https://github.com/catawalks/sindoh-klipper/blob/main/docs/hardware_notes.md) has `ttyS2` as the link to the
  power-management MCU (9600 8N1), which contradicts this; one of the two
  needs checking on a printer.
- **His per-unit values** (from his 3DWOX 1 `printer.cfg`, examples only):
  Z switch height 2.725, probe `z_offset` 2.711, extruder PID
  Kp 14.565 / Ki 1.566 / Kd 33.865 (210 C, `max_power` 0.6); bed PID not
  calibrated. He ran gentler limits: `max_accel` 500, X/Y homing 50 mm/s,
  `max_z_velocity` 3, Z homing 3 mm/s.
- **Stock motion values he read:** stock backs Z off the switch at about
  0.39 mm/s (at most 1.26 mm), so he uses `second_homing_speed` 0.5 and
  `homing_retract_dist` 2 (ours: 2 mm/s and 5 mm); stock ramps its X/Y
  homing seek at about 4500 mm/s2, so he raised `max_accel` to 3000 (ours:
  1500). Not tried on our printers.
- **Model tag:** `RODUP_` in `/snapshot_version.sh` = 3DWOX 1, `RODIN_` =
  DP200/DP201. His start script and screen app name the model from it.
- **Starting Klipper too early breaks stock Wi-Fi:** killing the stock app
  about 5 s after it starts leaves the radio mid-setup (no access points in
  scans, no Wi-Fi). Waiting until `mlan0` has an address first (up to
  60 s) fixed it on his unit.
- **His install route** runs Klipper from a Debian image on a USB stick
  (loop-mounted, nothing written to the flash). **(our note)** Not our
  direction: the end-goal installer stays on the printer, and the USB port
  stays free for storage and the accelerometer.

## Sebastian Schmidt's 2021 dumps (a second 3DWOX 1)

Read by us on 2026-11-20 from `3dwox1_2021/` in this repository (see "Where this
comes from"); the facts are his unit's, the comparisons ours.

- **Kernel:** `3.2.0-g67a8e16 #20 SMP PREEMPT Wed Jan 24 16:15:58 KST
  2018`, the same build as in Sindoh's RODUP_220111_1 update (the DP200's
  is `#6`, 2016, from the same source).
- **Partitions: the DP200's.** The kernel command line (from U-Boot's
  environment) has exactly the DP200's `mtdparts`: kernel 8 MB, u-boot-env
  128 KB, bbt 512 KB (read-only), boot-logo 1 MB, backup 8 MB, recovery
  200 MB, filesystem the rest (294 MB); root `ubi0:filesystem`, and
  `ubi1:backup` mounted on `/backup`. `/proc/partitions` lists
  mtdblock7 (288,176 KB) and mtdblock8 (7,192 KB): **(our note)** the
  gluebi devices of the two attached UBI volumes, so Fredrik's mtd7/mtd8
  are the same thing and not a hardware difference.
- **Root space then:** 264,580 KB, 57,452 KB free (on the firmware of
  2021); Fredrik's unit on RODUP_200730_4 had 34.5 MB free.
- **SD hosts:** the kernel registers two SDHCI controllers (`mmc0`,
  `mmc1`, `sdhci-gogin`), with no card found. **(our note)** So the SoC's
  SD hosts are enabled on this board too; whether a slot is fitted is
  still not known.
- **Serial ports:** `ttyS0`-`ttyS3` (16550A, 0xf8060000-0xf8063000), as on
  the DP200. What is wired to `ttyS2` is still the open question above.
- **Other hardware** (README): 800x480 panel on `/dev/fb0`, BU21029GUL
  touch on `/dev/event0`, Wi-Fi 1286:2040, webcam 0c45:6341: all as on the
  DP200.
