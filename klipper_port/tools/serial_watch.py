"""Send one shell command to the printer console and record its output for a
fixed time (no end-marker detection, so long-running monitors are captured).

usage: serial_watch.py COMPORT SECONDS COMMAND
"""
import sys
import time

import serial

port, secs, cmd = sys.argv[1], float(sys.argv[2]), sys.argv[3]
s = serial.Serial(port, 115200, timeout=0.2)
s.reset_input_buffer()
s.write(cmd.encode() + b'\n')
t0 = time.time()
print('--- watching %.0f s from %s' % (secs, time.strftime('%H:%M:%S')), flush=True)
while time.time() - t0 < secs:
    d = s.read(4096)
    if d:
        sys.stdout.write(d.decode('latin1'))
        sys.stdout.flush()
s.close()
print('\n--- done at %s' % time.strftime('%H:%M:%S'))
