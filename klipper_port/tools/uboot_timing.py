"""Reboot (from Linux or from the U-Boot prompt) and timestamp the boot output at
115200 until U-Boot's countdown, then stop autoboot. Prints when the first byte,
the U-Boot banner and the countdown arrived, and saves the raw bytes.
    python tools/uboot_timing.py COM3 --from-linux|--from-uboot OUT.bin"""
import sys, time
import serial

port, mode, out = sys.argv[1], sys.argv[2], sys.argv[3]
s = serial.Serial(port, 115200, timeout=0.01)
s.reset_input_buffer()
s.write(b'sync; reboot\n' if mode == '--from-linux' else b'\rreset\r')
t_cmd = time.time()
buf, marks = b'', {}
while time.time() - t_cmd < 90:
    d = s.read(4096)
    if d:
        now = time.time() - t_cmd
        buf += d
        if 'first' not in marks and mode == '--from-uboot':
            marks['first'] = now
        for name, key in (('banner', b'U-Boot 2011'), ('countdown', b'Hit any key')):
            if name not in marks and key in buf:
                marks[name] = now
        if 'countdown' in marks:
            s.write(b' ')
            time.sleep(0.3)
            s.write(b'\r')
            time.sleep(0.5)
            buf += s.read(4096)
            break
open(out, 'wb').write(buf)
print(marks)
print(buf[-300:].decode('latin1'))
