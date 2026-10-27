# Custom boot logo

`sindoh_bootlogo.py` turns any picture into the printer's boot logo and packs
it into an encrypted `.she` update file. The printer's own USB update
(`/app/auto_update.sh`) installs that file. You don't need a serial console, a
root shell or Klipper. It works on stock firmware and on Klipper-ported
printers.

## What the boot logo is (DP200, verified)

- **Where:** the flash partition `boot-logo` (`mtd3`, 1 MiB). U-Boot reads it
  at power-on.
- **Format:** one raw frame-buffer image, **800 × 480 pixels, RGB565
  little-endian, no header** (768000 bytes). The panel is mounted in
  portrait, so the image is stored turned 90°. Draw your logo **upright at
  480 × 800**; the tool turns it.
- **Progress bar:** U-Boot draws a progress bar over the logo. Its colour is
  the U-Boot variable `bar_color`: Sindoh uses 0 for dark logos (Sindoh,
  Leon3D) and 1 for light ones (Stanley, Mimaki).
- **The stock logos** are in `/app/boot-logo_{sindoh,stanley,leon3d,mimaki}.bin`.
  The OEM update (`image.logo`) carries `boot-logo_rodin.bin`, which is the
  same file as the Sindoh one.
- **When it gets replaced:** an OEM firmware update (`update.she`) writes
  the brand's stock logo back, chosen by the printer's TLI. So does the
  factory `--set-tli` step. After an OEM update, run your logo stick again.

## Use

Needs Python 3.8+, Pillow (`pip install pillow`) and the `openssl` command
(Linux/macOS have it; on Windows, Git for Windows includes one and the tool
finds it).

1. Copy `/app/crypto_key.dat` from your printer, or from a backup of its
   `/app`. The update password is not included in this tool.
2. Make the stick files:
   ```
   python sindoh_bootlogo.py my_logo.png --key-file crypto_key.dat
   ```
   This writes `bootlogo_usb/_update_rodin/unmistakable_bootlogo.she`. Check
   `bootlogo_usb/bootlogo_preview.png`: it shows exactly what the screen will
   show (16-bit colour).
3. Copy the `_update_rodin` folder to the root of a FAT32 USB stick and plug
   the stick into the printer. It shows "Touch to install the new boot
   logo"; touch the screen. The new logo appears at the next power-on.

The first time, the stick also gets **`bootlogo_original.bin`**, the logo
that was on the printer. To put it back:
```
python sindoh_bootlogo.py bootlogo_original.bin --key-file crypto_key.dat
```
(A `.bin` input is packed as it is.)

Options:

| Option | |
|---|---|
| `--fit contain` | whole picture, with `--bg` colour bars around it (default) |
| `--fit cover` | fill the screen, crop the edges |
| `--fit stretch` | distort to 480 × 800 |
| `--bg COLOUR` | background for `contain` and transparent areas (default black) |
| `--no-dither` | plain rounding to 16-bit colour, best for flat-colour logos. The default dithers, best for photos and gradients. |
| `--bar-color auto/0/1/keep` | progress bar colour; `auto` uses 0 for dark pictures and 1 for light ones |
| `--decode logo.bin out.png` | view a raw logo (a backup, a stock logo) upright |
| `--out DIR` | output folder (default `bootlogo_usb`) |

**Rehearsal:** an empty file named `dry_run` in `_update_rodin` on the stick
runs every check (partition, size, md5, current logo) and writes nothing.

## What runs on the printer

`unmistakable_bootlogo.sh` is packed inside the `.she` next to the image. It:
1. finds the partition by its name `boot-logo` in `/proc/mtd`, not by
   number;
2. refuses to write if the image is bigger than the partition, or if its
   size or md5 doesn't match;
3. returns without writing if the logo is already installed;
4. saves the current logo to the stick once (`bootlogo_original.bin`);
5. asks for a touch, then erases the partition, writes it (`nandwrite -p`)
   and reads it back to compare;
6. sets `bar_color`.

A failed write leaves the printer booting normally (the logo is only a
picture). Run the stick again, or restore `bootlogo_original.bin`.

Tested 2026-10-27 on a DP200:
- the stock logos are reproduced exactly (PNG → `.bin` round trip, md5 equal);
- the printer's OpenSSL 1.0 decrypts the `.she`, and the script passes every
  check in `dry_run` mode.

## Newer 3DWOX 1 models (not verified)

These printers use AES-256-CBC `.she` files and a `_update_rodin_up` folder
(see the main README). `--model 3dwox1 --experimental` packs that way, but
their logo partition and panel size are unknown. Until someone checks them,
the tool refuses this model without `--experimental`. What would settle it:
- a 3DWOX 1 OEM update (its `image.logo`, or `/app/boot-logo_*.bin`
  from the printer);
- or the output of `cat /proc/mtd` and `cat /sys/class/graphics/fb0/virtual_size`
  from one.

If its logo is the same 768000-byte format, only the cipher differs. Even
then, the on-printer script checks the partition name and size before
writing.
