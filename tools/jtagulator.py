#!/usr/bin/env python3
"""Talk to a JTAGulator (Grand Idea Studio) on a serial port.

  jtagulator.py [--port COM4] CMD [CMD ...]     send each line, print replies
  jtagulator.py --port COM4                       interactive (type lines)

The JTAGulator speaks a text menu at 115200 8N1 (prompt ':'). Each CMD is
sent with CR; a reply ends at the next prompt or after --wait seconds of
silence. Example (target at 3.3 V, IDCODE scan of channels 0-11):
  jtagulator.py J V 3.3 I 0 11 N
"""
import argparse
import sys
import time

import serial


def read_reply(s, wait):
    out, last = b'', time.time()
    while time.time() - last < wait:
        d = s.read(4096)
        if d:
            out += d
            last = time.time()
    return out.decode('latin1')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', default='COM4')
    ap.add_argument('--wait', type=float, default=1.5, help='s of silence that ends a reply')
    ap.add_argument('cmds', nargs='*')
    ap.add_argument('--no-cr', action='store_true',
                    help='do not send the initial CR (continue an open prompt)')
    a = ap.parse_args()
    s = serial.Serial(a.port, 115200, timeout=0.1)
    if not a.no_cr:
        s.write(b'\r')
        sys.stdout.write(read_reply(s, a.wait))
    lines = a.cmds or iter(lambda: sys.stdin.readline().rstrip('\n'), 'quit')
    for c in lines:
        s.write(c.encode() + b'\r')
        sys.stdout.write(read_reply(s, a.wait))
        sys.stdout.flush()


if __name__ == '__main__':
    main()
