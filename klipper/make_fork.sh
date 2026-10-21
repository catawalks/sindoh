#!/bin/sh
# Build a Klipper branch "sindoh-dp200" with the DP200 port committed on top of
# upstream, and export it as patches (git format-patch) - for a GitHub fork.
# Run inside the Debian root (git, python3, arm-none-eabi-gcc):
#
#   sh make_fork.sh [KLIPPER_SRC] [WORK_DIR] [PATCH_OUT]
#
#   KLIPPER_SRC  upstream Klipper checkout to start from (default /home/klipper/klipper;
#                it is only read - the branch is made in a fresh clone)
#   WORK_DIR     default /usr/src/dp200/klipper-fork
#   PATCH_OUT    default <this repo>/klipper/patches
#
# Apply to a fork:  git checkout -b sindoh-dp200 <base>  &&  git am patches/*.patch
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=${1:-/home/klipper/klipper}
F=${2:-/usr/src/dp200/klipper-fork}
OUT=${3:-$HERE/patches}
G="git -c user.name=catawalks -c user.email=catawalks@gmail.com"
TRAILER="Signed-off-by: catawalks <catawalks@gmail.com>
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"

rm -rf "$F"
# a copy owned by us (the source belongs to the klipper user, and git refuses
# to work in a tree owned by someone else); then drop local changes/builds
cp -a "$SRC" "$F"
chown -R "$(id -u):$(id -g)" "$F"
cd "$F"
$G checkout -q -- . && $G clean -q -fdx
BASE=$($G rev-parse --short HEAD)
$G checkout -q -b sindoh-dp200

# 1. MCU port
sh "$HERE/install_port.sh" "$F" >/dev/null
$G add src/Kconfig src/upc config/dp200_fm.config config/dp200_io.config
$G commit -q -m "upc: Add Marvell 88PA6170 UPC port (Sindoh DP200)

The Sindoh 3DWOX DP200 runs its motion and I/O on the two UPC
coprocessors (ARMv5) of its Marvell 88PA6170 SoC. This adds a Klipper
MCU port for them (MACH_UPC): the FM core drives the steppers, the IO
core the heaters, fans and ADC. Host communication goes through
shared memory, bridged to a pseudo-tty by upctool on the Linux side.

config/dp200_fm.config and config/dp200_io.config build the two images.

$TRAILER"

# 2. host extra
cp "$HERE/extras/upc_stats.py" "$HERE/extras/upc_clockcheck.py" klippy/extras/
$G add klippy/extras/upc_stats.py klippy/extras/upc_clockcheck.py
$G commit -q -m "upc: Add upc_stats and upc_clockcheck host modules

upc_stats: UPC_STEP_STATS reports the step pulse and step-engine busy
counters of the DP200 FM core, used to diagnose step-rate limits.

upc_clockcheck: repeats the MCU frequency check 30 s after start-up and
withdraws the start-up warning when the settled clock estimate agrees
(the first clock samples of the UPC cores arrive through a busy
shared-memory bridge and read 1-2 % low).

$TRAILER"

# 3. printer configs
mkdir -p config/sindoh-dp200
cp "$HERE/config/printer.cfg" "$HERE/config/dp200_printer.cfg" "$HERE/config/dp200_macros.cfg" \
   config/sindoh-dp200/
cat > config/sindoh-dp200/README.md <<'EOF'
# Sindoh 3DWOX DP200

Copy all three files to `printer_data/config/`:

- `printer.cfg` - the per-printer file: Z endstop, probe offsets, PID values
  and the SAVE_CONFIG block live here.
- `dp200_printer.cfg` - the hardware (UPC MCUs, steppers, heaters, sensors).
- `dp200_macros.cfg` - filament load/unload, nozzle cleaning, the levelling
  probe, bed mesh, lamp.

The MCU firmware and the host-side bridge (upctool) come from the DP200
port project; see https://github.com/catawalks/sindoh
EOF
$G add config/sindoh-dp200
$G commit -q -m "config: Add Sindoh 3DWOX DP200 configuration

$TRAILER"

# test build of both images from the branch
for core in fm io; do
    cp config/dp200_$core.config .config
    make olddefconfig >/dev/null
    make -j2 >/tmp/fork_build_$core.log 2>&1 || { echo "BUILD FAILED ($core), see /tmp/fork_build_$core.log"; exit 1; }
    echo "built $core: $(stat -c %s out/klipper.bin) bytes"
    cp out/klipper.bin /tmp/fork_$core.bin
    make clean >/dev/null
done
rm -f .config .config.old

rm -rf "$OUT"; mkdir -p "$OUT"
$G format-patch -q -o "$OUT" "$BASE"..HEAD
echo "base $BASE ($($G log -1 --format=%cs $BASE)), branch sindoh-dp200:"
$G log --oneline "$BASE"..HEAD
ls "$OUT"
