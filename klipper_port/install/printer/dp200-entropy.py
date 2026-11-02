#!/usr/bin/python3
"""Seed the stock 3.2 kernel's entropy pool at boot (run in the Debian root
by dp200-start.sh before the stack starts).

Kernel 3.2 has no getrandom(): OpenSSL 3 (Moonraker, the screen's urllib)
waits until /dev/random reports 64 bits of entropy before it uses
/dev/urandom. The pool only grows from interrupts and disk timing; with the
root on the SD card its reads filled it, but with the root on NAND it stayed
at ~57 bits and Moonraker and the screen app hung at startup (2026-11-02).

Like systemd-random-seed: a seed saved at the previous boot is written into
the pool and credited (RNDADDENTROPY), mixed with fresh /dev/urandom bytes;
then a new seed is saved for the next boot. The first boot has no seed and
credits /dev/urandom output alone.
"""
import fcntl, os, struct, sys

SEED = '/var/lib/dp200/random-seed'
RNDADDENTROPY = 0x40085203
SIZE = 512

def credit(data, bits):
    with open('/dev/random', 'wb') as f:
        fcntl.ioctl(f, RNDADDENTROPY, struct.pack('ii', bits, len(data)) + data)

def main():
    try:
        with open(SEED, 'rb') as f:
            seed = f.read(SIZE)
    except OSError:
        seed = b''
    data = seed + os.urandom(64)
    credit(data, min(len(data) * 8, 4096))
    os.makedirs(os.path.dirname(SEED), exist_ok=True)
    tmp = SEED + '.new'
    with open(tmp, 'wb') as f:
        f.write(os.urandom(SIZE))
    os.chmod(tmp, 0o600)
    os.replace(tmp, SEED)
    with open('/proc/sys/kernel/random/entropy_avail') as f:
        print('dp200-entropy: %s seed, pool %s bits'
              % ('saved' if seed else 'no', f.read().strip()))

if __name__ == '__main__':
    try:
        main()
    except Exception as e:                  # never block the boot on this
        print('dp200-entropy: %s' % e, file=sys.stderr)
