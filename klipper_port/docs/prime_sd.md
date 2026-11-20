# Sindoh 2X ("Prime"): the factory recovery SD card

**Source:** an 8 GB SD card (SanDisk SL08G, 2018) from the owner's RODIN
PRIME board, read on the dev printer on 2026-11-20 with everything mounted
read-only (`ro,noload`); nothing on the card was changed. A copy of its
used area (819 MiB, md5 `0ed41ab4e1929b9bae7b943f0460b99f`) and the
decrypted recovery partition stay on the owner's PC (`prime_sd/`). They
hold Sindoh's firmware and are never published. Inferences are marked
"(our reading)".

## What it is

A **NAND recovery card for the 2X r1** (88PA6270 with NAND). The 6270's
boot ROM starts it from SD; it boots a small Linux, opens its encrypted
partition and rewrites the printer's NAND root and `/app` with
`PRIME_190726_2`, keeping the printer's own karas.db when it can be read.

| Part | Sectors | Contents |
|---|---|---|
| sector 0 | | Marvell boot image header (magic `c1deed1c`, as in the DP200's mtd0) |
| before p1 | 1-1279 | MiniLoader (DDR, PLL, code validation), built 2018-01-12 from `Rodin_Prime_BSP`, commit `130c164` |
| p1 | 1280, 3.1 MB, no filesystem | U-Boot for the 6270 (`mv6270-toc`, `mv6220-toc`, `destiny-fpga` boards) |
| p2 | 7680, 302 MB, ext4 | the recovery Linux (Buildroot 2016.02): `/boot/uImage`, `MiniLoader.bin`, DTBs `mv6220-{ffc,toc}`, `mv6270-{ffc,toc}`; `/app/cryptsetup`, `sd_crypt_util.sh`; `S99recovery` |
| p3 | 628736, 512 MB, LUKS1 `aes-cbc-essiv:sha256` | the recovery set (below) |
| p4 | 1677312, 6.6 GB | empty (all zeros where sampled) |

- **U-Boot on the card** loads the kernel and `mv6270-toc.dtb` from
  `mmc 2:2` (the card's p2) with `ext2load`.
- **The encryption key is not secret.** `sd_crypt_util.sh` builds it from
  the board itself: the `/proc/cpuinfo` "Hardware" string (`Marvell
  Pegmatite (Device Tree)` on a 6270) is AES-256-CBC-encrypted with its own
  first 16 characters as key and IV, and that file is the LUKS passphrase.
  Key slot 0 opens with it. (our reading) It only ties the card to a 6270
  board; it protects nothing.

## The recovery set (p3)

- `nandwrite/nand_write_rodin_prime.sh` (started by `run.sh`):
  1. waits for a touch ("Please touch LCD to recovery F/W or power off");
  2. attaches UBI on mtd7, copies `app/nvram/karas.db` out if it reads;
  3. erases and `ubiformat`s mtd7, makes one UBI volume `filesystem`;
  4. untars `rootfs.tar.bz2` (62 MB) and `app.tar.bz2` (115 MB) into it;
  5. puts back the saved karas.db, or the factory `karas.db.rodin_prime`;
  6. copies both tarballs into `/recovery` on the new root.
  The kernel, DTB, U-Boot env and boot-logo writes are present but
  commented out: it rewrites only the root.
- `snapshot_version.sh`: `PRIME_190726_2`.
- `karas.db.rodin_prime`: the factory database (`INST_MACHINE` TLI
  `3D2XAQ`), with a `CONF_ENGINE_GEAR_RATIO` table the 1X does not have.
- A recovery screen: `launcher/appBrowser`, `app/tinydebug`, `app/display.sh`.

## 2X r1 NAND layout (from the recovery script and U-Boot)

| mtd | Size | Name |
|---|---|---|
| 0 | 1 MB | miniloader |
| 1 | 1 MB | r4 |
| 2 | 1 MB | u-boot-env |
| 3 | 2 MB | boot-logo |
| 4 | 1 MB | u-boot |
| 5 | 5 MB | kernel |
| 6 | 512 KB | dtb |
| 7 | rest (244.5 MB) | filesystem (UBI, volume `filesystem`) |

U-Boot names the NAND controller `mv61x0_nand`, as on the DP200.

## Motor currents: factory defaults

`CONF_ENGINE_PWM` in the factory database, X/Y/Z/E offsets:

| Row | Prime factory | Owner's 1X | Dev DP200 (Stanley) |
|---|---|---|---|
| NO=1-3 | -15 / +15 / +30 / +50 | -15 / +15 / +30 / +50 | |
| **NO=4** (the live row) | -15 / +20 / +30 / +50 | **-15 / +40 / +40 / +50** | -15 / +20 / +30 / +50 |

So the dev printer still has Sindoh's factory row 4, and the 1X has been
tuned (Y and Z). Reading each printer's own row, as the installer does, is
the right call.

## Why it matters (our reading)

- **An unbrick route for the 2X r1** exists and is Sindoh's own: an SD card
  the boot ROM starts. The same header magic as the DP200's mtd0 suggests
  the 6170 boot ROM's SD mode (docs/sd_boot_plan.md) works the same way.
- **A known-good 6270 boot chain** (MiniLoader, U-Boot, kernel, DTBs) to
  study for a 6270 Klipper port, next to the 1X survey (docs/1x.md).
