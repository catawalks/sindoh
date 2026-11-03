# Klipper on internal storage (no SD card) - plan

User requirement (2026-10-18): stock DP200s have no usable microSD card, so
the installable firmware must live entirely on the internal NAND, and be
installed from a USB stick (see usb_installer.md).

## The plan (agreed 2026-10-31): our system in the stock system's place

**Goal (the owner's words, summarized):**
- a full replacement of the running OS: kernel, drivers and the touchscreen front end;
- Sindoh's recovery and update scripts keep working, so owners can go back to stock or use recovery mode;
- everything on the internal NAND: no added hardware, no opening the printer;
- Klipper, so owners can extend the printer easily.

**Layout:** the same partition boundaries as stock. They are U-Boot's
`mtdparts`, and our device tree has the same ones. Only two partitions get new
content.

| mtd | Name | Size | Stock content | Ours |
|---|---|---|---|---|
| 0 | kernel | 8 MB | U-Boot boot block + stock kernel (6.9 MB, incl. initramfs) | U-Boot boot block untouched + **our kernel** (~3 MB) at 0x40000 |
| 1 | u-boot-env | 128 KB | settings | unchanged (only bar_* variables from the boot-logo app) |
| 2 | bbt | 512 KB | bad-block table | unchanged |
| 3 | boot-logo | 1 MB | logo | logo (boot-logo app) |
| 4 | backup | 8 MB | Sindoh /backup (~5 MB) | unchanged |
| 5 | recovery | 200 MB | **factory recovery set** (149 MB, see the correction below) | **unchanged** |
| 6 | filesystem | 294 MB | stock root + apps (264 MB) | **our root**: Debian + Klipper + Moonraker + Mainsail + screen app (~160-175 MB est.; ~265 MB usable, ~90 MB for G-codes/logs) |

**Why this layout:**
- **U-Boot is unchanged.** It still reads 0x7C0000 bytes from mtd0+0x40000
  and runs `bootm`. The stock bootargs it passes (`ubi.mtd=filesystem
  root=ubi0:filesystem rootfstype=ubifs`, `mtdparts`) are right for our
  root as well.
- **Back to stock = Sindoh's recovery sequence, from mtd5.** Our system runs
  the same steps (rewrite mtd0's kernel area and mtd6 from mtd5, extract the
  apps), and the printer is factory stock again. Sindoh's updates then work
  normally. Correction (2026-11-01): Sindoh's own /etc/system_recovery.sh
  uses the KARA-S file names and can't work on a DP200. Our version uses
  the rodin names: see kernel/revert_to_stock_plan.md.

**To build:**
1. **NAND write support in the mainline driver** (BCH write path, erase, bad
   blocks). Needed for a read-write UBIFS root, for updates and for running
   recovery. The critical path. Test only on NAND areas the owner approves.
2. **Installer stick** (stock firmware's auto_update.sh runs it):
   - check the hardware (board, NAND layout, Wi-Fi chip) and refuse anything
     unknown;
   - check that mtd5 holds the recovery set;
   - save the user's settings from the stock root (Wi-Fi networks, ...) to
     the new root;
   - write mtd6 (ubiupdatevol), verify it, then mtd0 last (the kernel
     only, never the U-Boot block), and verify that too.
3. **Recovery compatibility in our system:**
   - automatic recovery when the root is broken (the rcS behavior);
   - a revert stick that runs the recovery from mtd5;
   - a Sindoh `update.she` on a stick: offer to go back to stock first, so
     the stock updater can run it. **Decided 2026-11-03: this is the user's
     revert path**, needing no backup files from us (mtd5 + mtd4 hold
     everything; kernel/revert_to_stock_plan.md, "The user's revert path").
4. **Size budget** of the trimmed runtime, now with numpy, busybox,
   wpasupplicant and the firmware.
5. **Tests** on more printers and boards before release.

**Risk:** with our kernel in mtd0, a kernel that doesn't boot on some board
has no automatic fallback. That's the same exposure as a Sindoh firmware
update. Mitigations: the hardware check in the installer, writing mtd0
last, and testing on more boards.

The sections below (written 2026-10-18) put Klipper in mtd5 under the stock
kernel. **That design is superseded:** mtd5 holds the factory recovery set.

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

## Correction (2026-10-31): mtd5 holds the factory recovery set

"Not used by the boot path" was true only for a normal boot. Read-only from
the mainline kernel (UBI attached through the ioctl, on read-only MTD),
this printer's mtd5 has the UBI volume `recovery`: 1580 PEBs reserved
(~191 MB). Its files, 149 MB in all:

| File | Size | Restores |
|---|---|---|
| pa6170_rodin_nand.bin | 6.9 MB | mtd0: U-Boot + stock kernel |
| boot-logo_rodin.bin | 750 KB | mtd3 |
| nandrootfs.ubifs | 36 MB | mtd6, the stock root |
| update.tar.bz2 | 103 MB | /app and the rest of the apps |
| u-boot-env.bin, nand_write.sh | small | the env; Sindoh's restore script |

Who uses it:
- **Automatic:** rcS, from the stock kernel's built-in initramfs (root_fs),
  runs /etc/system_recovery.sh when the root is broken (no /etc/profile).
  That script mounts ubi2:recovery and is meant to rewrite mtd0, mtd3,
  mtd6 and the apps from it. On the DP200 it looks for
  pa6170_karas_nand.bin and boot-logo.bin, which aren't there, so it stops
  before writing (2026-11-01, see kernel/revert_to_stock_plan.md).
- **Manual:** `rodin_util.sh --system-recovery` (a service function) erases
  mtd6, so that the next boot recovers.
- **Firmware updates:** an update with a `recovery/` folder copies it into
  ubi2:recovery (3DWOX 1 update.sh; the DP200's 2020 update ships none).

So a Klipper root in mtd5 removes the printer's self-recovery for as long as
it is installed. Any update that refreshes recovery/ would then fail at
that step. The installer's mtd5 backup on the stick (nanddump) and the
remove stick's restore keep the set, but only on the stick. ~42 MB of the
volume is free.

## What a revert to stock can restore (2026-11-03)

File-by-file comparison of the test printer's live stock root (2020
firmware RODIN_200730_2, 2,962 files, md5 each) with the mtd5 recovery set
(nandrootfs.ubifs + update.tar.bz2, extracted from the PC copies whose md5s
match install/nand/recovery.md5) and with Sindoh's 2020 update
(image.app -> app.tar.bz2):

| Live files | Count | Restorable from |
|---|---|---|
| identical in the recovery set (factory 2017, GUI 1.2.51) | 1,734 | mtd5 |
| missing there or different, identical in the 2020 update | 1,178 | Sindoh's 2020 update (newer GUI, gemstone ELF, UIManager, tinydebug, libs, web, examples) |
| per-printer data | ~30 | **nowhere but the printer** |
| local edits / ours | ~20 | not needed |

- **Per-printer data:** `app/nvram/` (17 files: **karas.db** = serial,
  model ID / TLI (the Stanley conversion), calibration offsets, settings;
  NET*, WIF*, UAP0, PLAT, PJLO, STRM, jobid.dat, sc_details.dat),
  `etc/network/{interfaces,CONN_SSID,SSID_LIST}`,
  `etc/init.d/{wpa_supplicant.conf,wifi_sta_start.sh}`, `etc/resolv.conf`,
  `var/net-snmp/snmpd.conf`, `var/spool/cron/crontabs/root`,
  `app/homepage.txt`, `app/.browser/`, logs (`app/errorlog`,
  `app/update.log`, `var/log`).
- **Local edits:** `app/auto_update.sh` (whitespace only), `test/run.sh` and
  `test/restart.sh` (webcam 1 -> 4 fps), `app/ALPINE_MOUNT.sh`, an editor
  backup and a stray `usr/local/ssl/bin/-`; ours: DEBUG_MACHINE,
  etc/dp200-boot.sh, etc/profile(.stock).
- The Wi-Fi firmware in `lib/firmware/mrvl/` equals
  `lib/modules/8782/usb8782_uapsta.bin` (in the packages).
- None of the 12 DP200 updates (2016-2020) has the live auto_update.sh,
  run.sh or restart.sh: they are the local edits above.

**karas.db rebuilds itself from mtd4 (checked 2026-11-03).** The stock
/etc/profile mounts `ubi1:backup` (mtd4) on /backup, and Sindoh keeps a
copy there, `/backup/karas_backup.db` (rodin_util.sh writes it at
--set-tli, --set-serial and --test-end). The main program's NVRAM setup
(`db_setup` in the gemstone ELF) at every start:
- no karas.db ("No DB") or a failed integrity check -> copy the backup in
  (after checking the backup's integrity);
- karas.db without a model (TLI empty or "NOTLI") while the backup has one
  -> copy the backup in ("TLI integrity check fail... DB recovery");
- a broken backup -> copy the live DB over it.
So after Sindoh's recovery wipes mtd6, the first boot restores model,
serial and calibration from mtd4 - as long as **mtd4 is never written**
(already a rule). Test printer: the backup is intact, same TLI (3DP200Q)
and serial as live; the dumps differ only in one CONF_MACHINE_OFFSET value
(a later calibration), two newer saved Wi-Fi networks and two error-log
rows. Network settings (etc/network, the stock wpa_supplicant.conf) are
not in it.

**Consequence for the full mtd6 replacement:** no backup is required for a
correct recovery. Optional convenience: the installer saves the live
karas.db and the network files (~100 KB) to the stick, so a revert can also
restore the latest calibration and Wi-Fi. Never refresh mtd4's copy
ourselves. Then Sindoh's 2020 update brings the software to 2020.

## NAND wear and the root's writes (2026-11-01, agreed with the owner)

**Wear isn't a practical limit:**
- The chip is SLC (Macronix MX30LF4G18AC). Datasheet PM2129 rev. 1.3
  (2015-07-10; read 2026-11-02 from the copy at
  static.rapidonline.com/pdf/73-3784.pdf):
  - **Endurance: typically 100K P/E cycles**, with 4-bit ECC per
    (512+16) bytes (the "18A" option code = 4-bit ECC required).
  - Data retention 10 years; up to 4 partial programs (NOP) per page.
  - **Valid blocks: at least 4016 of 4096** (4 Gb part). Bad blocks are
    marked 00h in the first spare byte of pages 0 and 1, and new ones may
    appear in use: the driver's bad-block table must be kept (we never erase
    the marks; UBI handles new bad blocks).
  - **Block 0 is guaranteed good only up to 1K P/E cycles** (with ECC). It
    holds U-Boot, which we never write.
  Our BCH (16 bits per page) covers 4-bit ECC.
- Scale: mtd6 has ~2350 blocks of 128 KiB, so 100K cycles are ~30 TB of
  erases. At 1 GB of writes a day that is decades, before UBI's levelling.
- UBI levels wear over mtd6's ~2350 blocks.
- After years of stock use: mean erase count 10, max 127.

**Still, for our root:**
- **Logs in RAM:** tmpfs, capped, rotated. The latest log is copied to the
  NAND on an error or crash.
- **On the NAND:** G-code files (written once) and the power-loss resume
  state (small, batched by UBIFS, survives a power cut).
- **Mount options:** noatime, LZO compression.
- **A wear readout** (UBI max/mean EC) on the touchscreen and through
  Moonraker, with a warning far below the limit.
