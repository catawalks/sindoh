#!/usr/bin/env python3
"""Make a custom boot logo for a Sindoh DP200 / Model 1 or 3DWOX 1.

Command-line version (Windows, Linux, macOS); sindoh_bootlogo_gui.py is the
same with a window. Turns any picture (PNG, JPG, ...) into the printer's raw
boot-logo format and packs it, with a small install script, into an encrypted
.she file that the printer's own USB update (/app/auto_update.sh) runs:

    python sindoh_bootlogo.py my_logo.png

then copy the generated _update_rodin folder to the root of a FAT32 USB
stick, plug it into the printer and touch the screen when asked.

The boot logo (DP200): flash partition "boot-logo" (mtd3, 1 MiB), read by
U-Boot at power-on. It holds one raw frame-buffer image: 800 x 480 pixels,
RGB565 little-endian (768000 bytes). The panel is mounted in portrait, so the
picture is stored turned 90 degrees: draw your logo upright at 480 x 800.
U-Boot draws a progress bar over it; its colour is the U-Boot variable
bar_color (0 for dark logos, 1 for light ones, like Sindoh's own files).

Other commands:
    python sindoh_bootlogo.py --decode bootlogo_original.bin original.png
        show a raw logo (e.g. the backup the stick saves) as an upright PNG
    python sindoh_bootlogo.py bootlogo_original.bin
        a raw .bin logo is packed as it is (restore the original)

The update key of each model is built in. If your printer uses another one,
pass its /app/crypto_key.dat with --key-file, or the key itself with --key.
Needs Python 3.8+ and Pillow (pip install pillow).
"""
import argparse
import hashlib
import os
import sys

try:
    from PIL import Image, ImageColor, ImageOps
except ImportError:
    sys.exit("This tool needs Pillow:  pip install pillow")
import bootlogo_core as core


def fit_image(path, size, fit, bg):
    im = ImageOps.exif_transpose(Image.open(path))
    # flatten transparency onto the background colour
    im = im.convert("RGBA")
    base = Image.new("RGBA", im.size, bg + (255,))
    im = Image.alpha_composite(base, im).convert("RGB")
    if fit == "stretch":
        return im.resize(size, Image.Resampling.LANCZOS)
    if fit == "cover":
        return ImageOps.fit(im, size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, bg)
    im = ImageOps.contain(im, size, Image.Resampling.LANCZOS)
    canvas.paste(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
    return canvas


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Example: python sindoh_bootlogo.py logo.png")
    ap.add_argument("image", nargs="?", help="your picture, or a raw logo .bin to pack as is")
    ap.add_argument("--key-file", help="use the key in this crypto_key.dat (from the printer's /app) instead of the built-in one")
    ap.add_argument("--key", help="use this update password instead of the built-in one")
    ap.add_argument("--model", choices=sorted(core.MODELS), default="dp200")
    ap.add_argument("--experimental", action="store_true",
                    help="allow a model whose logo format is not verified yet")
    ap.add_argument("--fit", choices=("contain", "cover", "stretch"), default="contain",
                    help="contain: whole picture, bars around it (default); "
                         "cover: fill the screen, crop edges; stretch: distort to fit")
    ap.add_argument("--bg", default="black", help="background colour for 'contain' and transparency")
    ap.add_argument("--invert", action="store_true", help="invert the picture's colours")
    ap.add_argument("--no-dither", action="store_true",
                    help="plain rounding to 16-bit colour (best for flat-colour logos)")
    ap.add_argument("--bar-color", choices=("auto", "0", "1", "keep"), default="auto",
                    help="progress bar colour: 0 for dark logos, 1 for light ones (auto: from the picture)")
    ap.add_argument("--dry-run", action="store_true",
                    help="the stick only runs the checks and writes nothing")
    ap.add_argument("--out", default="bootlogo_usb", help="output folder (default: bootlogo_usb)")
    ap.add_argument("--decode", nargs=2, metavar=("LOGO_BIN", "PNG"),
                    help="convert a raw logo to an upright PNG and exit")
    a = ap.parse_args()
    m = core.MODELS[a.model]
    fb_bytes = m["fb"][0] * m["fb"][1] * 2

    if a.decode:
        data = open(a.decode[0], "rb").read()[:fb_bytes]
        if len(data) != fb_bytes:
            sys.exit(f"{a.decode[0]}: need {fb_bytes} bytes")
        core.fb_to_upright(core.from_rgb565(data, m["fb"])).save(a.decode[1])
        print(f"wrote {a.decode[1]}")
        return

    if not a.image:
        ap.error("give a picture (or --decode)")
    if not m["verified"] and not a.experimental:
        sys.exit(f"The {a.model} boot-logo format is not verified yet.\n"
                 "Run with --experimental to try anyway: the stick saves the old logo\n"
                 "(bootlogo_original.bin) so it can be put back.")
    try:
        key = a.key or (core.key_from_file(a.key_file, m["cipher"]) if a.key_file else m["key"])
    except ValueError as e:
        sys.exit(f"{e} - try --key")

    if a.image.lower().endswith(".bin"):
        raw = open(a.image, "rb").read()[:fb_bytes]        # a logo .bin / mtd3 dump
        if len(raw) != fb_bytes:
            sys.exit(f"{a.image}: a raw logo must be at least {fb_bytes} bytes")
    else:
        try:
            bg = ImageColor.getrgb(a.bg)[:3]
        except ValueError:
            sys.exit(f"unknown colour: {a.bg}")
        upright = fit_image(a.image, m["upright"], a.fit, bg)
        if a.invert:
            upright = ImageOps.invert(upright)
        raw = core.to_rgb565(core.upright_to_fb(upright), not a.no_dither)
    upright = core.fb_to_upright(core.from_rgb565(raw, m["fb"]))

    bar = core.auto_bar_color(upright) if a.bar_color == "auto" else a.bar_color
    she = core.build_usb(raw, a.model, key, bar, a.out, a.dry_run)
    os.makedirs(a.out, exist_ok=True)
    open(os.path.join(a.out, "bootlogo_new.bin"), "wb").write(raw)
    upright.save(os.path.join(a.out, "bootlogo_preview.png"))

    print(f"wrote {she}  (verified)" + ("  DRY RUN" if a.dry_run else ""))
    print(f"preview (as the screen shows it): {os.path.join(a.out, 'bootlogo_preview.png')}")
    print(f"progress bar colour: {bar}   logo md5: {hashlib.md5(raw).hexdigest()}")
    print(f"Copy the {m['folder']} folder to the root of a FAT32 USB stick, plug it into\n"
          "the printer and touch the screen when asked. The stick keeps the old logo\n"
          "as bootlogo_original.bin.")


if __name__ == "__main__":
    main()
