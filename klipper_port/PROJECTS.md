# DP200 - larger projects ("look at later" / nice to have)

Bigger, mostly self-contained pieces of work, separate from the day-to-day
list in [TODO.md](TODO.md). Each entry is written so it can be handed to
another agent or session: goal, where things stand, where to start, what
"done" means.

**Rules for anyone picking one up** (same as the main work):
- No heat and no motion unless the user is at the printer and agreed.
- Never write the NAND, the cartridge chip, or the user's `printer.cfg`
  without the user's OK; never delete `/mnt/sd/pa6170_rodin_nand.bin` or the
  stock `auto_update.sh`.
- Downloaded files are untrusted: own directory, read with `python -I`.
- Commits as catawalks (see HANDOFF.md), normal pushes only.
- Work in a branch or a separate checkout; the main session keeps editing
  `klipper_port` and the printer's live files.

---

## 1. Kernel: rebuild 3.2 modules, or a newer kernel

**Goal:** get past the vendor kernel's limits: no Thumb (forces Debian
armel), no swap, no devtmpfs, no USB CDC-ACM, time32-only V4L2/input.

**Status:** research only (2026-10-20), [docs/kernel_research.md](docs/kernel_research.md).
Vendor kernel `3.2.0-g67a8e16`, Marvell LSP 2014 "shiloh", built with Marvell
GCC (Linaro 4.6.4); no public source. `/proc/config.gz` and a hardware
snapshot are in `docs/kernel/`. A GPL source request is drafted in that doc
(the user hasn't sent it yet).

**Steps, smallest first:**
1. **Out-of-tree modules for the running 3.2 kernel without Marvell's SDK.**
   Vanilla Linux 3.2 + the printer's config + a matching vermagic
   (`3.2.0-g67a8e16 SMP preempt mod_unload ARMv7`), built with an old
   ARM GCC. First target: `cdc-acm.ko` (USB accelerometers, see
   docs/input_shaping.md). Risk: Marvell patches may change struct layouts
   the module touches; test by loading it only with the user's OK and with
   a power cycle as the way back. Done = the module loads and a Klipper
   RP2040 board appears as /dev/ttyACM0.
2. **GPL request** (user sends the draft) - if the source arrives, rebuild the
   vendor kernel with Thumb, swap and CDC-ACM.
3. **Mainline kernel (6.x) with a new device tree**, booted from RAM via
   U-Boot first (milestone 1: UART + GIC + timer). Weeks of work; see the
   "routes" section of kernel_research.md. Needs SD boot (project 2).

## 2. SD-card boot

**Goal:** boot from an SD card (DIP switch / U-Boot) as an alternative to the
internal NAND, and as the test bed for a newer kernel.
**Status:** read-only investigation, [docs/sd_boot_plan.md](docs/sd_boot_plan.md).
**Next:** read U-Boot's environment and commands (mtd1, U-Boot strings),
answer whether U-Boot can load a kernel from SD or serial. Then, with the
user: boot into U-Boot with Klipper off, nothing written to flash.

## 3. Internal NAND install (stock printers have no SD card)

**Goal:** the USB-stick installer puts the Klipper runtime on mtd5.
**Status:** plan [docs/internal_firmware_plan.md](docs/internal_firmware_plan.md),
installer scripts in install/usb + install/nand, payload builds and passes
its release check on the SD build. Size 2026-10-27: 431 MB raw / 141 MB
gzip vs ~190 MB of UBI space - fits, headroom shrinking.
**Next:** trim (git-core 23 MB, Moonraker env, libs); then, with the user's
OK, back up mtd5 and do the first real NAND install; then the remove/restore
path.

## 4. Object-on-bed check with the camera

**Goal:** before a print, warn or stop if something is still on the bed.
**Plan:** fixed bed pose + lamp on -> snapshot from ustreamer -> compare with
a reference of the empty bed (downscaled difference + blob size) in a small
Klipper extra; PRINT_START stops with "Object on the bed?", the screen offers
CONTINUE / CANCEL. Camera looks down at the bed from close above
(hardware_notes, 2026-10-27).
**Needs the user for:** the pose that shows the whole plate, the reference,
tests with real leftovers (thin first layers are the hard case).

## 5. Faster stepping in the UPC firmware

**Goal:** raise the step-rate ceiling. Each step is one hardware engine move
now; the engines can do multi-step moves with their own ramp (stock firmware
does), which would cut per-step overhead.
**Status:** idea (hardware_notes 2026-10-18/19). Today's limits are fine for
the stock speeds. Also open: what step-engine registers +0x10 / +0x14 /
+0x2c mean (copied from the stock app, 2026-10-27).
**Done =** drift test (scratchpad drift_test.py) still 0.000 mm at higher
speeds, emulator regression passes.

## 6. Other Sindoh models

**Goal:** the same Klipper port on the 3DWOX 1X, 2X (dual extruder) and 30X.
**Status:** [docs/other_models.md](docs/other_models.md); OEM firmware for all
models decrypted (oem_models, oem_3dwox1); the 30X key is unknown.
**Next:** 1X testing; 2X second extruder; 30X key.

## 7. Spaghetti / failure detection

Not on the printer (CPU/RAM). Document how a main Klipper host running
Obico (or similar) can watch this printer through its Moonraker.

## 8. Cartridge chip writing

Read-only today (docs/cartridge_chip.md). Writing (e.g. resetting the
remaining length) stays off unless the user explicitly agrees.

## 9. JTAG

CN3 header prepared, no TAP answered (likely fused off), [docs/jtag_prep.md](docs/jtag_prep.md).
Parked.
