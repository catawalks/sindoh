# Model IDs in every Sindoh motion program

Read 2026-11-24 from the motion program of each firmware line we have
(disassembled on the PC, never run): the DP200's `RODIN_200730_2` (and
its 2017 build), the 3DWOX 1's `RODUP_`, the 1X's `ROD1X_190917_1` and the
owner's newer 1X copy, the 2X's `PRIME_210419_2` and the 7X's
`RODNH_210602_1`. The 30X update cannot be decrypted (key unknown). The
DP200 family in detail, and what its program changes on a DP201:
[dp200_family_models.md](dp200_family_models.md).

## How it works

Each printer stores its model ID ("TLI") in the settings database
(`sqlite3 /app/nvram/karas.db 'select MachineTLI from INST_MACHINE'`).
At start-up `engine_getMachineModel` compares it with a list and keeps a
32-bit model code; the rest of the program tests bits of that code
(`engine_ifRodinE`, `engine_ifRodin1X`, ...). The high bits are the
family, the low bits the variant. An ID that is not in the list gets the
build's default.

Suffixes in the IDs: the market (K Korea, A Americas, J Japan, C/CM China,
none Europe), **Q** the open-filament model, **H** a further variant (the
program gives H and non-H the same code: the difference, if any, is
elsewhere).

## The families

| Code bit | Sindoh's name | Model | Test function |
|---|---|---|---|
| `0x01000000` | Rodin P | DP200, DP102 | (none: the default family on the DP200 line) |
| `0x02000000` | Rodin E | DP201, DP202 | `engine_ifRodinE` |
| `0x04000000` | Yangpan | ? | `engine_ifRodinYangpan` |
| `0x08000000` | Rodin U | 3DWOX 1 | `engine_ifRodinU` |
| `0x10000000` | Rodin PP ("Prime") | 2X | `engine_ifRodinPP` |
| `0x20000000` | Rodin H / HH | 7X | `engine_ifRodinH`, `engine_ifRodinHH` |
| `0x40000000` | Rodin 1X / HL | 1X on the 1X line; **5X** on the 7X line | `engine_ifRodin1X`, `engine_ifRodinHL` |
| `0x80000000` | "Rodin L" | `3DP203KQ` only | |

Variant bits (low half): `0x0100` Sindoh, `0x0200` China (ESUN),
`0x0400` Stanley, `0x0800` Leon 3D (Spain), `0x1000` Japan (3DWOX 1),
`0x2000` OEM IDs (`B1015..`, `RIZE`).

## The lists, by firmware line

**DP200 line** (`RODIN_200730_2`, also the DP201's):

| Code | IDs |
|---|---|
| `0x01000100` | `3DP200` `3DP102` `3DP200K` `3DP200A` `3DP200CM` `3DP200J` `3DP200Q` `3DP102Q` `3DP200KQ` `3DP200AQ` `3DP200CMQ` `3DP200JQ` `3DP200H` `3DP200CMH` `3DP200JH` `3DP200KH` |
| `0x01000200` | `3DP200C` `3DP200CQ` |
| `0x01000400` | `ST3DP1` `ST3DP1Q` (Stanley Model 1) |
| `0x01000800` | `LEON3D` `LEON3DQ` |
| `0x02000100` | `3DP201` `3DP201K` `3DP201A` `3DP201CM` `3DP202` `3DP201J` `3DP201Q` `3DP201KQ` `3DP201AQ` `3DP201CMQ` `3DP202Q` `3DP201JQ` `ORAL3DQ`; IDs starting `RDPL` or `3DPL`; **any unknown ID** |
| `0x02000200` | `3DP201C` `3DP201CQ` |
| `0x80000100` | `3DP203KQ` |

The 2017 build had a shorter list (no Q, H or regional DP201 IDs, no
Stanley Q, no Leon).

**3DWOX 1 line** (`RODUP_`; its own build, `RODIN_SUB=U`):

| Code | IDs |
|---|---|
| `0x08000100` | `3D1Q` `3D1AQ` `3D1CQ` `3D1KQ` `3DP103` `RDPU0000-SQ` `3D1H` `3D1AH` `3D1CH` `3D1KH` `3DP103H` `RDPU0000-H` |
| `0x40001000` | `3D1JQ` `3D1JH` (Japan) |

**1X line** (`ROD1X_`; the owner's 1X reads `3D1XAH`):

| Code | IDs |
|---|---|
| `0x01000100`, `0x01000200`, `0x01000400`, `0x02000100`, `0x02000200` | the DP200/DP201 IDs as above (shorter list) and **`ST3000`** (Stanley, variant `0x0400`) |
| `0x20000100` | `RDPH` |
| `0x10000100` | `RDPR` `3D2X` `3D2XKQ` `3DP303` `3D2XA` `3D2XJ` `RDPP0000-SQ` `3D2XQ` `3D2XAQ` `3D2XJQ` `3D2XCQ` `3D2XKH` `3DP303H` `3D2XH` `3D2XAH` `3D2XCH` `3D2XJH`; **any unknown ID** |
| `0x10000800` | `LEON3D2XQ` |
| `0x40000100` | `3D1XQ` `3D1XAQ` `3D1XKQ` `3D1XCQ` `3DP302` `RD1X0000-SQ` `3D1XH` `3D1XAH` `3D1XKH` `3DP302H` `RD1X0000-H` |

(The H IDs, the owner's `3D1XAH` among them, are in the owner's 2020 copy
only, not in the 2019 update: on that update the owner's 1X would count
as a 2X.)

**2X line** (`PRIME_`): as the 1X line without the 1X IDs, plus
`RDPP0000-H` and **`0x10002000`: `B101500` `B101500H` `RIZE2XCKH`** (OEM
2X builds). Unknown IDs count as a 2X.

**7X line** (`RODNH_`, "Rodin New H"):

| Code | IDs |
|---|---|
| `0x20000100` | `RODIN-HH` `3D7X` `3D7XPA`; **any unknown ID** |
| `0x40000100` | `RODIN-HL` **`3D5X`** |
| `0x20002000` | `B101501` (OEM) |

So the 7X firmware also runs a **3DWOX 5X** ("Rodin HL"), a model we had
no record of.

## Other things these programs tell apart

- **3DWOX 1, two driver boards:** at start-up it reads a board-select
  GPIO (`gp_pcb_select`). Read 1: "New Board (Trinamic)": TMC2224
  drivers, and the program sets all five motor current offsets to 99.
  Read 0: the older board (A4982 drivers, as the DP200), and bit
  `0x00800000` is added to the model code ("Machine Revision"). So a
  3DWOX 1 database with +99 on every axis (Fredrik Gustafsson's unit)
  marks a TMC2224 board, not a calibration. The DP200's 2020 program has
  no such check.
- **1X and 2X share one program** (`ROD1X_` lists the 2X IDs too), with
  `engine_ifRodin1X` and `engine_ifRodinPP` choosing the paths; the 2X
  line's program has no 1X IDs.
- **7X and 5X share one program** (`engine_ifRodinHH` / `engine_ifRodinHL`).

## For the Klipper port

- The model ID picks the config: the DP200 installer does this already
  (DP200 family / DP201 family; sindoh-klipper
  `install/usb/unmistakable_klipper_install.sh`). The 1X installer can
  check for the `0x40000100` IDs above.
- The 3DWOX 1 config should tell its two boards apart (offsets of 99 on
  every axis, or the board-select pin) before setting motor currents.
