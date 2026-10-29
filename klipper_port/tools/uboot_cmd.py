"""Talk to the DP200 U-Boot 2011.09 prompt safely over the serial console.

usage:
    uboot_cmd.py COMPORT --catch [--log RAW.bin]     reboot Linux, stop autoboot
    uboot_cmd.py COMPORT CMD [CMD ...]               run allow-listed commands
    uboot_cmd.py COMPORT --reset                     'reset' back to stock boot

--catch: sends 'sync; reboot' to the Linux shell (stop Klipper first), waits
for "Hit any key to stop autoboot" and only then sends ONE space, which
U-Boot's getc() consumes. Nothing else is sent, so a missed window just boots
Linux as normal.

Commands go through uboot_upload.Console: typed without the terminator, the
echo must match exactly, then ONE '\\r' (never an empty line: hush repeats the
last command on one). Only read-only commands are allowed; 'reset' only via
--reset. setenv/saveenv/nand/mmc/i2c/run/mw/bootm/go are refused here.
"""
import re
import sys
import time

sys.path.insert(0, __file__.rsplit('\\', 1)[0].rsplit('/', 1)[0])
from uboot_upload import Console, SerialLink, UploadError, check_prompt  # noqa: E402

ALLOWED = ('help', 'bdinfo', 'printenv', 'version', 'coninfo', 'iminfo',
           'md', 'md.l', 'md.w', 'md.b', 'crc32')


def allowed(cmd):
    if ';' in cmd or '$' in cmd or '\n' in cmd or '\r' in cmd:
        return False
    argv = cmd.split()
    if not argv or argv[0] not in ALLOWED:
        return False
    if argv[0] == 'crc32' and len(argv) != 3:      # never the 'store' form
        return False
    return True


def catch(port, log):
    import serial
    s = serial.Serial(port, 115200, timeout=0.01)
    s.reset_input_buffer()
    s.write(b'sync; reboot\n')
    t0, buf = time.time(), b''
    while time.time() - t0 < 120:
        buf += s.read(4096)
        if b'Hit any key to stop autoboot' in buf:
            s.write(b' ')
            end = time.time() + 3
            while time.time() < end and not buf.rstrip(b' ').endswith(b'#'):
                buf += s.read(4096)
            break
    else:
        s.close()
        sys.exit('no autoboot countdown seen in 120 s')
    time.sleep(0.5)
    buf += s.read(65536)
    s.close()
    if log:
        open(log, 'wb').write(buf)
    print(buf[-1500:].decode('latin1'))
    print('--- caught at %.1f s' % (time.time() - t0))


def main():
    port, args = sys.argv[1], sys.argv[2:]
    log = None
    if '--log' in args:
        i = args.index('--log')
        log = args[i + 1]
        del args[i:i + 2]
    if args == ['--catch']:
        return catch(port, log)
    link = SerialLink(port, log)
    try:
        con = Console(link)
        print('prompt check:', check_prompt(con))
        if args and args[0] == '--bootm':
            # bootm ADDR: only after iminfo verifies the image in RAM; then
            # record the console for SECS seconds (nothing more is sent).
            addr, secs = int(args[1], 16), float(args[2]) if len(args) > 2 else 120
            if not 0x01000000 <= addr < 0x17F00000:
                sys.exit('bootm address outside the safe window')
            out = con.command('iminfo %x' % addr, timeout=10.0).decode('latin1')
            print(out)
            if 'Verifying Checksum ... OK' not in out:
                sys.exit('iminfo did not verify the image: not booting')
            con._type(b'bootm %x' % addr)
            link.write(b'\r')
            t0, buf = time.time(), b''
            while time.time() - t0 < secs:
                d = link.read(0.2)
                if d:
                    buf += d
                    sys.stdout.write(d.decode('latin1'))
                    sys.stdout.flush()
            print('\n--- %d bytes in %.0f s' % (len(buf), secs))
            return
        if args == ['--reset']:
            con.sync()
            con._type(b'reset')
            link.write(b'\r')
            time.sleep(1.0)
            print(link.read(0.5).decode('latin1'))
            print('reset sent; send NOTHING on the port until Linux is up')
            return
        for cmd in args:
            if not allowed(cmd):
                sys.exit('refused (not allow-listed): %r' % cmd)
        for cmd in args:
            out = con.command(cmd, timeout=10.0)
            print('### ' + cmd)
            print(out.decode('latin1').rstrip())
    finally:
        link.close()


if __name__ == '__main__':
    try:
        main()
    except UploadError as e:
        sys.exit('error: %s' % e)
