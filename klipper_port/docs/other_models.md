# Other Sindoh models (groundwork)

What Sindoh's own firmware updates show about the rest of the 3DWOX range.
This is a starting point for bringing the Klipper port, and the USB install
path, to other models.

**Source:** the newest update of each model in the public Sindoh firmware
Drive (FFF folder), downloaded 2026-10-27:

| Folder | Update |
|---|---|
| 3DWOX 1 | `RODUP_220111_1` |
| 2X | `PRIME_210419_2` |
| 1X | `ROD1X_190917_1` |
| 7X | `RODNH_210602_1` |
| 30X | `RDSTF_220422_1` |
| DP201 | `RODIN_200730_2`, byte for byte the DP200's update |

Nothing here was run on those printers. It was read from the updates only
(decrypted, unpacked, never executed).

## Summary

| Model | SoC / motion firmware | Kernel | Storage | USB folder | `.she` cipher, key |
|---|---|---|---|---|---|
| DP200 / DP201 / Model 1 | 88PA6170 "gemstone", `upc.ko` | 3.2 | NAND | `_update_rodin` | des3, `sindoh024601779` |
| 3DWOX 1 | same as DP200 (same firmware, `RODIN_SUB=U`) | 3.2 | NAND | `_update_rodin_up` | AES, `sindoh024601779U` |
| 2X ("Prime") | 88PA6270 "granite2", `upc_6270.ko` | 4.2.8 | r1: NAND; r2: eMMC | `_update_rodin_prime` | des3, `sindoh024601779` |
| 1X | 88PA6270 "granite2", `upc_6270.ko` | 4.2.8 | eMMC | `_update_rodin_1x` | AES, `sindoh0246017791` |
| 7X ("Rodin H") | 88PA6270 "granite2", `upc_6270.ko` | 4.2.8 | eMMC | `_update_rodin_h` | AES, `sindoh024601779H` |
| 30X ("STF") | ? | ? | ? | `_update_rodin_stf` | AES, key unknown |

- **Ciphers:**
  - des3 is `openssl des3 -salt` (MD5 key derivation);
  - AES is `openssl aes-256-cbc -K hex(key) -iv hex(key)`, with the key
    zero-padded.
- **Key files:** each key is what that model's `/app/crypto_key.dat`
  decrypts to. The DP200 and 2X files are des3 with an empty password; the
  1X and 7X files are `aes-256-cbc -salt` with an empty password.
- **One update script for several boards:** the 1X/7X `update.sh` handles
  boards `H_r1`, `1X_r1`, `Prime_r2`, `M_P_r1` and `M_H_r1` ("Myron"
  printers, with folders `_update_myron_p` and `_update_myron_h`), plus
  `TOC`. It tells them apart by `/sys/kernel/board_name`.
- **Device trees:** `mv6270-{1X,H,M-H,M-P,Prime-r2,toc}.dtb`.
- **USB auto-update:** every model's `/app/auto_update.sh` decrypts and runs
  `unmistakable*.she` from its USB folder before `update.she`, the same way
  as the DP200. So the boot logo tool and a Klipper USB installer can use
  the same route on all of them (except the 30X, until its key is known).

## What this means for Klipper

- **3DWOX 1:** the DP200 work should carry over almost unchanged. It's the
  same firmware, SoC, kernel and motion firmware, with a different USB
  folder and key. The hardware (motors, heaters, sensors) still needs
  checking.
- **2X, 1X, 7X:** a new platform. They use the 88PA6270 with Cortex-A53
  cores (the device tree also lists a Cortex-A15 interrupt controller) and
  Linux 4.2.8 with device trees. The stock motion firmware is "granite2"
  (`marvell_lspsdk_3dp_granite2-debug_stripped.elf`) and the UPC driver is
  `upc_6270.ko`. Motion likely still runs on UPC cores, as on the DP200, so
  the Klipper UPC port is the right model. But the core type, memory map
  (ITCM/DTCM) and step/ADC peripherals must be probed again, as was done
  for the DP200 (`upc_fw/probe/`). The DTB lists a `dcmotor` block.
