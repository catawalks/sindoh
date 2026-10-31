"""Talk to the DP200 U-Boot 2011.09 prompt safely over the serial console.

usage:
    uboot_cmd.py COMPORT --catch [--log RAW.bin]     reboot Linux, stop autoboot
    uboot_cmd.py COMPORT CMD [CMD ...]               run allow-listed commands
    uboot_cmd.py COMPORT --reset                     'reset' back to stock boot

--catch: sends 'sync; reboot' (reboot -f on a 6.x test kernel) to the Linux
shell (stop Klipper first), waits
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


def allowed_sd(cmd):
    """Read-only SD commands: probe/info/list, and ext2load into the upload window."""
    argv = cmd.split()
    if not argv or ';' in cmd or '$' in cmd:
        return False
    if argv[0] == 'mmc':
        return len(argv) >= 2 and argv[1] in ('rescan', 'info', 'list', 'part')
    if argv[0] in ('mmcinfo', 'ext2ls'):
        return True
    if argv[0] == 'ext2load' and len(argv) >= 4:
        return 0x01000000 <= int(argv[3], 16) < 0x17F00000
    return False


def catch(port, log):
    import serial
    s = serial.Serial(port, 115200, timeout=0.01)
    s.reset_input_buffer()
    # the m1 test kernels' /init ignores a plain reboot: force it there only
    # (the Debian root on mainline has no /sbin/reboot: BusyBox's then)
    s.write(b'sync; case $(uname -r) in 6.*) reboot -f || busybox reboot -f ;; *) reboot ;; esac\n')
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
        if args == ['--pinmux-sd']:
            # User-approved 2026-10-29: route the last two SD pins like stock
            # Linux does (all six SD pin selects read 0x00001002 there; U-Boot
            # leaves these two at 0x1001 / 0x0). RAM-only register state.
            for addr in (0xf8041080, 0xf8041084):
                con.command('mw.l %x 1002' % addr, timeout=5.0)
            print(con.command('md.l f8041080 2', timeout=5.0).decode('latin1'))
            return
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
            if not (allowed(cmd) or allowed_sd(cmd)):
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
