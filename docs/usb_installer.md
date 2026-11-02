# USB stick installer (plan + first implementation)

Goal: owners of a Sindoh DP200 install or remove Klipper by plugging in a USB
stick, with no serial console, PC tools or Linux knowledge.

## The stock mechanism (verified 2026-10-18)

1. mdev runs `/usr/sbin/media.connect` for any `sd[a-z]` device (hotplug, and
   at boot from `/etc/profile` if `/dev/sda1` exists). It mounts the stick as
   **vfat** on `/mnt/sda1` and calls `/app/auto_update.sh`.
2. `auto_update.sh` derives `KEY` from `/app/crypto_key.dat`
   (`openssl des3 -d -salt -k "" | tar -xjO`).
3. Every `/mnt/sda1/_update_rodin/unmistakable*.she` is decrypted
   (`openssl des3 -d -salt -k $KEY | tar -xj -C /tmp`; the trailing "e" is
   dropped from the name) and executed as root with the folder as `$1`.
   A failing script aborts the rest.
4. Then `_update_rodin/update.she` (the OEM full flash: `image.bin/.app/.logo`
   = DES3 tar(.bz2) with .md5; kernel to `/dev/mtd0`, rootfs/app via tar or
   rsync) runs if present.

The OEM 2020 update (`Manufacturer_Firmware_Updates/…RODIN_200730_2.zip`) and
the community "Model 1 converter" (`Model_1_Converter/`) both use step 3.
Both run in stock mode and in Klipper mode, because media.connect belongs to
the stock kernel/BusyBox side.

## Update 2026-11-02: the stock root (mtd6) is the NAND target

Agreed with the owner for a first release on the **stock 3.2 kernel**:
Klipper goes into `/klipper`, a directory on the stock root (mtd6, UBIFS),
written through Sindoh's own NAND driver. **mtd5 (the factory recovery set),
mtd0, the U-Boot blocks and the env are never touched** (the mtd5 target
below is dropped: it erased the recovery set).

- **Room:** mtd6 has 264 MB, 54 MB free on stock. The installer deletes only
  `/app/SVN_GUI` (93 MB, Sindoh's touch-screen app; Klipper's screen replaces
  it), after copying it to the stick (`dp200_stock_backup/`, md5-checked).
  The rest of the stock system stays: auto_update.sh and its key, upc.ko,
  Wi-Fi, BusyBox, the Qt browser libraries.
- **Size (measured on the printer):** `runtime.exclude` now also drops perl,
  git, apt, iconv tables, pip/setuptools, compiler leftovers and this
  printer's `/var/backups` and `/root`. Runtime 235 MB, payload 84 MB gzip;
  UBIFS zlib estimate block by block (`ubifs_est.py`): 103 MB. About 44 MB
  stays free for G-codes. New files are written with `compr=zlib`
  (remount); the stock files stay LZO.
- **Checks before any change:** DP200-family hardware (`/app/upc.ko`), kernel
  `3.2.0-g67a8e16` (Sindoh 2020 firmware, the build upctool and cdc-acm.ko
  are tested on; DP200 and Stanley Model 1 alike), mtd6 = "filesystem" as
  the UBIFS root, space, room on the stick for the backup, payload md5.
- **On failure** after the backup: `/klipper` is removed and SVN_GUI copied
  back, so the stock firmware boots as before.
- **Boot:** `dp200-boot.sh` starts `/klipper/dp200/dp200-start.sh`;
  `etc/dp200/on_nand` keeps the logs in RAM.
- **Remove:** `unmistakable_klipper_remove.she` restores the hook, deletes
  `/klipper` and puts SVN_GUI back from the stick (md5-checked). Without the
  backup it refuses (Sindoh's OEM update restores the app instead).
- **Stick layout** (the folder that should run is renamed `_update_rodin`):
  ```
  _update_rodin_KlipperInstall/unmistakable_klipper_install.she
                               dp200_klipper_payload.tar.gz (+ .md5, .size)
  _update_rodin_KlipperRemove/unmistakable_klipper_remove.she
  dp200_stock_backup/SVN_GUI (+ .md5)      written by the installer
  ```

## Tested on the test printer (2026-11-02) and what it taught

Install from the stick (twice), pull-to-cancel at the INSTALL prompt, a
boot without the SD card, remove with the stick backup, remove with the
mtd5 fallback; each time the stock UI or Klipper came back as expected.
Findings, all fixed:

- **Pulling a stick kills `tinydebug`.** Sindoh's `media.connect` (USB
  removal) unmounts the stick and runs `kill -9` on every tinydebug,
  including the `keywait` that waits for the confirm touch. A pulled stick
  started an upgrade once. Now only keywait's exit 0 (a touch) with the
  stick still present counts; 137 (killed) cancels or asks again.
