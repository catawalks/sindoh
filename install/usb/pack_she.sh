#!/bin/sh
# Pack a shell script into Sindoh's encrypted ".she" format, as read by the
# stock /app/auto_update.sh:  .she = openssl des3 (salted, MD5 key derivation)
# of a tar.bz2 that holds the .sh at its top level. The DES3 password is the
# DP200 family's update key (Sindoh, Stanley, Leon3D, Mimaki; it is what
# /app/crypto_key.dat decrypts to and is already public). It is built in;
# pass a crypto_key.dat with -k for a printer that uses another key.
#
#   sh pack_she.sh [-k crypto_key.dat] unmistakable_klipper_install.sh [out_dir]
#
# The old form "pack_she.sh crypto_key.dat script.sh [out_dir]" still works.
# Runs on any Linux with openssl (1.0 or 3.x: "-md md5" keeps the old
# key derivation the printer expects) and on the printer itself
# (PATH=/usr/local/ssl/bin:$PATH).
set -e
KEY=sindoh024601779
KEYFILE=
if [ "$1" = "-k" ]; then
    KEYFILE=$2; shift 2
elif [ $# -ge 2 ] && [ -f "$1" ] && case "$1" in *.sh) false ;; *) true ;; esac; then
    KEYFILE=$1; shift
fi
SCRIPT=$1
OUT=${2:-.}
[ -f "$SCRIPT" ] || { echo "usage: $0 [-k crypto_key.dat] script.sh [out_dir]"; exit 2; }
case "$SCRIPT" in *.sh) ;; *) echo "script must end in .sh"; exit 2 ;; esac

if [ -n "$KEYFILE" ]; then
    [ -f "$KEYFILE" ] || { echo "no such key file: $KEYFILE"; exit 2; }
    KEY=`openssl des3 -d -salt -md md5 -k "" -in "$KEYFILE" | tar -xjO`
    [ -n "$KEY" ] || { echo "could not read the key from $KEYFILE"; exit 1; }
fi
NAME=`basename "$SCRIPT"`
DIR=`dirname "$SCRIPT"`
# auto_update.sh runs /tmp/<name>.sh after extracting: the tar must hold the
# bare file name with exec permission
chmod 755 "$SCRIPT"
tar -cjf - -C "$DIR" "$NAME" | openssl des3 -e -salt -md md5 -k "$KEY" > "$OUT/${NAME}e"
echo "wrote $OUT/${NAME}e"

# self-check: decrypt again and compare
openssl des3 -d -salt -md md5 -k "$KEY" -in "$OUT/${NAME}e" | tar -xjO "$NAME" | cmp - "$SCRIPT" && echo "verified"
