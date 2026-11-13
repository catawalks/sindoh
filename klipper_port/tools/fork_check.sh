#!/bin/sh
# Guard against the Klipper code drifting into two homes again.
#   sh tools/fork_check.sh [FORK_CHECKOUT]
# Without an argument it checks out the pinned fork (klipper/FORK) into a
# temporary directory. Checks:
#  1. this repo holds no Klipper code (klipper/ = FORK, get_fork.sh, config/);
#  2. the fork holds no printer configuration;
#  3. the two IPC headers shared with upctool are identical in both
#     (common/ here is their home; the fork carries a copy to build);
#  4. the fork has the three host modules.
set -e
here=$(cd "$(dirname "$0")/.." && pwd)
fail=0
bad() { echo "FORK-CHECK FAIL: $*"; fail=1; }
sum() { tr -d '\015' < "$1" | md5sum; }      # ignore CRLF checkouts
for d in src configs extras patches; do
    [ -e "$here/klipper/$d" ] && bad "klipper/$d exists here: Klipper code lives only in the fork"
done
fork=$1
if [ -z "$fork" ]; then
    fork=$(mktemp -d); trap 'rm -rf "$fork"' EXIT
    sh "$here/klipper/get_fork.sh" "$fork" >/dev/null
fi
ls "$fork"/config/sindoh-dp200/*.cfg >/dev/null 2>&1 &&
    bad "the fork has printer .cfg files: they live only in klipper/config here"
for h in upc_hw.h upc_ipc.h; do
    [ "$(sum "$here/common/$h")" = "$(sum "$fork/src/upc/$h")" ] ||
        bad "common/$h differs from the fork's src/upc/$h"
done
for f in upc_stats.py upc_clockcheck.py dp200_cartridge.py; do
    [ -f "$fork/klippy/extras/$f" ] || bad "the fork lacks klippy/extras/$f"
done
[ $fail = 0 ] && echo "FORK-CHECK OK ($(git -C "$fork" rev-parse --short HEAD))"
exit $fail
