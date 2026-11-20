#!/bin/sh
# SSH access to a stock Sindoh printer, from a USB stick (dev use).
#
# The stock /app/auto_update.sh runs this from the model's stick folder.
# It starts the printer's own dropbear (stock: /usr/sbin/dropbear, not
# running) on port 2222, with key-only login for root:
#   - a fresh host key in /tmp;
#   - root's home /root is covered (bind mount) by a /tmp copy holding
#     our public key in .ssh/authorized_keys; the real /root is not changed;
#   - password logins are off (-s).
# Nothing is written to the flash: a reboot removes all of it. It writes
# remote_shell_<time>.txt to the stick: the addresses, the port, and the
# host key fingerprint. No screen messages (the stock app stays as is).
#
# Packed by pack.py, which puts the public key into PUBKEY below.
PUBKEY='@PUBKEY@'
PORT=2222
STICK=${1:-.}
W=/tmp/remote_shell
LOG=$W/log

mkdir -p $W
: > $LOG
# the version line of /snapshot_version.sh, read as text (never run it)
FW=`sed -n "s/.*echo '\(.*\)'.*/\1/p" /snapshot_version.sh 2>/dev/null | head -n 1`
log() { echo "$*" >> $LOG; echo "[remote_shell] $*"; }

DB=`command -v dropbear || echo /usr/sbin/dropbear`
DK=`command -v dropbearkey || echo /usr/bin/dropbearkey`
if [ ! -x "$DB" ] || [ ! -x "$DK" ]; then
    log "no dropbear on this printer"
elif [ -f $W/dropbear.pid ] && kill -0 "`cat $W/dropbear.pid`" 2>/dev/null; then
    log "already running (pid `cat $W/dropbear.pid`)"
else
    [ -f $W/host_ecdsa ] || "$DK" -t ecdsa -s 256 -f $W/host_ecdsa >> $LOG 2>&1
    # root's home, in RAM: a copy of /root plus our key
    if ! grep -q " /root " /proc/mounts; then
        rm -rf $W/root
        mkdir -p $W/root
        cp -a /root/. $W/root/ 2>/dev/null
        mkdir -p $W/root/.ssh
        echo "$PUBKEY" > $W/root/.ssh/authorized_keys
        chmod 700 $W/root $W/root/.ssh
        chmod 600 $W/root/.ssh/authorized_keys
        mount --bind $W/root /root && log "/root covered by a RAM copy"
    fi
    # its own session, so it outlives the stock update script
    SS=`command -v setsid`
    $SS "$DB" -r $W/host_ecdsa -p $PORT -s -P $W/dropbear.pid \
        </dev/null >/dev/null 2>&1 &
    sleep 2
    if [ -f $W/dropbear.pid ] && kill -0 "`cat $W/dropbear.pid`" 2>/dev/null; then
        log "dropbear running on port $PORT (pid `cat $W/dropbear.pid`)"
    else
        log "dropbear did not start"
    fi
fi

# what the owner needs: where to connect
OUT="$STICK/../remote_shell_`date +%Y%m%d-%H%M%S`.txt"
{
    echo "remote shell, `date`"
    echo "firmware: $FW"
    cat $LOG
    echo "port: $PORT, user: root, key login only"
    echo "host key: `\"$DK\" -y -f $W/host_ecdsa 2>/dev/null | grep -i fingerprint`"
    echo "addresses:"
    ip -4 addr 2>/dev/null | grep -E "inet |^[0-9]" ||
        ifconfig 2>/dev/null | grep -E "Link encap|inet addr"
} > "$OUT" 2>&1
sync
exit 0
