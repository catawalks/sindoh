# Klipper on the Sindoh DP200

Klipper runs on the printer's own SoC (Marvell 88PA6170): klippy, Moonraker
and Mainsail on the Linux cores, and the Klipper MCU firmware on the two
UPC real-time cores that used to run Sindoh's motion and heater microcode.
A touch screen app replaces Sindoh's panel UI.

```
 Linux ── Debian root ─────────────────────────────────────────────────────┐
 │ nginx+Mainsail :80 ── Moonraker :7125 ── klippy        touch screen app │
 │                                      ├── /tmp/klipper_upc_fm ─┐         │
 │                                      └── /tmp/klipper_upc_io ─┤ upctool │
 └───────────────────────────────────────────────────────────────┼─────────┘
                       DTCM rings (shared 256 KiB TCM, /dev/mem) │
   UPC FM core (/dev/upc1): steppers, endstops, motor current    │
   UPC IO core (/dev/upc0): heaters, fans, thermistors      ─────┘
```

There are two ways it is installed today:
- **USB stick install (usable now):** our runtime on the stock root, under
  Sindoh's stock 3.2 kernel. No hardware changes; removable.
  [docs/INSTALL.md](docs/INSTALL.md).
- **End goal (in development, dev printer only):** our own mainline 6.18
  kernel in NAND with our root, still revertible to stock.
  [docs/end_goal_install_plan.md](docs/end_goal_install_plan.md).

## Start here

| Read | For |
|---|---|
| [docs/STATUS.md](docs/STATUS.md) | What runs on each printer today; who owns what |
| [TODO.md](TODO.md) | Open items |
| [PROJECTS.md](PROJECTS.md) | Larger projects and decisions |
| [docs/README.md](docs/README.md) | The documentation map, and the rules for where things go |
| [docs/history/CHANGELOG.md](docs/history/CHANGELOG.md) | What was done, by date |

## Layout

| Path | What |
|---|---|
| `common/` | Hardware register map and IPC layout, shared by every component |
| `host/upctool.c` | Linux tool: `load`, `stop`, `safe`, `probe`, `bridge`, `info`, `dump` |
| `upc_fw/probe/` | Hardware probe firmware (passive) |
| `klipper/README.md`, `klipper/FORK` | Where Klipper's code lives: the fork `catawalks/klipper`, branch `sindoh-dp200` (MCU port, host modules, build configs), and the commit the printers build |
| `klipper/config/printer.cfg` | The user's file: includes the two below and holds per-printer calibration. Never overwritten by an update |
| `klipper/config/dp200_printer.cfg` | Hardware definition, PRINT_START/END, PAUSE/RESUME, PRIME_LINE; replaced on updates |
| `klipper/config/dp200_macros.cfg` | Stock-derived macros (load/unload, clean, bin, probe, bed mesh, homing guards); replaced on updates |
| `install/` | Root builder, USB installer, boot hook, service script, screen app (`install/display/`), slicer profiles |
| `kernel/` | Mainline kernel patches, variants and initramfs for the end-goal install |
| `camera/`, `tools/`, `prebuilt/` | Camera helpers; development and test tools; verified test builds |
| `docs/` | Documentation: see [docs/README.md](docs/README.md) |

## Safety

* The stock firmware's heater protection is gone. Klipper's protections
  replace it: `max_temp`/`min_temp` checks on the MCU, `verify_heater`, and
  the MCU turns a heater off on its own if klippy stops updating it.
* `upctool stop` (also run by `rc.dp200 stop`) holds both UPC cores in
  reset and forces every PWM output low and every stepper driver off.
* A firmware exception on a UPC core turns its outputs off and shows
  `state FAULT` in `upctool info`.
* **Z homes upward.** Anything left on the bed is crushed against the
  nozzle, so every Z homing asks whether the bed is empty (BED_CLEAR).
* The touch screen's STOP (hold 1 s) is an emergency stop on every page.

The first bring-up notes (October 2026) are in
[docs/history/README_bringup_2026-10.md](docs/history/README_bringup_2026-10.md).