- **Our touch screen kept reading touches** under the installer's messages:
  it is stopped first and started again on a cancel.
- **Entropy on NAND** (kernel 3.2, OpenSSL 3): Moonraker and the screen
  hung on the boot logo; fixed by `dp200-entropy.py` (seed file).
- **nginx** needed `/var/log/nginx` (logs are RAM on NAND).
- **`tinydebug` lines are Qt labels and render HTML:** colored titles
  (`<font color=...>`); about 21 characters fit on a line.
- **Stock `ubiattach`/`ubidetach` need the control device:**
  `ubiattach /dev/ubi_ctrl -m 5 -d 2`.
- **A tar stream's md5 is not a file-set identity** (directory order changes
  after a restore): backups are matched by a fingerprint of the per-file
  md5s (`SVN_GUI.files.md5`).
- **Space:** the 80 MB payload took 106 MB of the root; removing SVN_GUI
  freed 79 MB (not its 93 MB du size). 27 MB stays free.
- **mtd5 fallback:** the recovery set's SVN_GUI is the factory 2017 one
  (491 files; the 2020 one has 1260). With the 2020 firmware it starts and
  shows the stock home screen; Sindoh's 2020 update matches it again.

## More room on the stock root: Qt WebKit (2026-11-02)

The NAND install leaves ~27 MB free. Of the stock libraries (readelf on the
printer):
- `libQt5WebKit` (20 MB) and `libQt5WebKitWidgets` are needed only by
  `/app/appBrowser`, Sindoh's touch-screen browser, which only shows the
  SVN_GUI pages the install already removes. Removing them (backed up and
  restored with SVN_GUI) would give ~48 MB free.
- ICU (`libicudata` 18 MB, `libicui18n`, `libicuuc`) must stay:
  `libQt5Core` needs it, and `tinydebug` (every installer and Sindoh update
  message) uses QtCore, QtGui and QtWidgets. So do `UIManager` and the
  Qt plugins in `/usr/lib/qt` (linuxfb).
Done (2026-11-02, owner's OK): the installer removes WebKit after SVN_GUI,
backed up to the stick as `WEBKIT.tar` (+ `.md5`, `.files.md5`); undo and
the remover put it back, from the stick or else from the recovery set
(`update.tar.bz2` holds the same two libraries, md5-identical). Measured:
deleting WebKit frees 12.9 MB of flash (it is stored compressed), so a
NAND install should leave ~40 MB free. Tested on the test printer: the
backup commands, then the remover's mtd5 fallback restoring WebKit
(fingerprint identical, the stock browser starts).

## Update 2026-10-20: internal NAND is now the default target (superseded)

- **Target:** the installer writes Klipper to **mtd5 "recovery"** as UBI
  volume `klipper` (ubi2), mounted on `/klipper`. Before formatting it, it
  saves the partition to the stick: `nanddump -o -b` → `mtd5_recovery_backup.bin`
  + `.md5`, the exact stream `nandwrite -p` writes back.
  An empty file `_update_rodin/target_sd` selects the old SD-card target.
- **Boot:** `hook_install.sh` now copies `dp200-boot.sh` to `/etc/dp200-boot.sh`.
  This stage 1 attaches mtd5, mounts the volume, and starts
  `<root>/dp200/dp200-start.sh`; it falls back to the SD card.
  `dp200-start.sh` works out its root from its own path. On NAND, logs go to
  tmpfs (flash wear).
- **Remove stick:** restores the stock boot. If the backup + md5 are on the
  stick, it also writes mtd5 back (`flash_erase` + `nandwrite -p`).
- **Payload:** `make_payload.sh` builds the **runtime** image by default
  (`install/nand/runtime.exclude`: no compilers, docs or caches), plus a
  generic `printer_data`. This printer's calibration, database, logs and
  G-code are never shipped. `full` builds the whole tree for SD installs.
  Debian's tar runs inside the chroot (it needs Debian's libraries).
