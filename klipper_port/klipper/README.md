# Klipper for the DP200: what lives where

Klipper's part of this project is split between two repositories. Each
file has **one home**; nothing is copied by hand between them.

| What | Its one home |
|---|---|
| The MCU port for the two UPC cores (`src/upc/`) | the fork |
| Changes to Klipper's shared code (`src/stepper.c`, `src/sched.c`, `src/Kconfig`) | the fork |
| Firmware build configs (`config/dp200_fm.config`, `dp200_io.config`) | the fork |
| Host modules (`klippy/extras/upc_stats.py`, `upc_clockcheck.py`, `dp200_cartridge.py`) | the fork |
| Printer configuration: `printer.cfg`, `dp200_printer.cfg`, `dp200_macros.cfg`, `dp200_adxl.cfg.off` | here, `klipper/config/` |
| The UPC register map and IPC layout (`upc_hw.h`, `upc_ipc.h`) | here, `common/` (upctool uses them). The fork carries a copy in `src/upc/` to build; `tools/fork_check.sh` compares them |
| Which fork commit the printers build | here, `klipper/FORK` |

**The fork:** https://github.com/catawalks/klipper

| Branch | What it is |
|---|---|
| `master` | Upstream Klipper, unchanged. Synced from Klipper3d/klipper. |
| `sindoh-dp200` | The product branch: what the printers build and run. |
| anything else | A short-lived working branch: merged into `sindoh-dp200` and deleted when its work is tested. |

## How a build gets the code

`klipper/get_fork.sh DEST` checks out the commit pinned in `klipper/FORK`.
The root builders (`install/build_rootfs.sh`, `install/rootfs_inside.sh`)
use it for `/home/klipper/klipper`, so klippy and the UPC firmware are
built from the same tree. `tools/fm_rebuild.sh` rebuilds one firmware
image from that checkout on the printer.

## Rules

- **Changing Klipper code:** commit in the fork (a working branch, then
  `sindoh-dp200`), push, then set `COMMIT=` in `klipper/FORK` here in the
  commit that needs it. Never patch a checkout on a printer and leave it.
- **Changing configuration or macros:** edit `klipper/config/` here. Run
  `tools/klippy_batch_check.sh` and `tools/cfglint.py` first.
- **Commits in the fork** follow upstream's form: one topic per commit, the
  summary starts with the module (`upc:`, `stepper:`, `config:`), no merge
  commits on `sindoh-dp200` (rebase a working branch onto it).
- **Before a payload build or a release:** `sh tools/fork_check.sh`. It
  fails if Klipper code has reappeared here, if printer `.cfg` files have
  reappeared in the fork, or if the shared headers differ.
- **Upstream:** nothing has been submitted to Klipper. A submission needs
  the owner's real-name `Signed-off-by` on every commit, no board-specific
  `#if` in shared code, one minimal example config and reference docs.
  That would be a separate branch rebuilt on current upstream; the product
  branch stays as it is.

History: until 2026-11-13 this folder also held a copy of `src/upc`, the
host modules, the build configs, `install_port.sh`, `make_fork.sh` and a
`patches/` folder, and the fork held a copy of the printer configuration.
The copies had drifted (11 files). They are in git history (last commit
with them: the parent of the one that added this file).
