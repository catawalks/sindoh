# Documentation map and rules

Read in this order when you pick the project up:
1. [STATUS.md](STATUS.md): what runs on each printer today, and who owns what.
2. [../TODO.md](../TODO.md): open items only.
3. [../PROJECTS.md](../PROJECTS.md): larger projects, with decisions.
4. The reference document for your area (table below).

## Where things go

| Kind of information | Its one home | Rule |
|---|---|---|
| Current state of the printers, sessions and their areas | `docs/STATUS.md` | Overwrite in place. One page. No history. |
| Open work | `TODO.md` | Open items only, a few lines each. When an item is done, delete it and add a line to the changelog. |
| What was done, and when | `docs/history/CHANGELOG.md` | Append, newest first: date, one or two lines, the commit. |
| Larger projects and decisions | `PROJECTS.md` | Status line first. Decisions with their date. |
| How a thing works (facts, measured values) | one reference doc in `docs/` or `docs/kernel/` | Describe how it is now. No dated diary. Each fact lives in one file; other files link to it. |
| A plan that is not finished | `docs/*_plan.md` | Status line on top. When finished or dropped, move it to `docs/history/` with a `**Status:**` line and fold the lasting facts into a reference doc. |
| Test logs, investigations, session notes, raw captures | `docs/history/` (kernel ones in `docs/history/kernel/`) | Never in `TODO.md` or a reference doc. Start each with a `**Status:**` line (SOLVED / DONE / SUPERSEDED / HISTORY) and where the live facts are. |
| Anything that needs the owner at the printer | `TODO.md`, section "Owner at a printer" | One list. (`docs/history/printer_checks_2026-10-31.md` is folded into it.) |

Rules that keep it tidy:
- **One home per fact.** NAND partitions and the boot path: `nand_layout.md`.
  Network settings: `network.md`. Wi-Fi setup and the 8782 driver:
  `wifi.md` and `kernel/wifi_88w8782.md`. Link, don't copy.
- **Same commit.** Update `TODO.md`, `STATUS.md` and the changelog in the
  commit that does the work.
- **Sections, not sprawl.** A session edits only its own area's entries in
  `TODO.md`; the coordinating session merges and publishes.
- **No results in TODO.md.** A test result is one changelog line plus, if
  the detail matters, a file in `docs/history/`.
- **Dates are absolute** (2026-11-12, not "yesterday").
- **Nothing is deleted from history**; it is moved there.
- Code comments and kernel patches may still name a document by its old
  path. If it isn't there, it is in `docs/history/` under the same name.

## Reference documents

| Area | Document |
|---|---|
| Install from the USB stick (stock 3.2 kernel) | [INSTALL.md](INSTALL.md), [usb_installer.md](usb_installer.md) |
| NAND partitions, boot path, write rules | [nand_layout.md](nand_layout.md), [nand_restore.md](nand_restore.md), [kernel/nand_boot_cmdline.md](kernel/nand_boot_cmdline.md) |
| End-goal install (our kernel + root in NAND) | [end_goal_install_plan.md](end_goal_install_plan.md), [internal_firmware_plan.md](internal_firmware_plan.md), [kernel/revert_to_stock_plan.md](kernel/revert_to_stock_plan.md) |
| Mainline kernel | [no_gpl_plan.md](no_gpl_plan.md), [kernel/smp_freeze_summary.md](kernel/smp_freeze_summary.md), [kernel/upc_mainline_design.md](kernel/upc_mainline_design.md), [kernel/debian_root_boot.md](kernel/debian_root_boot.md), [mainline_userspace.md](mainline_userspace.md), [kernel/rtc_setup.md](kernel/rtc_setup.md), [kernel/touch_bu21029.md](kernel/touch_bu21029.md) |
| Wi-Fi and network | [wifi.md](wifi.md), [network.md](network.md), [kernel/wifi_88w8782.md](kernel/wifi_88w8782.md) |
| Hardware facts | [hardware_notes.md](hardware_notes.md), [stock_routines.md](stock_routines.md), [kernel/6270_vs_6170.md](kernel/6270_vs_6170.md), `kernel/uboot_*.txt`, `kernel/vendor_*` |
| Motion and stepping | [faster_stepping_plan.md](faster_stepping_plan.md), [input_shaping.md](input_shaping.md), [test_print_plan.md](test_print_plan.md) |
| Touch screen app | [touchscreen_options.md](touchscreen_options.md) |
| Other topics | [cartridge_chip.md](cartridge_chip.md), [other_models.md](other_models.md), [sd_boot_plan.md](sd_boot_plan.md), [jtag_prep.md](jtag_prep.md), [kernel/marvell_github.md](kernel/marvell_github.md) |
| History | [history/CHANGELOG.md](history/CHANGELOG.md), everything else in `history/` |
