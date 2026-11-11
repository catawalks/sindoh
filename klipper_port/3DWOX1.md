# 3DWOX 1: first hardware checks (2026-11-11)

First run of the DP200 port's tools on a Sindoh 3DWOX 1. Until now the
3DWOX 1 was only known from its update files
([docs/other_models.md](docs/other_models.md)). Everything here was done on
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

- **Root shell:** the top-level `_update_rodin_up/update.she` (AES,
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
  (the route in HANDOFF.md). The already-running `udhcpc` keeps the Wi-Fi
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

| Measurement | DP200 (hardware_notes.md) | This 3DWOX 1 |
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

`tools/khost.py` (read-only), over Wi-Fi through the bridge:

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
hardware_notes.md is not tested here).

## Open on the 3DWOX 1

- **Z switch height against the nozzle: inconclusive.** By eye the switch
  triggered with about 13 mm left to the nozzle (DP200: about 2.3 mm), but
  the bed plate had been removed for the test. Repeat with the plate on,
  then do the paper test.
- **Z travel:** roughly 200 mm bottom to switch, based on a by-eye 40 mm
  after the stall. Not measured.
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
