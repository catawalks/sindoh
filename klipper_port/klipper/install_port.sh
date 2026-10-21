#!/bin/sh
# Add the Sindoh DP200 UPC port to a Klipper source tree.
#
#   ./install_port.sh [~/klipper]
#
# Copies src/upc (plus the shared headers) into the tree and registers
# MACH_UPC in src/Kconfig. Safe to run again after a Klipper update.
set -e
K=${1:-$HOME/klipper}
HERE=$(cd "$(dirname "$0")" && pwd)

[ -f "$K/src/Kconfig" ] || { echo "no Klipper tree at $K" >&2; exit 1; }

rm -rf "$K/src/upc"
cp -r "$HERE/src/upc" "$K/src/upc"
cp "$HERE/../common/upc_hw.h" "$HERE/../common/upc_ipc.h" "$K/src/upc/"

if ! grep -q 'MACH_UPC' "$K/src/Kconfig"; then
    python3 - "$K/src/Kconfig" <<'EOF'
import sys
path = sys.argv[1]
s = open(path).read()
choice = '    config MACH_AR100\n'
entry = ('    config MACH_UPC\n'
         '        bool "Marvell 88PA6170 UPC (Sindoh DP200)"\n')
src = 'source "src/ar100/Kconfig"\n'
if choice not in s or src not in s:
    sys.exit("src/Kconfig layout not recognized - add MACH_UPC by hand")
s = s.replace(choice, entry + choice, 1)
s = s.replace(src, src + 'source "src/upc/Kconfig"\n', 1)
open(path, 'w').write(s)
EOF
    echo "registered MACH_UPC in $K/src/Kconfig"
fi

mkdir -p "$K/config"
cp "$HERE/configs/dp200_fm.config" "$HERE/configs/dp200_io.config" "$K/config/"
echo "UPC port installed. Build each core with, e.g.:"
echo "  cd $K && cp config/dp200_fm.config .config && make olddefconfig && make"
echo "  cp out/klipper.bin ~/dp200/fm.bin"
