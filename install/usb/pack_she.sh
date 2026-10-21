#!/bin/sh
# Pack a shell script into Sindoh's encrypted ".she" format, as read by the
# stock /app/auto_update.sh:  .she = openssl des3 (salted, MD5 key derivation)
# of a tar.bz2 that holds the .sh at its top level. The DES3 password is
# itself stored in the printer's /app/crypto_key.dat (des3, empty password,
# tar.bz2). The key is NOT part of this repository: pass the crypto_key.dat
# from your own printer (e.g. scp it, or copy it from a /app backup).
#
#   sh pack_she.sh crypto_key.dat unmistakable_klipper_install.sh [out_dir]
#
# Runs on any Linux with openssl (1.0 or 3.x: "-md md5" keeps the old
# key derivation the printer expects) and on the printer itself
# (PATH=/usr/local/ssl/bin:$PATH).
set -e
KEYFILE=$1
SCRIPT=$2
OUT=${3:-.}
[ -f "$KEYFILE" ] && [ -f "$SCRIPT" ] || { echo "usage: $0 crypto_key.dat script.sh [out_dir]"; exit 2; }
case "$SCRIPT" in *.sh) ;; *) echo "script must end in .sh"; exit 2 ;; esac

KEY=`openssl des3 -d -salt -md md5 -k "" -in "$KEYFILE" | tar -xjO`
[ -n "$KEY" ] || { echo "could not read the key from $KEYFILE"; exit 1; }
NAME=`basename "$SCRIPT"`
DIR=`dirname "$SCRIPT"`
# auto_update.sh runs /tmp/<name>.sh after extracting: the tar must hold the
# bare file name with exec permission
chmod 755 "$SCRIPT"
tar -cjf - -C "$DIR" "$NAME" | openssl des3 -e -salt -md md5 -k "$KEY" > "$OUT/${NAME}e"
echo "wrote $OUT/${NAME}e"

# self-check: decrypt again and compare
openssl des3 -d -salt -md md5 -k "$KEY" -in "$OUT/${NAME}e" | tar -xjO "$NAME" | cmp - "$SCRIPT" && echo "verified"
