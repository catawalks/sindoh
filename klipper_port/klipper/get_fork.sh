#!/bin/sh
# Check out the pinned DP200 Klipper fork (klipper/FORK) into a directory.
#   sh get_fork.sh DEST
# DEST then holds upstream Klipper plus the UPC MCU port, the host modules
# and the build configs (config/dp200_fm.config, dp200_io.config). Nothing
# is copied in from this repo: the fork is the one home for Klipper code.
# An existing checkout is moved to the pinned commit (it must be clean).
set -e
DEST=${1:?usage: get_fork.sh DEST}
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/FORK"
if [ -d "$DEST/.git" ]; then
    [ -z "$(git -C "$DEST" status --porcelain --untracked-files=no)" ] ||
        { echo "get_fork: $DEST has local changes" >&2; exit 1; }
    git -C "$DEST" remote set-url origin "$REPO"
else
    mkdir -p "$DEST"
    git -C "$DEST" init -q
    git -C "$DEST" remote add origin "$REPO"
fi
git -C "$DEST" fetch -q --depth 1 origin "$COMMIT"
git -C "$DEST" checkout -q -B "$BRANCH" FETCH_HEAD
[ -f "$DEST/src/upc/Kconfig" ] || { echo "get_fork: no src/upc in $COMMIT" >&2; exit 1; }
echo "klipper fork: $BRANCH $(git -C "$DEST" rev-parse --short HEAD)"
