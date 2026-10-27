# Custom boot logo

Turn any picture into the printer's boot logo. The tool packs it into an
encrypted `.she` update file, which the printer's own USB update
(`/app/auto_update.sh`) installs. You don't need a serial console, a root
shell or Klipper. It works on stock firmware and on Klipper-ported printers.

There are two versions, which share `bootlogo_core.py`:
- **`SindohBootLogo.exe`** / `sindoh_bootlogo_gui.py`: a Windows program
  with a live preview of the printer screen;
- **`sindoh_bootlogo.py`**: a command-line version for Windows, Linux and
  macOS.

Both do the encryption themselves; no `openssl` is needed.

## Supported printers

| Model | Screen (draw upright at) | Logo format | Where it lives | USB folder |
|---|---|---|---|---|
| DP200 / DP201 / Model 1 (Sindoh, Stanley, Leon3D, Mimaki) | 480 × 800 | 800 × 480 RGB565, turned 90° | NAND partition `boot-logo` (`mtd3`) | `_update_rodin` |
| 3DWOX 1 | 480 × 800 | same as DP200 | NAND `boot-logo` | `_update_rodin_up` |
| 3DWOX 2X | 480 × 800 | 800 × 480 24-bit BGR, turned 90° | older boards (Prime_r1): NAND `boot-logo`; newer (Prime_r2): `/boot/bootlogo.bin` | `_update_rodin_prime` |
| 3DWOX 1X | 480 × 800 | 800 × 480 24-bit BGR, turned 90° | `/boot/bootlogo.bin` on the eMMC | `_update_rodin_1x` |
| 3DWOX 7X | 1024 × 600 (landscape) | 1024 × 600 RGB565 | `/boot/bootlogo.bin` on the eMMC | `_update_rodin_h` |
| 3DWOX 30X | not supported yet | | | `_update_rodin_stf` |

Pick the model in the window or with `--model` (`dp200`, `3dwox1`, `2x`,
`1x`, `7x`). Each model's update key is built in. The 30X uses a key that
isn't known yet; see the end of this page.

- **The logo** is one raw frame-buffer image with no header. U-Boot shows it
  at power-on: the DP200 and 3DWOX 1 read it from NAND, while the 1X, 7X and
  newer 2X load the file `/boot/bootlogo.bin` from the eMMC. The 800 × 480
  panels are mounted in portrait, so those logos are stored turned 90°.
  Draw your logo upright; the tool turns it.
- **Progress bar:** a progress bar is drawn over the logo. Its colour is the
  U-Boot variable `bar_color`: Sindoh uses 0 for dark logos (Sindoh,
  Leon3D) and 1 for light ones (Stanley, Mimaki).
- **The stock logos:** DP200 and 3DWOX 1 have them in
  `/app/boot-logo_{sindoh,stanley,leon3d,mimaki}.bin`, and the others in
  `/boot/bootlogo_{sindoh,leon3d,rize}.bin`.
- **When it gets replaced:** an OEM firmware update (`update.she`) writes
  the brand's stock logo back, chosen by the printer's TLI. So does the
  factory `--set-tli` step on the DP200. After an OEM update, run your logo
  stick again.

## The window version

![The boot logo maker window](screenshot.png)

1. Start `SindohBootLogo.exe`, or `python sindoh_bootlogo_gui.py` with
   Python 3.8+ and `pip install pillow`. Then:
   - **Open picture...** (PNG, JPG, BMP, GIF, WebP, TIFF);
   - drag the picture to move it, use the mouse wheel to zoom, or use the
     Size / Rotate sliders, *Rotate 90*, *Mirror*, *Fit whole picture*,
     *Fill screen*, *Center*;
   - pick a background colour, *Invert colours*, and *Dither* (on for
     photos and gradients, off for flat-colour logos; it only matters on
     the 16-bit screens). The preview shows the screen's own colours;
   - choose the printer model (the preview changes to its screen) and the
     boot progress bar colour: Automatic,
     0 (dark logos), 1 (light logos) or *Leave as is*;
   - the update key is built in. If your printer uses another one,
     **Key file...** loads the `crypto_key.dat` from your printer's `/app`, or
     **Type key...** takes it as text.
2. **Save to USB stick...**: choose the stick, or any folder whose model
   folder (`_update_rodin`, `_update_rodin_up`, ...) you'll copy onto a
   FAT32 stick later. The file is
   checked by decrypting it again before it's saved.
3. Plug the stick into the printer. It shows "Touch to install the new boot
   logo"; touch the screen. The new logo appears at the next power-on.

**Open raw logo (.bin)...** loads a raw logo exactly, for example the
`bootlogo_original.bin` the stick saved. Saving it unchanged puts the old
logo back bit for bit.

