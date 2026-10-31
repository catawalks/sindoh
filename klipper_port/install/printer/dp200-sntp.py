#!/usr/bin/python3
"""One-shot clock sync for the mainline boot (init.mainline), where the
Debian root has no ntpd (Debian's busybox leaves the applet out). Asks NTP
servers (SNTP, RFC 4330) until one answers, sets the system clock, then saves
it to the RTC with BusyBox hwclock. Retries while the network comes up.

    dp200-sntp.py [--dry-run] [--wait SECONDS] [SERVER ...]

On stock, dp200-start.sh uses the stock BusyBox ntpd instead.
"""
import socket
import struct
import subprocess
import sys
import time

SERVERS = ['pool.ntp.org', '0.pool.ntp.org', '1.pool.ntp.org', 'time.google.com']
NTP_EPOCH = 2208988800                 # 1900-01-01 to 1970-01-01, in seconds


def ts(b):
    sec, frac = struct.unpack('!II', b)
    return sec - NTP_EPOCH + frac / 2 ** 32


def query(server, timeout=3.0):
    """Clock offset in seconds (server time - our time) from one exchange."""
    addr = socket.getaddrinfo(server, 123, socket.AF_INET, socket.SOCK_DGRAM)[0][4]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        t1 = time.time()
        sec = int(t1) + NTP_EPOCH
        req = b'\x23' + bytes(39) + struct.pack('!II', sec, int((t1 % 1) * 2 ** 32))
        s.sendto(req, addr)
        data, _ = s.recvfrom(512)
        t4 = time.time()
    if len(data) < 48:
        raise ValueError('short reply')
    mode, stratum = data[0] & 7, data[1]
    if mode != 4 or not 1 <= stratum <= 15:
        raise ValueError('bad reply (mode %d, stratum %d)' % (mode, stratum))
    if data[24:32] != req[40:48]:
        raise ValueError('reply does not match the request')
    t2, t3 = ts(data[32:40]), ts(data[40:48])
    return ((t2 - t1) + (t3 - t4)) / 2


def main():
    args = sys.argv[1:]
    dry = '--dry-run' in args
    wait = 120.0
    if '--wait' in args:
        i = args.index('--wait')
        wait = float(args[i + 1])
        del args[i:i + 2]
    servers = [a for a in args if not a.startswith('--')] or SERVERS
    end = time.time() + wait
    while True:
        for srv in servers:
            try:
                off = query(srv)
            except (OSError, ValueError) as e:
                last = '%s: %s' % (srv, e)
                continue
            print('dp200-sntp: %s offset %+.3f s' % (srv, off), flush=True)
            if dry:
                return 0
            time.clock_settime(time.CLOCK_REALTIME, time.time() + off)
            # the RTC (BusyBox hwclock; the rtc-mv61x0 set_time is enabled)
            r = subprocess.run(['busybox', 'hwclock', '-w', '-u'])
            print('dp200-sntp: clock set to %s UTC%s' % (
                time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()),
                '' if r.returncode == 0 else ', RTC not saved'), flush=True)
            return 0
        if time.time() >= end:
            print('dp200-sntp: no NTP server answered (%s)' % last, flush=True)
            return 1
        time.sleep(5)


if __name__ == '__main__':
    sys.exit(main())
