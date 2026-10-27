#!/usr/bin/env python3
"""Make a custom boot logo for a Sindoh DP200 (3DWOX DP200 / Model 1 family).

Turns any picture (PNG, JPG, ...) into the printer's raw boot-logo format
and packs it, with a small install script, into an encrypted .she file that
the printer's own USB update (/app/auto_update.sh) runs:

    python sindoh_bootlogo.py my_logo.png --key-file crypto_key.dat

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
    python sindoh_bootlogo.py bootlogo_original.bin --key-file crypto_key.dat
        a raw 768000-byte logo is packed as it is (restore the original)

The encryption key is not part of this tool: pass the crypto_key.dat from
your own printer (/app/crypto_key.dat), or --key if you already know it.
Needs Python 3.8+, Pillow (pip install pillow) and the openssl command line
tool (Linux/macOS: installed; Windows: Git for Windows includes one).
"""
import argparse
import bz2
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("This tool needs Pillow:  pip install pillow")

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT_NAME = "unmistakable_bootlogo.sh"
LOGO_NAME = "bootlogo_new.bin"

# Per printer family: logo geometry, USB folder and .she cipher.
# Only the DP200 is verified. The 3DWOX 1 entry follows the cipher described
# in this repository's README; its logo partition and panel are unknown until
# someone checks a 3DWOX 1 update or a dump of its boot-logo partition.
MODELS = {
    "dp200": dict(fb=(800, 480), upright=(480, 800), folder="_update_rodin",
                  cipher="des3", verified=True),
    "3dwox1": dict(fb=(800, 480), upright=(480, 800), folder="_update_rodin_up",
                   cipher="aes", verified=False),
}


# ---------------------------------------------------------------- image ----

def parse_color(text):
    try:
        from PIL import ImageColor
        return ImageColor.getrgb(text)[:3]
    except ValueError:
        sys.exit(f"unknown colour: {text}")


