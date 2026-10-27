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

## Update 2026-10-20: internal NAND is now the default target

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