To build the `.exe` yourself: `pip install pillow pyinstaller`, then run
`build_exe.bat` (it writes to `dist\`).

## The command-line version

```
python sindoh_bootlogo.py my_logo.png --model dp200
```
This writes `bootlogo_usb/_update_rodin/unmistakable_bootlogo.she` and
`bootlogo_usb/bootlogo_preview.png` (what the screen will show). Copy the
model folder (here `_update_rodin`) to the root of a FAT32 USB stick.

The first time, the stick also gets **`bootlogo_original.bin`**, the logo
that was on the printer. To put it back:
```
python sindoh_bootlogo.py bootlogo_original.bin --model dp200
```
(A `.bin` input is packed as it is.)

| Option | |
|---|---|
| `--fit contain` | whole picture, with `--bg` colour bars around it (default) |
| `--fit cover` | fill the screen, crop the edges |
| `--model` | `dp200` (default), `3dwox1`, `2x`, `1x`, `7x` |
| `--fit stretch` | distort to the screen size |
| `--bg COLOUR` | background for `contain` and transparent areas (default black) |
| `--invert` | invert the picture's colours |
| `--no-dither` | plain rounding to 16-bit colour, best for flat-colour logos. The default dithers, best for photos and gradients. (24-bit models need neither.) |
| `--bar-color auto/0/1/keep` | progress bar colour; `auto` uses 0 for dark pictures and 1 for light ones |
| `--dry-run` | the stick only runs the checks and writes nothing |
| `--decode logo.bin out.png` | view a raw logo (a backup, a stock logo) upright |
| `--out DIR` | output folder (default `bootlogo_usb`) |
| `--key-file crypto_key.dat` / `--key TEXT` | use another update key instead of the built-in one |

**Rehearsal (both versions):** with *Dry run* or `--dry-run`, the stick gets
an empty `dry_run` file. The printer then runs every check (partition, size,
md5, current logo) and writes nothing. Delete that file, or save again
without the option, to install for real.

## What runs on the printer

`unmistakable_bootlogo.sh` is packed inside the `.she` next to the image. It:
1. finds the logo: the NAND partition named `boot-logo` in `/proc/mtd` (not
   by number), or the file `/boot/bootlogo.bin`. On the 2X it picks by
   `/sys/kernel/board_name`: the file on Prime_r2 boards, NAND otherwise;
2. refuses to write if the image's size or md5 doesn't match, or if it's
   bigger than the partition;
3. returns without writing if the logo is already installed;
4. saves the current logo to the stick once (`bootlogo_original.bin`);
5. asks for a touch, then writes the logo and reads it back to compare.
   NAND: erase, then `nandwrite -p`. File: writes `bootlogo.bin.new`, then
   renames it over `bootlogo.bin`. Sindoh's updates leave `bootlogo.bin` as
   a symlink to the stock logo; the rename replaces the link, not the stock
   file;
6. sets `bar_color`.

A failed write leaves the printer booting normally (the logo is only a
picture). Run the stick again, or restore `bootlogo_original.bin`.

## How each model was checked

**DP200** (tested on a printer, 2026-10-27):
- the stock logos are reproduced exactly (PNG → `.bin` round trip, md5 equal);
- the Python Triple DES / AES match `openssl` byte for byte;
- the printer's OpenSSL 1.0 decrypts the `.she`, and the script passes every
  check in `dry_run` mode;
- a test logo was flashed and read back (`mtd3` md5 equals the image);
- the DP201's OEM update is byte for byte the DP200's.

**3DWOX 1, 2X, 1X, 7X** were checked against Sindoh's own updates:
`RODUP_220111_1`, `PRIME_210419_2`, `ROD1X_190917_1` and `RODNH_210602_1`.
- **Keys:** each update decrypts with the model's built-in key, and the
  printer's own `crypto_key.dat` gives the same key.
- **The 3DWOX 1** runs the same firmware as the DP200, with `RODIN_SUB=U`;
  its stock logos are byte for byte the DP200's.
- **Logo formats** come from the stock logo files in each update. Every one
  converts to a picture and back to the identical file.
- **Install path:** each model's `update.sh` / `auto_update.sh` shows how the
  logo is installed, and that `unmistakable*.she` files in the model's USB
  folder are run the same way as on the DP200. The 1X and 7X U-Boot loads
  `/boot/bootlogo.bin`.
- **The sticks** this tool makes decrypt with `openssl` and unpack with
  `tar -xj`, the way each printer does it.
- **The file-mode script** ran on the DP200's busybox shell, in a `/tmp`
  copy, over a symlinked stock logo:
  - the dry run wrote nothing;
  - the install replaced the link and left the stock file alone;
  - the backup held the old logo;
  - a second run said "already installed".

None of these four has been run on its own hardware yet. Use *Dry run* the
first time.

## 3DWOX 30X (not supported yet)

Its update (`RDSTF_220422_1`, folder `_update_rodin_stf`) is AES-encrypted
like the 1X and 7X, but not with any key tried so far. Those were the
DP200 key plus every one- or two-character ending; the 1X and 7X keys
follow that pattern. With the key, from a 30X's `/app/crypto_key.dat`, it
can probably be added like the 7X: its system image is the same size.
