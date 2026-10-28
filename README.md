# Klipper on the Sindoh DP200

Klipper runs on the printer's own SoC (Marvell 88PA6170): klippy, Moonraker and
Mainsail on the Linux cores, and the Klipper MCU firmware on the two UPC
real-time cores that used to run Sindoh's motion and heater microcode.
Nothing is flashed: Debian lives on a microSD card, and one line in
`/etc/profile` plus a flag file (both reversible) switch the boot over.

```
 Linux (stock kernel 3.2) ── Debian chroot on microSD ─────────────────────┐
 │ nginx+Mainsail :80 ── Moonraker :7125 ── klippy                         │
 │                                      ├── /tmp/klipper_upc_fm ─┐         │
 │                                      └── /tmp/klipper_upc_io ─┤ upctool │
 └──────────────────────────────────────────────────────────── bridge ─────┘
                       DTCM rings (shared 256 KiB TCM, /dev/mem) │
   UPC FM core (/dev/upc1): steppers, endstops, motor current    │
   UPC IO core (/dev/upc0): heaters, fans, thermistors      ─────┘
```

## Layout

| Path | What |
|---|---|
| `common/` | Hardware register map and IPC layout, shared by every component |
| `host/upctool.c` | Linux tool: `load`, `stop`, `safe`, `probe`, `bridge`, `info`, `dump` |
| `upc_fw/probe/` | Hardware probe firmware (passive; run this first) |
| `klipper/src/upc/` | Klipper MCU port for the UPC cores; `install_port.sh` adds it to a Klipper tree |
| `klipper/configs/` | Build configs for each core (`dp200_fm`, `dp200_io`) |
| `klipper/config/printer.cfg` | The user's file: includes the two below, holds per-printer calibration (Z endstop, probe offsets, PID) and Klipper's SAVE_CONFIG block. Never overwritten by updates |
| `klipper/config/dp200_printer.cfg` | Hardware definition (two MCUs, steppers, heaters, sensors, fans, PRINT_START/END); replaced on updates |
| `klipper/config/dp200_macros.cfg` | Stock-derived macros (load/unload, clean, probe deploy/stow, bed mesh wrapper); replaced on updates |
| `install/` | Debian rootfs builder, SD writer, boot hook, service script |
| `docs/hardware_notes.md` | Facts the port depends on, with evidence and open items |
| `docs/other_models.md` | What Sindoh's updates show about the 3DWOX 1, 2X, 1X, 7X and 30X (SoC, keys, USB folders) |
| `prebuilt/` | Verified test builds (see below) |
| `tools/` | Development tools used for verification (zig build, Unicorn emulators) |

## What has been verified (without hardware)

* **upctool** cross-compiles as a static ARMv7 binary. A scan of the output found no d16–d31 or NEON use in ARM-mode code (PJ4 is VFPv3-D16).
* **Klipper port** builds against current Klipper master for ARMv5TE in Thumb mode: FM image 15,904 B and IO image 15,920 B, both under the 16,384 B ITCM.
  Both images were booted in a Unicorn ARM946 emulator and driven over the DTCM rings with klippy's own `msgproto`:
  * `identify` and the data dictionary work.
  * 25 queued steps produced exactly 25 hardware step-engine pulses with the direction bit set, and `stepper_get_position` returns 25.
  * The endstop reads both levels.
  * ADC reports are exact for both mux inputs (8×600 and 8×300), and stay stable at Klipper's real heater sampling rate.
  * A heater pin switches block 5 to its static level.
* **Probe firmware** boots in the emulator on both cores and writes a complete report, which decodes correctly.
* **The printer config** (now `dp200_printer.cfg`): all 26 pin references resolve in the real data dictionaries of the two builds.
* **On the real printer** (see docs/hardware_notes.md "Measured on the printer"):
  * the probe firmware ran on both cores;
  * Timer1 was found and measured (395.8 MHz) and is now the Klipper timebase;
  * Thumb support is confirmed;
  * the Klipper firmware runs on both UPC cores, and identify, clock, endstop reads, thermistor reads and `reset` all work from a PC over WiFi through `upctool bridge -f tcp:9100 -i tcp:9101`.
* **Motion:** an extruder test (460 steps each way) turned the motor smoothly forward and back, which confirms the step-engine pulses, DIR, driver enable and motor-current PWM.
* **Real klippy on the printer (2026-10-18):** the Debian trixie armel root was built on the printer with `install/build_rootfs_native.sh`. `dp200-start.sh` brings up the gcc-built UPC firmware, klippy ("Printer is ready" with the full printer.cfg and macros), Moonraker and Mainsail on port 80. Motion, homing, fans and heaters were verified earlier with the test clients (docs/hardware_notes.md), not yet through klippy.
* **Not verified yet:** G-code motion/homing/heating through klippy, PID tuning, the boot hook, and the PC-side `build_rootfs.sh` (it needs a Linux PC).

## Bring-up order

Do the steps in order and don't skip the probe. Have someone at the power switch for every step that can move or heat anything.

**0. Access.** Get a root shell on the stock firmware, over ssh (dropbear) or the serial console (ttyS0 115200, probably CN4).

