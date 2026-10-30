#!/bin/sh
# Offline Klipper config check (2026-10-29): runs klippy in batch mode in WSL
# against klipper/config/*.cfg and the UPC firmware's data dictionaries
# (prebuilt/klipper_fm.dict, klipper_io.dict). No printer needed.
#
# It catches config errors: unknown options, bad pins, macro template syntax,
# includes, kinematics and bed-mesh setup. It cannot get past homing, because
# upc_clockcheck waits for real MCU clocks. A first G28 is refused by the
# BED_CLEAR guard, as designed.
#
# Klippy needs cffi, greenlet, jinja2, markupsafe, pyserial for WSL's Python.
# WSL has no pip, so fetch Linux wheels with Windows pip into DEPS:
#   py -3.15 -m pip install --target DEPS --platform manylinux2014_x86_64 \
#     --platform manylinux_2_17_x86_64 --python-version 3.13 --implementation cp \
#     --only-binary=:all: cffi greenlet jinja2 markupsafe pycparser
#   py -3.15 -m pip install --target DEPS --no-deps pyserial
#
# usage (Git Bash): tools/klippy_batch_check.sh DEPS_DIR [GCODE_FILE]
#   DEPS_DIR as a WSL path (/mnt/c/...)
set -e
deps=${1:?usage: $0 DEPS_DIR [GCODE_FILE]}
here=$(cd "$(dirname "$0")/.." && pwd -W 2>/dev/null || pwd)
w() { echo "/mnt/$(echo "$1" | sed 's#^\([A-Za-z]\):#\L\1#; s#\\#/#g')"; }
port=$(w "$here")
gcode=${2:+$(w "$(cd "$(dirname "$2")" && pwd -W)/$(basename "$2")")}
wsl -e sh -c "
set -e
rm -rf /tmp/kb && mkdir -p /tmp/kb/cfg /tmp/kb/home/printer_data/config /tmp/kb/home/printer_data/gcodes
cp -r /mnt/c/Users/temp.DESKTOP-L41KPL5/klipper/klippy /tmp/kb/
cp $port/klipper/config/*.cfg /tmp/kb/cfg/
cp $port/prebuilt/klipper_fm.dict $port/prebuilt/klipper_io.dict /tmp/kb/
if [ -n '$gcode' ]; then cp '$gcode' /tmp/kb/t.gcode; else printf 'M105\nBED_CLEAR\nLAMP_TOGGLE\nM104 S0\nM140 S0\n' > /tmp/kb/t.gcode; fi
cd /tmp/kb
HOME=/tmp/kb/home PYTHONPATH=$deps timeout 300 python3 klippy/klippy.py cfg/printer.cfg \
    -i t.gcode -o out.serial -v -d klipper_fm.dict -d io=klipper_io.dict -l log.txt || true
if grep -q -e 'Error loading' -e 'Config error' -e 'Unhandled exception' -e 'Option .* is not valid' log.txt; then
    grep -B2 -A8 -e 'Error loading' -e 'Config error' -e 'Unhandled exception' -e 'is not valid' log.txt | head -60
    echo 'klippy_batch_check: CONFIG ERRORS'; exit 1
fi
grep -q 'Running full garbage collection' log.txt && echo 'klippy_batch_check: config loads, all sections and macros OK'
"
