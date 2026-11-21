# Sindoh 3DWOX printers: hardware research

Notes on how Sindoh's 3DWOX 3D printers work inside: the mainboards, the
firmware update mechanism, and what differs between models. It is the
reference shelf for the projects below.

Looking for Klipper? Go to
**[catawalks/sindoh-klipper](https://github.com/catawalks/sindoh-klipper)**.

## What is here

| Path | What |
|---|---|
| [docs/other_models.md](docs/other_models.md) | Every model compared (DP200/DP201, 3DWOX 1, 2X, 1X, 7X, 30X): chip, kernel, storage, USB update folder and key |
| [docs/1x.md](docs/1x.md) | The 3DWOX 1X, read from a real printer: eMMC layout, motion hardware, TMC2224 drivers, GPIOs |
| [docs/3dwox1.md](docs/3dwox1.md) | The 3DWOX 1: Fredrik Gustafsson's tests and Sebastian Schmidt's dumps |
| [docs/prime_sd.md](docs/prime_sd.md) | The 2X ("Prime"): its mainboard and Sindoh's factory recovery SD card |
| [docs/nand_partition_layout.md](docs/nand_partition_layout.md) | NAND partitions of the DP200 family |
| [docs/tli_list.txt](docs/tli_list.txt) | Model ID codes ("TLI") seen in Sindoh firmware |
| [3dwox1_2021/](3dwox1_2021/) | Sebastian Schmidt's original 2021 notes and dumps from a 3DWOX 1, which this repository was forked from: how the printer's software fits together and how to get a root shell |
| [Model_1_Converter/](Model_1_Converter/) | USB stick files that turn a Stanley Model 1 into a DP200Q (open filament, latest firmware) and back |

Each document says where its facts come from: which printer, who measured
them, and what is only our reading.

## Related repositories

| Repository | What |
|---|---|
| [sindoh-klipper](https://github.com/catawalks/sindoh-klipper) | Klipper, Moonraker and Mainsail on the printer's own mainboard, installed from a USB stick |
| [klipper](https://github.com/catawalks/klipper/tree/sindoh-dp200) (branch `sindoh-dp200`) | The Klipper code for the printer's real-time cores |
| [sindoh-kernel](https://github.com/catawalks/sindoh-kernel) | Mainline Linux for the Marvell 88PA6170 |
| [sindoh-model-survey](https://github.com/catawalks/sindoh-model-survey) | A read-only USB stick that saves a hardware report from any model. **Own a model other than the DP200? Running it helps.** |
| [sindoh-boot-logo](https://github.com/catawalks/sindoh-boot-logo) | Put your own picture on the boot screen |

## A warning that applies to every model

Sindoh's update scripts run as root from a USB stick, which is what makes
all of this possible, and also what can brick a printer. Never run the
stock `/snapshot_version.sh` by hand (it rewrites boot settings), and read
[3dwox1_2021/README.md](3dwox1_2021/README.md) before logging in to a
stock printer.

## License

Everything here by catawalks and contributors is free and open source
under the **GNU General Public License, version 3 or (at your option) any
later version** ([LICENSE](LICENSE)).

Not covered: `3dwox1_2021/`, the notes and dumps by Sebastian Schmidt
([yath/sindoh](https://github.com/yath/sindoh), 2021). His repository has
no license, so they stay his. Nothing from Sindoh or Marvell (firmware,
images, apps) is included.
