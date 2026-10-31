#!/bin/bash
# Regenerate patches/0010 (guarded NAND write) from an edit script:
# vanilla marvell_nand.c + patch 0006's hunks for it = a/, + EDIT = b/.
#   tools/regen_0010.sh EDIT.py      (in WSL; needs $WORK/pristine from build.sh)
set -euo pipefail
M1=$(cd "$(dirname "$0")/.." && pwd)
EDIT=$1
KVER=6.18.59
WORK=${WORK:-$HOME/dp200}
F=drivers/mtd/nand/raw/marvell_nand.c
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/a/$(dirname $F)" "$T/b/$(dirname $F)"
cp "$WORK/pristine/linux-$KVER/$F" "$T/a/$F"
# only 0006's marvell_nand.c part
awk -v f="$F" '/^diff -ru /{keep = index($0, "a/" f) > 0} keep' \
	"$M1/patches/0006-mtd-rawnand-read-only-marvell-mv61x0.patch" > "$T/0006.patch"
patch -d "$T/a" -p1 -s < "$T/0006.patch"
cp "$T/a/$F" "$T/b/$F"
python3 "$EDIT" "$T/b/$F"
(cd "$T" && diff -u "a/$F" "b/$F" || true) |
	sed -E 's@^(---|\+\+\+) ([ab]/[^\t]*)\t.*@\1 \2@' \
	> "$M1/patches/0010-mtd-rawnand-marvell-mv61x0-guarded-write.patch"
wc -l "$M1/patches/0010-mtd-rawnand-marvell-mv61x0-guarded-write.patch"
