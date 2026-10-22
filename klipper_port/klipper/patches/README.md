# Klipper fork patches (branch `sindoh-dp200`)

Made by `../make_fork.sh` on top of upstream Klipper **9cb9975**
(2026-10-13, "mcu: Report a normal CommandError if CommandWrapper fails"):

1. `upc: Add Marvell 88PA6170 UPC port (Sindoh DP200)`: `src/upc`,
   `src/Kconfig` (MACH_UPC), `config/dp200_fm.config`, `config/dp200_io.config`
2. `upc: Add upc_stats and upc_clockcheck host modules`: `klippy/extras/`
3. `config: Add Sindoh 3DWOX DP200 configuration`: `config/sindoh-dp200/`
4. `sindoh-dp200: Add the cartridge module, update the DP200 configuration`:
   `klippy/extras/dp200_cartridge.py`, plus the configs as of 2026-10-22
   (made directly in the fork clone, then exported with `git format-patch`)
5. `sindoh-dp200: Re-prime in PRINT_START, add PRIME_LINE, exclude_object
   and arcs` (2026-10-22)

Both MCU images build from the branch (FM 11736 B, IO 11800 B with
arm-none-eabi-gcc 14.2).

To put them on GitHub, fork Klipper3d/klipper, then:

```
git clone https://github.com/<you>/klipper && cd klipper
git checkout -b sindoh-dp200 9cb9975
git am /path/to/klipper_port/klipper/patches/*.patch
git push -u origin sindoh-dp200
```

On a newer upstream the patches normally apply as well. Only the
`src/Kconfig` hunk can conflict; if it does, re-run `make_fork.sh` against
the new checkout.
