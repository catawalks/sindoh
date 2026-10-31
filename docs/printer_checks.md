# Checks that need someone at the printer

A running list of things that can only be confirmed at the printer itself
(looking at the panel, touching it, being there for motion). Remove an entry
once it's done, with its result in the matching doc.

## Open

| Added | Check | How | Context |
|---|---|---|---|
| 2026-10-30 | **Input shaping test** with the FLY-ADXL345 | Needs motion: someone present, and an OK for each move | docs/input_shaping.md |

## Decisions (not checks)

- **The daily boot method** for the mainline kernel. Today it is a serial or Ethernet loader each time, and nothing is written to NAND or the U-Boot env. Booting it by default needs a `saveenv` or NAND decision from the owner.

## Done

- 2026-10-31: **CONSOLE in the screen app** works on the panel. It shows the kernel log, and a tap closes it (the owner, on mainline).
- 2026-10-31: **The boot logo on a mainline boot** stays up, with no text until the screen app (the owner). No loading bar yet: only the vendor kernel draws it.