def fit_image(path, size, fit, bg):
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    # flatten transparency onto the background colour
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        base = Image.new("RGBA", im.size, bg + (255,))
        im = Image.alpha_composite(base, im)
    im = im.convert("RGB")
    if fit == "stretch":
        return im.resize(size, Image.Resampling.LANCZOS)
    if fit == "cover":
        return ImageOps.fit(im, size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, bg)
    im = ImageOps.contain(im, size, Image.Resampling.LANCZOS)
    canvas.paste(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
    return canvas


def to_rgb565(im, dither):
    """RGB image -> RGB565 little-endian bytes (Floyd-Steinberg if dither)."""
    w, h = im.size
    data = im.tobytes()
    px = [tuple(data[i:i + 3]) for i in range(0, len(data), 3)]
    out = bytearray(w * h * 2)
    if not dither:
        for i, (r, g, b) in enumerate(px):
            v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            out[2 * i] = v & 0xFF
            out[2 * i + 1] = v >> 8
        return bytes(out)
    # error diffusion per channel, one row of error at a time
    nxt = [[0.0, 0.0, 0.0] for _ in range(w + 2)]
    for y in range(h):
        cur, nxt = nxt, [[0.0, 0.0, 0.0] for _ in range(w + 2)]
        row = y * w
        for x in range(w):
            r0, g0, b0 = px[row + x]
            e = cur[x + 1]
            r = min(255.0, max(0.0, r0 + e[0]))
            g = min(255.0, max(0.0, g0 + e[1]))
            b = min(255.0, max(0.0, b0 + e[2]))
            r5, g6, b5 = int(r + 4) >> 3, int(g + 2) >> 2, int(b + 4) >> 3
            r5, g6, b5 = min(r5, 31), min(g6, 63), min(b5, 31)
            er = r - (r5 * 255 / 31)
            eg = g - (g6 * 255 / 63)
            eb = b - (b5 * 255 / 31)
            for (dx, ee, f) in ((1, cur, 7 / 16), (-1, nxt, 3 / 16),
                                (0, nxt, 5 / 16), (1, nxt, 1 / 16)):
                t = ee[x + 1 + dx]
                t[0] += er * f
                t[1] += eg * f
                t[2] += eb * f
            v = (r5 << 11) | (g6 << 5) | b5
            out[2 * (row + x)] = v & 0xFF
            out[2 * (row + x) + 1] = v >> 8
    return bytes(out)


def from_rgb565(data, fb):
    return Image.frombytes("RGB", fb, data, "raw", "BGR;16")


def fb_to_upright(im):
    # panel mounted in portrait: fb (x, y) shows at upright (u = y, v = 799 - x)
    return im.transpose(Image.Transpose.ROTATE_90)


def upright_to_fb(im):
    return im.transpose(Image.Transpose.ROTATE_270)


# --------------------------------------------------------------- crypto ----

def find_openssl():
    exe = shutil.which("openssl")
    if not exe and os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            cand = os.path.join(base, "Git", "usr", "bin", "openssl.exe")
            if os.path.exists(cand):
                exe = cand
                break
    if not exe:
        sys.exit("openssl not found (Windows: install Git for Windows, or put openssl on PATH)")
    return exe


def openssl(exe, args, data):
    p = subprocess.run([exe] + args, input=data, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode(errors="replace").strip())
    return p.stdout


def first_tar_member(blob):
    with tarfile.open(fileobj=io.BytesIO(bz2.decompress(blob))) as t:
        for m in t.getmembers():
            if m.isfile():
                return t.extractfile(m).read()
    raise ValueError("empty archive")


def key_from_file(exe, path, cipher):
    """The update password stored (encrypted) in the printer's crypto_key.dat."""
    blob = open(path, "rb").read()
    attempts = []
    if cipher == "des3":
        attempts.append(["des3", "-d", "-salt", "-md", "md5", "-pass", "pass:"])
    else:
        h = b"SINDOH".hex()
        attempts.append(["aes-256-cbc", "-d", "-K", h, "-iv", h])
        attempts.append(["aes-256-cbc", "-d", "-md", "md5", "-pass", "pass:SINDOH"])
    for a in attempts:
        try:
            plain = openssl(exe, a, blob)
        except RuntimeError:
            continue
        for unpack in (first_tar_member, lambda b: b):
            try:
                key = unpack(plain).strip().decode("ascii")
            except Exception:
                continue
            if key and key.isprintable():
                return key
    sys.exit(f"could not read the key from {path} (wrong model? try --key)")


def encrypt(exe, cipher, key, data):
    if cipher == "des3":
        # old OpenSSL default key derivation (MD5), as the printer's 1.0.x uses
        return openssl(exe, ["des3", "-e", "-salt", "-md", "md5", "-pass", "pass:" + key], data)
    h = key.encode().hex()
    return openssl(exe, ["aes-256-cbc", "-e", "-K", h, "-iv", h[:32]], data)


def decrypt(exe, cipher, key, data):
    if cipher == "des3":
        return openssl(exe, ["des3", "-d", "-salt", "-md", "md5", "-pass", "pass:" + key], data)
    h = key.encode().hex()
    return openssl(exe, ["aes-256-cbc", "-d", "-K", h, "-iv", h[:32]], data)


# ----------------------------------------------------------------- pack ----

def make_tar_bz2(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as t:
        for name, data, mode in files:
            ti = tarfile.TarInfo(name)
            ti.size, ti.mode, ti.uid, ti.gid = len(data), mode, 0, 0
            ti.uname = ti.gname = "root"
            t.addfile(ti, io.BytesIO(data))
    return bz2.compress(buf.getvalue(), 9)


def install_script(size, md5, bar_color):
    text = open(os.path.join(HERE, SCRIPT_NAME), "rb").read().replace(b"\r\n", b"\n")
    return (text.replace(b"@SIZE@", str(size).encode())
                .replace(b"@MD5@", md5.encode())
                .replace(b"@BAR_COLOR@", str(bar_color).encode()))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Example: python sindoh_bootlogo.py logo.png --key-file crypto_key.dat")
    ap.add_argument("image", nargs="?", help="your picture, or a raw logo .bin to pack as is")
    ap.add_argument("--key-file", help="crypto_key.dat copied from your printer's /app")
    ap.add_argument("--key", help="the update password itself, instead of --key-file")
    ap.add_argument("--model", choices=sorted(MODELS), default="dp200")
    ap.add_argument("--experimental", action="store_true",
                    help="allow a model whose logo format is not verified yet")
    ap.add_argument("--fit", choices=("contain", "cover", "stretch"), default="contain",
                    help="contain: whole picture, bars around it (default); "
                         "cover: fill the screen, crop edges; stretch: distort to fit")
    ap.add_argument("--bg", default="black", help="background colour for 'contain' and transparency")
    ap.add_argument("--no-dither", action="store_true",
                    help="plain rounding to 16-bit colour (best for flat-colour logos)")
    ap.add_argument("--bar-color", choices=("auto", "0", "1", "keep"), default="auto",
                    help="progress bar colour: 0 for dark logos, 1 for light ones (auto: from the picture)")
    ap.add_argument("--out", default="bootlogo_usb", help="output folder (default: bootlogo_usb)")
    ap.add_argument("--decode", nargs=2, metavar=("LOGO_BIN", "PNG"),
                    help="convert a raw logo to an upright PNG and exit")
    a = ap.parse_args()
    m = MODELS[a.model]
    fb_bytes = m["fb"][0] * m["fb"][1] * 2

    if a.decode:
        data = open(a.decode[0], "rb").read()[:fb_bytes]
        if len(data) != fb_bytes:
            sys.exit(f"{a.decode[0]}: need {fb_bytes} bytes")
        fb_to_upright(from_rgb565(data, m["fb"])).save(a.decode[1])
        print(f"wrote {a.decode[1]}")
        return

    if not a.image:
        ap.error("give a picture (or --decode)")
    if not m["verified"] and not a.experimental:
        sys.exit(f"The {a.model} boot-logo format is not verified yet (only the DP200 is).\n"
                 "Run with --experimental to try anyway: the stick saves the old logo\n"
                 "(bootlogo_original.bin) so it can be put back.")
    if not (a.key or a.key_file):
        ap.error("need --key-file crypto_key.dat (from your printer's /app) or --key")

    exe = find_openssl()
    key = a.key or key_from_file(exe, a.key_file, m["cipher"])

    raw = None
    if a.image.lower().endswith(".bin"):
        raw = open(a.image, "rb").read()[:fb_bytes]        # a logo .bin / mtd3 dump
        if len(raw) != fb_bytes:
            sys.exit(f"{a.image}: a raw logo must be at least {fb_bytes} bytes")
        upright = fb_to_upright(from_rgb565(raw, m["fb"]))
    else:
        upright = fit_image(a.image, m["upright"], a.fit, parse_color(a.bg))
        raw = to_rgb565(upright_to_fb(upright), not a.no_dither)
        upright = fb_to_upright(from_rgb565(raw, m["fb"]))

    bar = a.bar_color
    if bar == "auto":
        lum = sum(ImageOps.grayscale(upright).tobytes()) / (upright.width * upright.height)
        bar = "1" if lum >= 128 else "0"

    md5 = hashlib.md5(raw).hexdigest()
    script = install_script(len(raw), md5, bar)
    she = encrypt(exe, m["cipher"], key, make_tar_bz2([(SCRIPT_NAME, script, 0o755),
                                                       (LOGO_NAME, raw, 0o644)]))

    folder = os.path.join(a.out, m["folder"])
    os.makedirs(folder, exist_ok=True)
    she_path = os.path.join(folder, SCRIPT_NAME + "e")
    open(she_path, "wb").write(she)
    open(os.path.join(a.out, "bootlogo_new.bin"), "wb").write(raw)
    upright.save(os.path.join(a.out, "bootlogo_preview.png"))

    # self-check: decrypt like the printer does and compare
    with tarfile.open(fileobj=io.BytesIO(bz2.decompress(decrypt(exe, m["cipher"], key, she)))) as t:
        ok = (t.extractfile(LOGO_NAME).read() == raw and
              t.extractfile(SCRIPT_NAME).read() == script)
    if not ok:
        sys.exit("self-check FAILED: the .she does not decrypt to what was packed")

    print(f"wrote {she_path}  (verified)")
    print(f"preview (as the screen shows it): {os.path.join(a.out, 'bootlogo_preview.png')}")
    print(f"progress bar colour: {bar}   logo md5: {md5}")
    print(f"Copy the {m['folder']} folder to the root of a FAT32 USB stick, plug it into\n"
          "the printer and touch the screen when asked. The stick keeps the old logo\n"
          "as bootlogo_original.bin.")


if __name__ == "__main__":
    main()
