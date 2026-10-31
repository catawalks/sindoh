# Checks that need someone at the printer

A running list of things that can only be confirmed at the printer itself
(looking at the panel, touching it, being there for motion). Remove an entry
once it's done, with its result in the matching doc.

## Open

| Added | Check | How | Context |
|---|---|---|---|
| 2026-10-31 | **The boot logo stays up during a mainline boot**, with no text on the panel until the screen app draws (like stock) | Watch the panel through a mainline Debian boot (m1-debian 695966b6 or later) | The kernel has no fbcon and no `console=tty0` any more. The boot log shows only the dummy console. docs/kernel/debian_root_boot.md, "No console on the panel" |
| 2026-10-31 | **CONSOLE in the screen app** opens the kernel log, and one tap closes it | System → Display → CONSOLE, then tap anywhere | It renders on the printer without errors, and dmesg is read. Not yet seen on the panel |
| 2026-10-30 | **Input shaping test** with the FLY-ADXL345 | Needs motion: someone present, and an OK for each move | docs/input_shaping.md |

## Decisions (not checks)

- **The daily boot method** for the mainline kernel. Today it is a serial or Ethernet loader each time, and nothing is written to NAND or the U-Boot env. Booting it by default needs a `saveenv` or NAND decision from the owner.
