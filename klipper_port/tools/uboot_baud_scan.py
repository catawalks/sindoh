"""Find the baud rate of the DP200's pre-U-Boot boot stage (the "garbage" at power-on).

Needs the printer sitting at the U-Boot prompt (or Linux, with --from-linux, which
reboots it). For each candidate rate: send "reset" at 115200, switch the PC port to
the candidate rate and record the first stage, then switch back to 115200 and stop
U-Boot's 1 s autoboot again. Nothing is flashed; the printer is left at the U-Boot
prompt (no Linux, no heaters).

    python tools/uboot_baud_scan.py COM3 [--from-linux] [rates...]
"""
import sys, time
import serial

UBOOT = 115200
PROMPT_KEYS = (b'Hit any key', b'autoboot')

def stop_autoboot(s, timeout=40):
    """Wait for U-Boot's countdown at 115200 and press a key; return the text seen."""
    s.baudrate = UBOOT
    buf, t0 = b'', time.time()
    while time.time() - t0 < timeout:
        buf += s.read(4096)
        if any(k in buf for k in PROMPT_KEYS):
            s.write(b' ')
            time.sleep(0.3)
            s.write(b'\r')
            time.sleep(0.5)
            buf += s.read(4096)
            return buf
    return buf

def score(data):
    """Fraction of printable ASCII / CR / LF bytes."""
    if not data:
        return 0.0
    ok = sum(1 for c in data if 32 <= c < 127 or c in (10, 13))
    return ok / len(data)

def main():
    port = sys.argv[1]
    from_linux = '--from-linux' in sys.argv
    rates = [int(a) for a in sys.argv[2:] if a.isdigit()] or \
        [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
    s = serial.Serial(port, UBOOT, timeout=0.05)
    if from_linux:
        s.write(b'sync; reboot\n')
    else:
        s.write(b'\rreset\r')
    seen = stop_autoboot(s)
    if not any(k in seen for k in PROMPT_KEYS):
        sys.exit('did not see the U-Boot countdown:\n' + seen[-500:].decode('latin1'))
    print('at the U-Boot prompt')
    results = []
    for rate in rates:
        s.reset_input_buffer()
        s.write(b'reset\r')
        s.flush()
        time.sleep(0.02)                         # let "reset" leave the UART
        s.baudrate = rate
        first, t0 = b'', time.time()
        # first stage only: it ends ~1.0 s after reset (U-Boot banner), and U-Boot's
        # 1 s countdown starts at ~3.9 s, which leaves ~3 s to switch back
        while time.time() - t0 < 0.9:
            first += s.read(4096)
        seen = stop_autoboot(s)
        ok = any(k in seen for k in PROMPT_KEYS)
        results.append((rate, score(first), first))
        print('%7d baud: %4d bytes, %3.0f %% printable, back at prompt: %s'
              % (rate, len(first), 100 * score(first), ok))
        print('         ' + repr(first[:160]))
        if not ok:
            print('lost the U-Boot prompt - stopping')
            break
    best = max(results, key=lambda r: (r[1], len(r[2])))
    print('\nbest: %d baud (%.0f %% printable)' % (best[0], 100 * best[1]))
    print(best[2].decode('latin1'))
    s.close()

main()