- **88PA6270 references in Marvell's public code**
  (kernel/marvell_github.md):
  - Marvell's A3700-utils-marvell repo (`wtptp/`, the TIM builder and the
    WTP downloader) lists `88PA62_70` (GRANITE2) as a platform. That
    downloader talks to the BootROM over UART/USB and is Marvell's tool for
    loading a first-stage image onto a board with no working boot flash.
  - **If the 6270 BootROM accepts it, it gives these models:**
    - an unbrick path;
    - a way to run our own U-Boot or kernel without touching eMMC/NAND;
    - a reference for their TIM boot-header format (the TIM parser is
      included).
  - Not tried; the tool and TIM format details have to be checked against
    a 2X/1X/7X boot partition first.
  - Nothing else for these chips is in that GitHub org: no kernel, no U-Boot.
- **2X** has two extruders (to be worked out with hardware). It comes in
  two board revisions: Prime_r1 boots from NAND, Prime_r2 from eMMC.
- **eMMC boards** have partitions p1 (U-Boot), p2 (root with `/boot`), p3
  (systemdata), p5 (recovery) and p6 (userdata). A Klipper chroot could go
  on userdata or an SD card instead of the DP200's SD-card root.
- **30X:** needs the key, and the key is **not guessable** — settled
  2026-11-11. The `karaspinetree` Prime (2X) firmware (unencrypted, from
  `firmware.sindoh.com`) let us confirm the whole scheme end to end:
  - each model's `/app/crypto_key.dat` is an openssl blob with an **empty
    password** (`des3` or `aes-256-cbc -d -k "" -md md5`) that unpacks (bzip2
    tar) to `crypto_key.txt` = the KEY; `update.she` is then `des3 -k KEY`
    or `aes-256-cbc -K hex(KEY) -iv hex(KEY)`;
  - the Prime's KEY is `sindoh024601779`, yet its `RODIN_SUB` is `P`, so the
    suffix is **not** derived from the model tag — the base+suffix pattern was
    a coincidence, and brute-forcing suffixes is a dead end (confirmed by the
    STF sweep).
  - So the only way in is a **real 30X's `/app/crypto_key.dat`** (decrypt it
    with the empty password → key). No 30X key file exists in any local dump.
  - The vendor store `http://firmware.sindoh.com/karaspinetree/` (HTTP basic auth,
    the original dev's login embedded in `net_update.sh` "karaspinetree_user:karaspinetree_sindoh" ) is now behind
    CloudFront and returns **502** (origin gone) as of 2026-11-11.

## Boot logo per model

These are implemented in [catawalks/sindoh-boot-logo](https://github.com/catawalks/sindoh-boot-logo).

| Model | Format | Location |
|---|---|---|
| DP200, 3DWOX 1 | 800×480 RGB565, portrait-mounted | NAND `boot-logo` (`mtd3`) |
| 2X | 800×480 24-bit BGR, portrait-mounted | r1: NAND `mtd3`; r2: `/boot/bootlogo.bin` |
| 1X | 800×480 24-bit BGR, portrait-mounted | `/boot/bootlogo.bin` (U-Boot `ext2load`) |
| 7X | 1024×600 RGB565, landscape | `/boot/bootlogo.bin` |

On eMMC models, Sindoh's update makes `/boot/bootlogo.bin` a symlink to
`bootlogo_{sindoh,leon3d,rize}.bin` (`rsync -l` of a link). Replace the
link; don't write through it.

## Local copies (not in git)

The downloads and decrypted parts are in `D:\DP200\backup\oem_models\<model>\`
and `D:\DP200\backup\oem_3dwox1\`. Each folder has:
- `dl/`: the zip;
- `x/`: the zip unpacked;
- `dec/`: the decrypted scripts and archives;
- `app/`: files pulled out of `/app` and `/boot`.
