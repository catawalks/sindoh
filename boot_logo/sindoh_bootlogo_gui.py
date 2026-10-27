#!/usr/bin/env python3
"""Sindoh Boot Logo Maker - window version of sindoh_bootlogo.py.

Pick a picture, place it on the printer's screen (drag to move, mouse wheel
to zoom, rotate, flip), choose the printer model and the progress bar colour,
then save the USB update files. Needs Python 3.8+ with Tk and Pillow, or the
packaged SindohBootLogo.exe (no Python needed).
"""
import hashlib
import math
import os
import sys
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageOps, ImageTk

import bootlogo_core as core

BOX = 500                    # preview: the longer screen side, in pixels
PAD = 12


class App:
    def __init__(self, root):
        self.root = root
        root.title("Sindoh Boot Logo Maker")
        root.minsize(760, 600)
        self.src = None              # RGBA source picture
        self.src_name = ""
        self.raw_exact = False       # loaded from a raw .bin: keep it exact
        self.key = None
        self.bg = (0, 0, 0)
        self.dx = self.dy = 0.0      # picture centre offset, screen pixels
        self.flip = False
        self.drag = None
        self.busy = False

        self.model = tk.StringVar(value="dp200")
        self.scale = tk.DoubleVar(value=100.0)
        self.angle = tk.DoubleVar(value=0.0)
        self.invert = tk.BooleanVar(value=False)
        self.dither = tk.BooleanVar(value=True)
        self.show565 = tk.BooleanVar(value=True)
        self.bar = tk.StringVar(value="auto")
        self.dry = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Open a picture to start.")
        self.key_status = tk.StringVar(value="built-in key")
        self.bar_auto_text = tk.StringVar(value="Automatic")

        self._build_ui()
        self.redraw()

    # ------------------------------------------------------------- layout --
    def _build_ui(self):
        r = self.root
        left = ttk.Frame(r, padding=PAD)
        left.grid(row=0, column=0, sticky="ns")
        right = ttk.Frame(r, padding=(0, PAD, PAD, PAD))
        right.grid(row=0, column=1, sticky="nsew")
        r.columnconfigure(1, weight=1)
        r.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(left, bg="#202020", highlightthickness=1,
                                highlightbackground="#888", cursor="fleur")
        self.canvas.grid(row=0, column=0)
        self.screen_lbl = ttk.Label(left, justify="center")
        self.screen_lbl.grid(row=1, column=0, pady=(6, 0))
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))
        self.canvas.bind("<MouseWheel>", self.on_wheel)              # Windows, macOS
        self.canvas.bind("<Button-4>", lambda e: self.zoom(1.05))    # X11
        self.canvas.bind("<Button-5>", lambda e: self.zoom(1 / 1.05))

        # 1. picture
        f = ttk.LabelFrame(right, text="1. Picture", padding=8)
        f.grid(row=0, column=0, sticky="ew")
        ttk.Button(f, text="Open picture...", command=self.open_picture).grid(row=0, column=0)
        ttk.Button(f, text="Open raw logo (.bin)...", command=self.open_raw).grid(row=0, column=1, padx=6)
        self.name_lbl = ttk.Label(f, text="(none)", foreground="#555")
        self.name_lbl.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # 2. placement
        f = ttk.LabelFrame(right, text="2. Position", padding=8)
        f.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Size %").grid(row=0, column=0, sticky="w")
        tk.Scale(f, variable=self.scale, from_=1, to=400, resolution=0.5, orient="horizontal",
                 command=lambda v: self.changed()).grid(row=0, column=1, columnspan=4, sticky="ew")
        ttk.Label(f, text="Rotate").grid(row=1, column=0, sticky="w")
        tk.Scale(f, variable=self.angle, from_=-180, to=180, resolution=0.5, orient="horizontal",
                 command=lambda v: self.changed()).grid(row=1, column=1, columnspan=4, sticky="ew")
        b = ttk.Frame(f)
        b.grid(row=2, column=0, columnspan=5, sticky="w", pady=(4, 0))
        for i, (t, c) in enumerate((("Rotate 90 left", lambda: self.turn(90)),
                                    ("Rotate 90 right", lambda: self.turn(-90)),
                                    ("Mirror", self.mirror))):
            ttk.Button(b, text=t, command=c).grid(row=0, column=i, padx=(0, 4))
        b = ttk.Frame(f)
        b.grid(row=3, column=0, columnspan=5, sticky="w", pady=(4, 0))
        for i, (t, c) in enumerate((("Fit whole picture", lambda: self.fit(False)),
                                    ("Fill screen", lambda: self.fit(True)),
                                    ("Center", self.center),
                                    ("Reset", self.reset))):
            ttk.Button(b, text=t, command=c).grid(row=0, column=i, padx=(0, 4))

        # 3. colours
        f = ttk.LabelFrame(right, text="3. Colours", padding=8)
        f.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(f, text="Background colour...", command=self.pick_bg).grid(row=0, column=0, sticky="w")
        self.bg_swatch = tk.Label(f, width=4, bg="#000000", relief="solid", bd=1)
        self.bg_swatch.grid(row=0, column=1, padx=6)
        ttk.Checkbutton(f, text="Invert colours", variable=self.invert,
                        command=self.changed).grid(row=0, column=2, padx=(12, 0))
        ttk.Checkbutton(f, text="Dither (smoother photos and gradients)",
                        variable=self.dither).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Checkbutton(f, text="Preview in the screen's own colours", variable=self.show565,
                        command=self.redraw).grid(row=2, column=0, columnspan=3, sticky="w")

        # 4. printer
        f = ttk.LabelFrame(right, text="4. Printer", padding=8)
        f.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(f, text="Model").grid(row=0, column=0, sticky="w")
        names = [m["name"] for m in core.MODELS.values()]
        self.model_box = ttk.Combobox(f, values=names, state="readonly", width=36)
        self.model_box.current(0)
        self.model_box.grid(row=0, column=1, columnspan=3, sticky="w", padx=6)
        self.model_box.bind("<<ComboboxSelected>>", self.on_model)
        self.fit_canvas()
        ttk.Label(f, text="Boot progress bar").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Radiobutton(f, textvariable=self.bar_auto_text, value="auto",
                        variable=self.bar).grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        ttk.Radiobutton(f, text="0 (dark logos)", value="0",
                        variable=self.bar).grid(row=2, column=1, sticky="w", padx=6)
        ttk.Radiobutton(f, text="1 (light logos)", value="1",
                        variable=self.bar).grid(row=2, column=2, sticky="w")
        ttk.Radiobutton(f, text="Leave as is", value="keep",
                        variable=self.bar).grid(row=2, column=3, sticky="w", padx=6)
        ttk.Label(f, text="Key (built in)").grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Button(f, text="Key file...", command=self.load_key).grid(row=3, column=1, sticky="w", padx=6, pady=(6, 0))
        ttk.Button(f, text="Type key...", command=self.type_key).grid(row=3, column=2, sticky="w", pady=(6, 0))
        ttk.Label(f, textvariable=self.key_status, foreground="#555").grid(row=4, column=1, columnspan=3, sticky="w", padx=6)

        # 5. save
        f = ttk.LabelFrame(right, text="5. Save", padding=8)
        f.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.save_btn = ttk.Button(f, text="Save to USB stick...", command=self.save_usb)
        self.save_btn.grid(row=0, column=0, sticky="w")
        ttk.Button(f, text="Save preview PNG...", command=self.save_png).grid(row=0, column=1, padx=6)
        ttk.Checkbutton(f, text="Dry run (printer only checks, writes nothing)",
                        variable=self.dry).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        ttk.Label(right, textvariable=self.status, wraplength=380, justify="left").grid(
            row=5, column=0, sticky="ew", pady=(10, 0))
        right.columnconfigure(0, weight=1)

    # ------------------------------------------------------------ helpers --
    def model_key(self):
        return list(core.MODELS)[self.model_box.current()]

    def size(self):
        return core.MODELS[self.model_key()]["upright"]

    def view(self):
        """Preview scale: the screen's longer side becomes BOX pixels."""
        return BOX / max(self.size())

    def fit_canvas(self):
        W, H = self.size()
        k = self.view()
        self.canvas.config(width=round(W * k), height=round(H * k))
        self.screen_lbl.config(text=f"Printer screen, upright ({W} x {H}).\n"
                                    "Drag to move, mouse wheel to zoom.")

    def compose(self, view):
        """The upright screen image. view=True: small and fast for the canvas."""
        W, H = self.size()
        k = self.view() if view else 1.0
        out = Image.new("RGB", (round(W * k), round(H * k)), self.bg)
        if self.src is None:
            return out
        im = self.src
        if self.flip:
            im = ImageOps.mirror(im)
        if self.invert.get():
            r, g, b, a = im.split()
            im = Image.merge("RGBA", ImageOps.invert(Image.merge("RGB", (r, g, b))).split() + (a,))
        s = self.scale.get() / 100 * k
        w, h = max(1, round(im.width * s)), max(1, round(im.height * s))
        if self.raw_exact and not view and self.is_identity() and im.size == (W, H):
            out.paste(im.convert("RGB"))
            return out
        im = im.resize((w, h), Image.Resampling.BILINEAR if view else Image.Resampling.LANCZOS)
        if self.angle.get() % 360:
            im = im.rotate(self.angle.get(), resample=Image.Resampling.BICUBIC, expand=True)
        x = round(out.width / 2 + self.dx * k - im.width / 2)
        y = round(out.height / 2 + self.dy * k - im.height / 2)
        out.paste(im, (x, y), im)
        return out

    def is_identity(self):
        return (self.scale.get() == 100 and self.angle.get() % 360 == 0 and not self.flip
                and self.dx == 0 and self.dy == 0)

    def changed(self):
        self.redraw()

    def redraw(self):
        im = self.compose(True)
        if self.show565.get():
            im = core.preview(im, core.MODELS[self.model_key()])
        self.bar_auto_text.set(f"Automatic ({core.auto_bar_color(im)})")
        self.tkimg = ImageTk.PhotoImage(im)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.tkimg, anchor="nw")

    # ------------------------------------------------------------ actions --
    def open_picture(self):
        path = filedialog.askopenfilename(title="Choose a picture", filetypes=[
            ("Pictures", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff"), ("All files", "*.*")])
        if not path:
            return
        try:
            im = ImageOps.exif_transpose(Image.open(path)).convert("RGBA")
        except Exception as e:
            messagebox.showerror("Can't open", str(e))
            return
        self.src, self.src_name, self.raw_exact = im, os.path.basename(path), False
        self.name_lbl.config(text=f"{self.src_name}  ({im.width} x {im.height})")
        self.flip = False
        self.angle.set(0)
        self.fit(False)
        self.status.set("Place the picture, then save it to a USB stick.")

    def open_raw(self):
        path = filedialog.askopenfilename(title="Choose a raw logo (e.g. bootlogo_original.bin)",
                                          filetypes=[("Raw logo", "*.bin"), ("All files", "*.*")])
        if not path:
            return
        m = core.MODELS[self.model_key()]
        n = m["bytes"]
        data = open(path, "rb").read()
        if m["target"] == "mtd":
            data = data[:n]                  # a partition dump has padding
        if len(data) != n:
            messagebox.showerror("Not a logo", f"A raw {m['name']} logo has {n} bytes, this file "
                                 f"{len(data)}.\nCheck the printer model (4. Printer) first.")
            return
        self.src = core.from_raw(data, m).convert("RGBA")
        self.src_name, self.raw_exact = os.path.basename(path), True
        self.name_lbl.config(text=f"{self.src_name}  (raw logo, kept exact)")
        self.reset()
        self.dither.set(False)
        self.status.set("Raw logo loaded. Saving it unchanged restores it exactly.")

    def reset(self):
        self.flip = False
        self.angle.set(0)
        self.scale.set(100)
        self.dx = self.dy = 0.0
        self.redraw()

    def center(self):
        self.dx = self.dy = 0.0
        self.redraw()

    def turn(self, deg):
        a = (self.angle.get() + deg + 180) % 360 - 180
        self.angle.set(a)
        self.redraw()

    def mirror(self):
        self.flip = not self.flip
        self.redraw()

    def fit(self, fill):
        if self.src is None:
            return
        W, H = self.size()
        t = math.radians(self.angle.get())
        bw = abs(self.src.width * math.cos(t)) + abs(self.src.height * math.sin(t))
        bh = abs(self.src.width * math.sin(t)) + abs(self.src.height * math.cos(t))
        s = (max if fill else min)(W / bw, H / bh)
        self.scale.set(max(1, min(400, round(s * 100, 1))))
        self.dx = self.dy = 0.0
        self.redraw()

    def zoom(self, f):
        self.scale.set(max(1, min(400, self.scale.get() * f)))
        self.redraw()

    def on_wheel(self, e):
        self.zoom(1.05 if e.delta > 0 else 1 / 1.05)

    def on_press(self, e):
        self.drag = (e.x, e.y)

    def on_drag(self, e):
        if self.drag:
            self.dx += (e.x - self.drag[0]) / self.view()
            self.dy += (e.y - self.drag[1]) / self.view()
            self.drag = (e.x, e.y)
            self.redraw()

    def pick_bg(self):
        c = colorchooser.askcolor(color="#%02x%02x%02x" % self.bg, title="Background colour")
        if c and c[0]:
            self.bg = tuple(int(v) for v in c[0])
            self.bg_swatch.config(bg=c[1])
            self.redraw()

    def on_model(self, _e=None):
        m = core.MODELS[self.model_key()]
        if not m["verified"]:
            messagebox.showwarning("Not verified", (
                f"{m['name']}: the boot logo format of this model has not been checked yet.\n\n"
                "The file is packed the way this model's updates are described, and the "
                "printer only writes it if it finds a 'boot-logo' partition big enough. "
                "It saves the old logo (bootlogo_original.bin) on the stick first, so it can "
                "be put back. Use the Dry run option first."))
        self.key = None
        self.key_status.set("built-in key")
        old = (int(self.canvas.cget("width")), int(self.canvas.cget("height")))
        self.fit_canvas()
        new = (int(self.canvas.cget("width")), int(self.canvas.cget("height")))
        if self.src is not None and old != new and not self.raw_exact:
            self.fit(False)                  # other screen shape: fit the picture again
        else:
            self.redraw()

    def load_key(self):
        path = filedialog.askopenfilename(title="crypto_key.dat from your printer's /app folder",
                                          filetypes=[("crypto_key.dat", "*.dat"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.key = core.key_from_file(path, core.MODELS[self.model_key()]["cipher"])
            self.key_status.set(f"key read from {os.path.basename(path)}")
        except Exception as e:
            self.key = None
            self.key_status.set("could not read that file")
            messagebox.showerror("Key", str(e))

    def type_key(self):
        k = simpledialog.askstring("Encryption key", "Update password for this model:")
        if k:
            self.key = k.strip()
            self.key_status.set("key typed in")

    def save_png(self):
        if self.src is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")],
                                            initialfile="bootlogo_preview.png")
        if path:
            core.preview(self.compose(False), core.MODELS[self.model_key()]).save(path)
            self.status.set(f"Saved {path}")

    def save_usb(self):
        if self.busy:
            return
        if self.src is None:
            messagebox.showinfo("No picture", "Open a picture first.")
            return
        model = self.model_key()
        m = core.MODELS[model]
        key = self.key or m["key"]
        if not m["verified"] and not messagebox.askyesno(
                "Not verified", f"{m['name']} is not verified. Make the file anyway?"):
            return
        out = filedialog.askdirectory(title="Choose the USB stick (or a folder to copy to it later)")
        if not out:
            return
        if os.path.exists(os.path.join(out, m["folder"], "update.she")):
            if not messagebox.askyesno("Firmware update on this stick", (
                    "This stick also holds a Sindoh firmware update (update.she). It runs after "
                    "the logo and writes the stock logo back. Continue anyway?")):
                return
        upright = self.compose(False)
        bar = self.bar.get()
        dither, dry = self.dither.get(), self.dry.get()
        self.busy = True
        self.save_btn.config(state="disabled")
        self.status.set("Converting and encrypting...")
        self.root.config(cursor="watch")

        def work():
            try:
                raw = core.to_raw(upright, m, dither)
                b = core.auto_bar_color(core.from_raw(raw, m)) if bar == "auto" else bar
                path = core.build_usb(raw, model, key, b, out, dry)
                msg = (f"Saved {path} (verified), progress bar {b}"
                       f"{', DRY RUN' if dry else ''}.\nlogo md5 {hashlib.md5(raw).hexdigest()}\n\n"
                       "Plug the stick into the printer and touch the screen when asked. "
                       "The stick keeps the old logo as bootlogo_original.bin.")
                self.root.after(0, self.done, msg, None)
            except Exception as e:
                self.root.after(0, self.done, None, e)

        threading.Thread(target=work, daemon=True).start()

    def done(self, msg, err):
        self.busy = False
        self.save_btn.config(state="normal")
        self.root.config(cursor="")
        if err:
            self.status.set(f"Failed: {err}")
            messagebox.showerror("Failed", str(err))
        else:
            self.status.set(msg)


def main():
    if sys.platform == "win32":
        try:                         # sharp text on scaled (high-DPI) screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