- **Rehearsal:** `DRY_RUN=1` (or a `dry_run` file in the folder) runs every
  check, unpacks with the **stock BusyBox tar** into `/mnt/sd/dryrun_root`,
  and verifies the key files. There's no screen, no flash access (it does
  not even attach mtd5, since UBI can write when attaching), no hook and no
  reboot.

## Our installer (install/usb/)

| File | Role |
|---|---|
| `unmistakable_klipper_install.sh` | Runs from the stick. Takes over the touchscreen (`/app/display.sh`, `tinydebug keywait`), checks the payload md5, SD card (ext2/3/4, free space) and that `/app/upc.ko` exists. Asks for a touch to confirm. Stops a running stack (upgrade), unpacks the payload to `/mnt/sd`, keeps an existing `printer_data/config`, runs `hook_install.sh`, then asks for a touch to reboot. |
| `unmistakable_klipper_remove.sh` | Restores the stock boot (`/etc/profile.stock`, removes `/DEBUG_MACHINE`). The SD card content stays. |
| `pack_she.sh` | Packs a `.sh` into `.she` (`tar cjf` + `openssl des3 -salt -md md5`). The DP200 family's update key is built in; `-k crypto_key.dat` uses another key. Self-verifies. |
| `make_payload.sh` | Builds `dp200_klipper_payload.tar.gz` (+ .md5) from a working printer's SD card with GNU tar from the Debian root, minus logs, database, caches and test files. |

Stick layout:
```
_update_rodin/unmistakable_klipper_install.she
_update_rodin/dp200_klipper_payload.tar.gz
_update_rodin/dp200_klipper_payload.tar.gz.md5
```
(Uninstall stick: only `_update_rodin/unmistakable_klipper_remove.she`.)

Verified: both scripts packed on the printer with its own openssl and key,
then decrypted exactly the way auto_update.sh does it, are byte-identical,
and pass `sh -n` in the stock BusyBox. **Not yet run end-to-end.**

## Revert to stock (OEM) with one stick (user request 2026-10-19, lower priority)

auto_update.sh runs every `unmistakable*.she` **before** `update.she`, so one
stick can do a complete revert:
```
_update_rodin/unmistakable_klipper_remove.she   (ours)
_update_rodin/update.she, image.bin, image.app, image.logo, *.md5,
             snapshot_version.sh, other unmistakable_*.she  (Sindoh's OEM update, unchanged)
```
The remove script removes the hook (/etc/profile.stock, /DEBUG_MACHINE). When it
sees `update.she` next to it, it returns without rebooting, so the OEM update
flashes the stock kernel and /app right after it. Without OEM files it just
restores the stock boot and reboots. TODO once Klipper lives on NAND (mtd5):
the remove script should also offer to write back the mtd5 backup that the
installer saved to the stick (`nandwrite`), so the "recovery" partition
returns to factory content. Not tested yet.

## Open items before giving it to others

- **microSD card:** does every DP200 have one, and how is it formatted from
  the factory? This unit's card is ext4, 3.6 GB. If stock cards are vfat, the
  installer needs a format step (check that mke2fs/mkfs.ext* exists on the
  stock side). The payload needs ~2.2 GB unpacked.
- **Payload size vs FAT32:** single files must stay under 4 GB (the expected
  ~0.6–0.8 GB gzip is fine).
- **Firmware versions:** tested only on RODIN_200730_2 (kernel 3.2.0-g67a8e16,
  no CONFIG_ARM_THUMB, so armel userland). Other versions should be checked
  (`/snapshot_version.sh -v`).
- **Per-printer state:** the payload must not carry this printer's Moonraker
  database or logs (excluded). The config is the generic printer_dp200.cfg plus
  macros, so offsets and PID are calibrated on each printer.
- **Updates later:** the same stick mechanism can deliver upgrades (the installer
  detects an existing install and keeps the config).
- **End-to-end test plan** (user at the printer): make the payload, put the
  remove .she on a stick and test it (stock boot comes back), then the install
  stick (Klipper boots without a serial console).
