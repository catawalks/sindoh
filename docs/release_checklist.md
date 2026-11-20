# Release checklist: USB stick install (release 1)

The steps between "it works on the owner's printers" and a public download.
Release 1 is the USB stick install on the stock 3.2 kernel (`/klipper` on
the stock root; PROJECTS.md #10). The end-goal install (our kernel in mtd0)
is a later release with its own checklist.

Mark each line with the date and the build it was checked on. A release is
cut only when every line is checked on the **same payload** (md5).

## 1. Decisions (owner, before the build)

- [ ] **Version and tag:** for example `v0.1.0`, as a tag on catawalks/sindoh.
- [ ] **Firmware lines supported:** release 1 = RODIN_ (DP200, DP201,
      DP200Q conversions) on RODIN_200730_2. Every other line (RODUP_ 3DWOX 1,
      the 6270 models) is refused with a clear message, not half-installed.
      (TODO 38 has what RODUP_ still needs.)
- [ ] **Pre-packed `.she` files in the release:** yes or no (INSTALL.md
      "For maintainers" leaves it open). A release that people can use
      without a Linux PC needs them.
- [ ] **License:** neither catawalks/sindoh nor the port has a LICENSE file.
      The fork is Klipper's GPLv3 (`COPYING`). Pick one for the port's own
      code (scripts, screen app, configs, docs) and add the file.

## 2. Build

- [ ] Payload built from the pinned fork commit (`klipper/FORK`, via
      `klipper/get_fork.sh`) and a committed port tree, with both commits
      written into the payload's version file (SYSTEM -> INFO shows them).
- [ ] `install/usb/release_check.sh` passes: payload, dry-run install,
      runtime check.
- [ ] Size: the unpacked runtime leaves at least 40 MB free on a stock
      RODIN_200730_2 root after the Sindoh app is removed (the installer
      refuses below 10 MB).
- [ ] Stick files packed with `install/usb/pack_she.sh`, then decrypted
      again the way `/app/auto_update.sh` does and compared byte for byte.

## 3. Content audit (nothing that must not be published)

On the unpacked payload, by listing and grepping, not by trust:
- [ ] No Wi-Fi networks or keys: no `wpa_supplicant.conf` with a
      `network=` block, no saved-network files, no network names anywhere.
- [ ] No per-printer data: no `printer_data` logs, Moonraker database,
      G-code, karas.db, `dp200_machine.cfg`, serial numbers, MAC addresses,
      or `/etc/dp200` state files from the build printer.
- [ ] No Marvell or Sindoh files: no `mrvl/*.bin` Wi-Fi firmware, nothing
      from `/app` (SVN_GUI, upc.ko, crypto_key.dat), no NAND images.
- [ ] No credentials: SSH host keys, root or user passwords, tokens
      (regenerate host keys at first boot if the root carries any).
- [ ] `cdc-acm.ko` and other binaries we ship have a note on where they
      came from and how to rebuild them.

## 4. Hardware tests (owner at the printer)

On the release payload, on a printer that does not have it yet:
- [ ] **Fresh install from stock** (remove first, so the printer is stock):
      the install runs from the screen prompts alone, the backup lands on
      the stick, Klipper is ready after the reboot, and `dp200_machine.cfg`
      holds this printer's own motor currents.
- [ ] **Upgrade over an existing install:** `printer.cfg` and its
      calibration are kept, port files (`dp200_*.cfg`) are replaced.
- [ ] **INSTALL.md followed word for word:** Wi-Fi, first-time setup
      (probe, PID, mesh), slicer G-code. Every step works as written.
- [ ] **A real print** start to finish (bed-empty question, mesh, purge,
      print, end), plus pause/resume and cancel.
- [ ] **Touch screen:** home, lamp, preheat, load/unload, STOP.
- [ ] **Pull-to-cancel** at the INSTALL prompt: nothing changed.
- [ ] **A refused install:** a payload with a wrong md5, and a printer
      on another firmware line or version, each end with a message and no
      change.
- [ ] **Remove:** the Sindoh app comes back and runs; then the full revert
      with Sindoh's own update next to the remover.
- [ ] The second printer (both the DP200 and the DP200Q-converted Stanley
      if possible), so it is not one unit's result.

## 5. Documents

- [ ] INSTALL.md matches this build: supported firmware, stick layout,
      screens and messages as they really appear, removal, known issues.
- [ ] Known issues listed (open TODO items a user can hit).
- [ ] Safety section: Z homes upward, first print attended, Klipper
      replaces the stock heater safety.
- [ ] Credits: Klipper, Moonraker, Mainsail; contributors (Fredrik
      Gustafsson's 3DWOX 1 notes).

## 6. Publish

- [ ] Tag the port repo and catawalks/sindoh; the fork commit is already
      public.
- [ ] GitHub release on catawalks/sindoh with: the install stick folder
      (`_update_rodin_KlipperInstall/`), the remove folder
      (`_update_rodin_KlipperRemove/`), `SHA256SUMS`, and the release notes
      (version, fork and port commits, supported firmware, known issues).
- [ ] Download the release assets on a clean PC, check `SHA256SUMS`, and
      install from that download once.
