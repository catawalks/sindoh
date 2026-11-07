# End-goal install: the sequence (plan, 2026-11-03)

**Target** (internal_firmware_plan.md): our kernel in mtd0 (U-Boot block
untouched), our root in mtd6, mtd5 recovery set and mtd4 never written, no
U-Boot env change. Optional SD card / USB stick for storage in tiers
(PROJECTS.md #11). Revert = a Sindoh update stick
(kernel/revert_to_stock_plan.md, "The user's revert path").

**Approval (owner, 2026-11-03):** every stage below is approved. **Start
after the weekly token refresh**, so the sequence isn't cut off in the
middle. The owner is at the printer for each write stage (power-cycle
access). Each stage ends with its checks; a failed check stops the
sequence.

**Printers:** the dev printer (Stanley, COM3, SD card in the slot, serial
console) does every stage first. The work printer (end-user stand-in: no
card, no serial, USB stick only) only gets stage 8, with the released
form of the installer.

## Where it starts from (done)

- Mainline 6.18 on the dev printer: SMP, SD, Ethernet, Wi-Fi (mwifiex),
  touch, framebuffer, the UPC driver, Klipper + Moonraker + screen app,
  shutdown screens. Booted by hand from U-Boot (SD raw sectors, 10-31).
- Mainline NAND: read-only proven (BCH, 10-30); UBI/UBIFS write test on
  mtd6 passed (16 MB, 11-01); mtd3 rewritten twice from our kernel (3c-0,
  3c-1, 11-01); 3a read-only checks and 3b dry run of dp200-revert.sh done.
- Stock-kernel USB installer (/klipper on mtd6): released form is the
  first public release (later, PROJECTS #10).

## Stages

**1. mtd0 kernel area, same contents (3c).** From our kernel (SD): erase
blocks 2-63, write back the stock kernel from pa6170_rodin_nand.bin.
Check: corrected read = file, raw + OOB = the 3a baseline, then a normal
stock boot from NAND. Proves the mtd0 write path. Fallback: U-Boot is
untouched; SD raw boot over serial, write again.
**Done 2026-11-07** (results: kernel/revert_to_stock_plan.md, "3c / stage 1").

**2. mtd6 full revert (3d).** Backup first: raw nanddump of mtd6 (308 MB)
and a tar of /app/nvram, the Wi-Fi config and G-codes, to the PC. Then the
mtd6 half of dp200-revert.sh from our kernel (root on SD). Check: stock
boots to the touchscreen app; karas.db restored from mtd4 (model, serial);
then the Sindoh 2020 USB update. Proves the revert half. Fallback: write
the nanddump back.
**Done 2026-11-07** (results: kernel/revert_to_stock_plan.md, "3d / stage 2").

**3. Initramfs for our kernel** (busybox + mtd-utils, ~2 MB), tested from
the SD fast path before anything uses it from NAND:
- normal boot: root = a card/stick marked for the printer if present
  (storage tier), else ubi0:filesystem on mtd6; `switch_root`;
- revert mode (marker or a Sindoh update stick + confirm on the panel):
  run dp200-revert.sh from RAM;
- broken root: offer the recovery from mtd5 ("touch to recover").

**4. Our kernel in mtd0, root still on the SD card.** Write our kernel
(+ initramfs) into mtd0's kernel area; U-Boot boots it with the stock
bootargs, the initramfs picks the card. Check: cold boot to Klipper with
no serial interaction. Fallback: stage 1's write of the stock kernel.

**5. Our root in mtd6.** Build the UBIFS image of the runtime (trimmed as
today, ~106 MB on flash), back up mtd6 (stage 2's way), write it with
ubiupdatevol from our kernel; take the card out. Check: NAND-only boot,
Klipper, screen, Wi-Fi, G-code space (~140-150 MB free), the NAND tier's
update path (Mainsail/Moonraker from upstream).

**6. Installer v2 (USB stick, runs under stock 3.2 via auto_update.sh).**
- Checks as today (hardware, NAND layout, mtd5 recovery set md5s, space).
- Saves the Sindoh app/WebKit backups and (optional) karas.db + network
  files to the stick, per printer and firmware (as today).
- Writes mtd6 (our root: ubiformat keeping erase counters, ubimkvol,
  ubiupdatevol), verifies, then mtd0's kernel area last, verifies.
- Carries the user's Wi-Fi networks into the new root.
- Also upgrades a printer with the interim /klipper install (keeps its
  printer.cfg and calibration).
Test on the dev printer from stock, and from the interim install.

**7. Revert by Sindoh stick, full cycle** on the dev printer: our system
-> plug in RODIN_200730_2 -> confirm -> stock from mtd5 -> stock runs the
update -> 2020 stock with model/serial from mtd4. Then installer v2 again.

**8. Work printer (end-user stand-in):** installer v2 over its interim
install, a long print, the Sindoh-stick revert, reinstall.

**9. Release checklist** (PROJECTS #10), then the public end-goal release.

## Root architecture (owner, 2026-11-06)

The root stays **armel** through the end-goal release: the interim USB
installer (stock 3.2 kernel, no Thumb, so no armhf) and our kernel then run
the same root. After the interim installer is retired, our kernel's root
moves to armhf (faster); until then two roots would have to be maintained.

## Mainline items that ride along

Tracked in no_gpl_plan.md; needed by stage 5 at the latest: NAND
read-write in the device tree for mtd0/mtd6 (the write window/guard,
patch 0010 v2), wear readout, power-loss behaviour of the UBIFS root,
the storage-tier card detection, faster stepping default (TODO 13).

## Accepted risk

A power cut during the mtd0 write leaves no bootable kernel; U-Boot is
untouched, recovery is the serial console - as with Sindoh's own kernel
updates. mtd0 is written last, rarely, and verified before the reboot.
