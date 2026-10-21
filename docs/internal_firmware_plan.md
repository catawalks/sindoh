# Klipper on internal storage (no SD card) - plan

User requirement (2026-10-18): stock DP200s have no usable microSD card, so
the installable firmware must live entirely on the internal NAND, and be
installed from a USB stick (see usb_installer.md).

## Internal NAND (measured on RODIN_200730_2)

| mtd | size | name | content / use |
|---|---|---|---|
| 0 | 8 MB | kernel | stock kernel 3.2 (U-Boot `load_nand` reads it) |
| 1 | 128 KB | u-boot-env | `bootcmd_select=run mv61X0_nandboot` |
| 2 | 512 KB | bbt | read-only |
| 3 | 1 MB | boot-logo | |
| 4 / 8 | 8 MB | backup | UBIFS `/backup` (5 MB, sync mount) |
| **5** | **200 MB** | **recovery** | UBI image (`UBI#`), **not used by the boot path** (U-Boot boots `ubi.mtd=filesystem root=ubi0:filesystem` only; `/etc/profile` has its mount commented out; the OEM update.sh can write an `image.recovery`, but the 2020 update ships none) |
| 6 / 7 | 294 MB | filesystem | UBIFS root incl. /app: 264 MB, **54 MB free** |

Stock tools: ubiattach/ubidetach/ubimkvol/ubirmvol/ubiformat/ubiupdatevol/
ubinfo, nanddump/nandwrite, flash_erase(all). No mkfs.ubifs; not needed,
since an empty UBIFS volume formats itself on first mount. PEB 128 KiB,
LEB 124 KiB, so mtd5 gives ~190 MB of UBI volume space.

## Size of a Klipper runtime (from the working SD build)

The full Debian trixie armel tree is ~2 GB, mostly build tooling: gcc 552 MB,
arm-none-eabi 419 MB, docs/man/locales/headers 144 MB, pip/apt caches 92 MB,
the Klipper checkout outside klippy/ ~225 MB. A runtime-only tree is
estimated at 330–370 MB uncompressed. UBIFS zlib compression should bring
that near the ~190 MB of mtd5. **Tight: measure it** (trim a copy, then
`tar czf` the copy; the gzip size is close to UBIFS zlib usage).

The things a runtime needs pre-built (no compiler on the printer):
- klippy's `chelper/c_helper.so`, built once in the build root (klippy only
  rebuilds it when the sources change);
- the pip wheels in klippy-env / moonraker-env (already built);
- UPC firmware `/opt/dp200/{fm,io}.bin` (gcc, already built).

**Measured 2026-10-18** (install/nand/measure_runtime.sh with
install/nand/runtime.exclude, run in the chroot of the working SD build):
**367 MB uncompressed, 119 MB gzip -6.** UBIFS compresses per 4 KiB block, so
expect roughly 130–150 MB on flash: **it fits mtd5 (~190 MB)** with headroom.
The biggest remaining parts: /usr/lib/arm-linux-gnueabi 116 MB, moonraker-env
55, /usr/bin 47, klippy-env 36, /usr/share 32, python3.13 stdlib 28, git-core
23 (only Moonraker's update manager needs git), mainsail 11, klippy 7 MB.
Further trims if needed: git, perl, apt/dpkg, unused shared libraries.

## Recommended design

1. **Root on mtd5 as UBIFS**, mounted at `/klipper` by the boot hook
   (`ubiattach -m 5`, `mount -t ubifs -o compr=zlib ubi2:klipper /klipper`).
   Everything else (dp200-start.sh, dp200-mounts.sh, rc.dp200, chroot) stays
   as it works today; only `ROOT` changes from /mnt/sd to /klipper.
2. **Stock firmware untouched**: kernel, U-Boot env and the stock rootfs keep
   working. The hook is the same reversible /etc/profile line + /DEBUG_MACHINE
   (the hook itself must live on NAND: /etc/dp200-start.sh instead of /mnt/sd).
3. **USB installer** (`unmistakable_klipper_install.she`, same touchscreen
   flow): (a) back up mtd5 to the stick (`nanddump`, 200 MB) so the recovery
   partition can be restored; (b) `ubiformat /dev/mtd5`, `ubiattach`,
   `ubimkvol -N klipper -m`; (c) mount, unpack the payload; (d) install the
   hook; (e) reboot. The remove stick restores the stock boot (and offers to
   write the mtd5 backup back).
4. **NAND wear / space**: logs, /tmp and the Moonraker database go to tmpfs or
   a small dedicated volume; G-code uploads have little room. Options are
   USB-stick gcodes or the 54 MB free on the stock rootfs. This needs a
   decision.
5. **Alternatives if it doesn't fit**: Alpine armhf (ARM-mode, runs on this
   kernel - the old Alpine 3.9 on the card executes) is far smaller (musl,
   python ~45 MB) but needs the wheels rebuilt for musl. Or slim Moonraker's
   optional dependencies.

## Next steps

1. Make a trimmed copy of the SD root (`tools`: a `make_runtime.sh` that
   deletes the build-only parts in a copy) and measure the gzip size.
2. Prove a UBIFS root on mtd5 **only after** backing up mtd5 (nanddump to the
   SD card / stick) and with the user's go-ahead (it erases that partition).
3. Port dp200-start.sh / the hook to ROOT=/klipper; test boot from NAND
   without the SD card.
4. Fold it into the USB installer, then test end to end on a printer.