**1. Probe (no installation needed).** Copy `prebuilt/upctool` and `prebuilt/probe_*.bin` to the printer, e.g. on a vfat USB stick at `/mnt/sda1`, then:
```sh
touch /DEBUG_MACHINE && reboot      # boot without the Sindoh app
cd /mnt/sda1
./upctool load probe_io.bin probe_fm.bin
./upctool probe 2                   # repeat while pressing each endstop by hand
./upctool stop
rm /DEBUG_MACHINE                   # back to stock on next boot
```
Each core prints `[UPC probe] .. core alive` on the serial console. From the report:
* pick a counter that only goes up (or only down) at a steady rate; its rate becomes `CONFIG_CLOCK_FREQ` and its address `CONFIG_UPC_TIMER_ADDR`;
* check that `thumb` reads `OK` (required);
* note the endstop bits and the ADC raw values at room temperature.

Record the results in `docs/hardware_notes.md` and in `klipper/configs/*.config`.
If no counter moves, Timer1 and Timer2 were loaded by the FM probe: look at whether they change after loading, and set `CONFIG_UPC_TIMER_START`.

**2. Build the SD card** on a Linux PC or WSL2. It needs `debootstrap qemu-user-static binfmt-support gcc-arm-none-eabi git python3`:
```sh
sudo install/build_rootfs.sh ./dp200-rootfs
sudo install/write_sd.sh ./dp200-rootfs /dev/sdX
```
This builds the UPC firmware from the same Klipper checkout that klippy uses, so their versions match.

**2b. No Linux PC? Build it on the printer.** The SoC is ARMv7, so apt and pip run natively in a chroot on the SD card (`install/build_rootfs_native.sh` + `install/rootfs_inside.sh`). Copy two files to the card: Debian's official **trixie armel** rootfs (debuerreotype artifacts, branch `dist-arm32v5`, `trixie/oci/blobs/rootfs.tar.gz`; check its sha256 against `image-manifest.json`) and this repository as `klipper_port.tar.gz`. It has to be armel: the vendor kernel has no `CONFIG_ARM_THUMB`, and Debian armhf binaries are Thumb-2, so they fail with "Exec format error". The printer boots with a 2013 clock, so set it first (`date -s`). Then, with the printer online:
```sh
sh build_rootfs_native.sh /mnt/sd/rootfs_armel.tar.gz /mnt/sd/klipper_port.tar.gz
```
The PC route (`build_rootfs.sh`) has the same constraint and needs `--arch=armel` (not yet changed there).
The stock curl has no CA bundle, so download on the PC and push with `tools/net_send.py`. The script leaves existing files on the card (NAND dump, `dp200/`, `auto_update.sh`) alone. If the gcc-built UPC image is over 16 KiB, it falls back to the verified `/dp200/klipper_*.bin`.

**3. Install the hook** (on the printer, SD card inserted):
```sh
sh /mnt/sd/dp200/hook_install.sh && reboot
```
After the reboot, Mainsail is on `http://<printer-ip>/`.
For logs and control:
```sh
chroot /mnt/sd /etc/dp200/rc.dp200 status
tail /mnt/sd/home/klipper/printer_data/logs/klippy.log
```
To return to the stock firmware:
```sh
sh /mnt/sd/dp200/hook_remove.sh && reboot
```

**4. Outputs first, motion second.** With the belts loose or the motors unplugged:
1. Check `QUERY_ENDSTOPS` and fix polarity in printer.cfg.
2. Check fans with `SET_FAN_SPEED` / `M106`.
3. Check motor-current PWM.
4. Use `STEPPER_BUZZ STEPPER=stepper_x` to confirm one step pulse per step and the direction.

Then home each axis on its own.

**5. Heaters last** (see Safety): run `PID_CALIBRATE` at a low target, check both thermistors against a reference thermometer, and only then raise `max_power`.

## Safety

* The stock firmware's heater protection is gone. Klipper's protections replace it:
  * `max_temp`/`min_temp` range checks on the MCU (`ADC out of range` shutdown);
  * `verify_heater`;
  * the MCU turns a heater off on its own if klippy stops updating it (`max_duration`).
* `upctool stop` (also run by `rc.dp200 stop`) holds both UPC cores in reset and forces every PWM output low and every stepper driver off. Put it on a key you can reach.
* The thermistor tables and endstop polarity are unverified. Until step 5 passes, power the heaters through a fuse or a current-limited supply, as the plan already says.
* A firmware exception on a UPC core turns its outputs off and shows `state FAULT` in `upctool info`.

## Known limitations

* Each step is one hardware engine pulse, so very high step rates depend on how quickly the engine accepts a new move (probe item 3).
* Hardware-PWM `cycle_time` is ignored; the stock periods per block are used.
* The IO image is close to the 16 KiB limit. Keep optional Klipper features disabled in `dp200_io.config`.
* SmartIC cartridge, clutch/solenoid filament handling, the multi-cartridge "C" axis, the LV sensor and the touchscreen UI are not handled yet (Phase 4/5 of the plan).
