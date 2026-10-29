"""Upload a file into DP200 RAM through the U-Boot 2011.09 serial console.

usage:
    uboot_upload.py COMPORT FILE LOADADDR [--chunk N] [--dry-run] [--log RAW.bin]
    uboot_upload.py COMPORT --check [--addr LOADADDR]
    uboot_upload.py --fake  FILE LOADADDR [--fake-drop P]
    python -I tools/uboot_upload.py --selftest

U-Boot must already be sitting at its "# " prompt. This tool never reboots the
board and never tries to catch the autoboot countdown; do that by hand (any key
stops it, see docs/no_gpl_plan.md 2.3).

What goes over the wire, and nothing else:
    mw.l ADDR VAL [COUNT]   (RAM write, chained with ';', max ~480 chars a line)
    md.l ADDR COUNT         (read-only; locates bad words after a CRC mismatch)
    crc32 ADDR LEN          (read-only; no store argument is ever given)
    ^C (0x03)               (throws away a half-typed line; also clears hush's
                             "repeat last command" flag)
There is no setenv, saveenv, nand, mmc, i2c, run, bootm or go anywhere in this
file. Booting the uploaded image is done by hand afterwards.

How a line is sent (the console drops characters if overrun):
 1. Type the line WITHOUT the terminator and read the echo. U-Boot echoes every
    character it accepted, so an exact echo proves the line buffer is right.
    With --window N at most N characters are ever un-echoed, which also bounds
    how full U-Boot's (16-byte) RX FIFO can get.
 2. Echo wrong / short / BEL -> send ^C, wait for the prompt, type it again.
    A corrupted line is therefore never executed (a dropped space could
    otherwise turn "mw.l A V N" into a write to a wild address).
 3. Echo right -> send ONE '\\r', wait for "\\n# ". mw.l prints nothing.
Every --chunk bytes the tool runs crc32 over the chunk and compares it with
zlib.crc32. On a mismatch it reads the chunk back with md.l, rewrites the bad
words and checks again; then it falls back to resending the whole chunk. At
the end it runs crc32 over the whole (word-padded) image.

pyserial is needed only for a real port (pip install pyserial; on this PC the
copy in the Python 3.15t user site works: py -3.15t tools/uboot_upload.py ...).
"""
import argparse
import os
import random
import re
import struct
import sys
import time
import zlib

# ---------------------------------------------------------------------------
# Safe upload window.
# From the offline U-Boot analysis (D:\DP200\uboot_work, uboot.elf cut from
# nand_images/mtd0.bin @0x180), assuming ram_size = 0x20000000 at base 0
# (env DRAM_SIZE=536870912 / mem_MiB=512; dram_init 0xf92a01f6):
#   0x00000000-0x00000100  vectors, ATAGs at 0x100 (board_init 0xf929f816)
#   0x00008000-...         bootm destination of the kernel
#   0x00400000             CONFIG_SYS_LOAD_ADDR / downld_addr (stock nand read)
#   0x18000000-0x180BB800  boot-logo framebuffer, ram_size-0x8000000, scanned
#                          out by the LCD (board_init_r 0xf92810d8-0xf928111c)
#   0x1FBBBF50 and up      U-Boot stack, gd, bd, malloc (0x1FBBC000), code
#                          (0x1FFBE000) and TLB (0x1FFF0000) (board_init_f
#                          0xf92811ce-0xf9281310)
# => [0x01000000, 0x17F00000). Confirm with the read-only `bdinfo` first.
SAFE_LO = 0x01000000
SAFE_HI = 0x17F00000

BAUD = 115200
CHAR_T = 10.0 / BAUD          # seconds per character, 8N1
MAX_LINE_HW = 509             # readline rings BEL after 0x1FD chars
MIN_LINE = 64                 # shortest line the adaptive packer goes down to
UIMAGE_MAGIC = 0x27051956


class UploadError(Exception):
    pass


class LineFailed(UploadError):
    pass


def check_window(addr, length):
    """Refuse anything that is not fully inside the safe window."""
    if addr % 4:
        raise UploadError('LOADADDR 0x%x is not word aligned' % addr)
    end = addr + length
    if addr < SAFE_LO or end > SAFE_HI or length <= 0:
        raise UploadError('0x%08x..0x%08x is outside the safe window '
                          '0x%08x..0x%08x' % (addr, end, SAFE_LO, SAFE_HI))


# ---------------------------------------------------------------------------
# Links. Each one has write(bytes), read(timeout) -> bytes and now().

class SerialLink:
    def __init__(self, port, log=None):
        try:
            import serial
        except ImportError:
            raise UploadError('pyserial is not importable (pip install pyserial, '
                              'or run with py -3.15t without -I)')
        self.s = serial.Serial(port, BAUD, bytesize=8, parity='N', stopbits=1,
                               timeout=0, xonxoff=False, rtscts=False)
        self.log = open(log, 'wb') if log else None

    def write(self, data):
        self.s.write(data)
        if self.log:
            self.log.write(b'\n>>' + data + b'<<\n')

    def read(self, timeout):
        end = time.monotonic() + timeout
        while True:
            n = self.s.in_waiting
            if n:
                d = self.s.read(n)
                if self.log:
                    self.log.write(d)
                return d
            if time.monotonic() >= end:
                return b''
            time.sleep(0.0005)

    def now(self):
        return time.monotonic()

    def close(self):
        self.s.close()
        if self.log:
            self.log.close()


class FakeUBoot:
    """Just enough of U-Boot 2011.09 + hush: readline with echo, BEL past 509
    chars, ^C, CR/LF, empty line repeats the last line, mw.l/md.l/crc32.
    RAM is modelled only inside the safe window; any write outside it, and any
    other command, is recorded as a violation."""

    ALLOWED = ('mw.l', 'md.l', 'crc32')

    def __init__(self, ram_corrupt=0.0, rng=None):
        self.ram = {}                 # word address -> value (sparse)
        self.buf = bytearray()
        self.last = b''
        self.repeat = False
        self.out = bytearray()
        self.violations = []
        self.empty_lines = 0          # empty lines executed (repeat or not)
        self.repeats = 0
        self.commands = 0
        self.ram_corrupt = ram_corrupt
        self.rng = rng or random.Random(0)
        self.exec_time = 0.0
        self.out.extend(b'# ')

    def _word(self, a):
        return self.ram.get(a, 0xE7E7E7E7)    # "uninitialised" RAM

    def feed(self, data):
        for c in data:
            if c in (0x0D, 0x0A):
                self.out.extend(b'\r\n')
                line = bytes(self.buf)
                self.buf.clear()
                if line:
                    self.last, self.repeat = line, True
                    self._run(line)
                else:
                    self.empty_lines += 1
                    if self.repeat:
                        self.repeats += 1
                        self._run(self.last)
                self.out.extend(b'# ')
            elif c == 0x03:
                self.buf.clear()
                self.repeat = False
                self.out.extend(b'# ')
            elif len(self.buf) >= MAX_LINE_HW:
                self.out.append(0x07)
            else:
                self.buf.append(c)
                self.out.append(c)

    def _print(self, s):
        self.out.extend(s.replace('\n', '\r\n').encode())

    def _run(self, line):
        for cmd in line.decode('latin1').split(';'):
            argv = cmd.split()
            if not argv:
                continue
            self.commands += 1
            name = argv[0]
            if name not in self.ALLOWED:
                self.violations.append('command %r' % cmd)
                self._print("Unknown command '%s' - try 'help'\n" % name)
                continue
            try:
                args = [int(a, 16) & 0xFFFFFFFF for a in argv[1:]]
            except ValueError:
                self._print('Usage:\n%s\n' % name)
                continue
            if name == 'mw.l':
                if len(args) not in (2, 3):
                    self._print('Usage:\nmw - memory write (fill)\n')
                    continue
                a, v = args[0], args[1]
                n = args[2] if len(args) == 3 else 1
                if a % 4 or a < SAFE_LO or a + 4 * n > SAFE_HI:
                    self.violations.append('stray write %r' % cmd)
                    continue
                for i in range(n):
                    w = v
                    if self.ram_corrupt and self.rng.random() < self.ram_corrupt:
                        w ^= 1 << self.rng.randrange(32)
                    self.ram[a + 4 * i] = w
                self.exec_time += 20e-6 * n
            elif name == 'md.l':
                if len(args) not in (1, 2):
                    self._print('Usage:\nmd - memory display\n')
                    continue
                a = args[0] & ~3
                n = args[1] if len(args) == 2 else 0x40
                for row in range(a, a + 4 * n, 16):
                    ws = [self._word(row + 4 * i) for i in range(min(4, (a + 4 * n - row) // 4))]
                    asc = ''.join(chr(b) if 32 <= b < 127 else '.'
                                  for b in struct.pack('<%dI' % len(ws), *ws))
                    self._print('%08x:%s    %s\n' % (row, ''.join(' %08x' % w for w in ws), asc))
            elif name == 'crc32':
                if len(args) != 2:            # store form never expected here
                    self.violations.append('crc32 form %r' % cmd)
                    continue
                a, n = args
                data = b''.join(struct.pack('<I', self._word(x))
                                for x in range(a & ~3, a + n, 4))[a & 3:(a & 3) + n]
                self._print('CRC32 for %08x ... %08x ==> %08x\n'
                            % (a, a + n - 1, zlib.crc32(data) & 0xFFFFFFFF))
                self.exec_time += n / 50e6

    def read_mem(self, addr, n):
        return b''.join(struct.pack('<I', self._word(a)) for a in range(addr, addr + n, 4))


class FakeLink:
    """Connects the uploader to FakeUBoot with a virtual clock and fault
    injection: tx_drop / tx_corrupt act on PC->board bytes, rx_drop on
    board->PC bytes. The clock charges wire time at 115200 8N1, one USB
    turnaround (latency) per write->read, and U-Boot's execution time."""

    def __init__(self, uboot, tx_drop=0.0, tx_corrupt=0.0, rx_drop=0.0,
                 latency=0.004, seed=1):
        self.u = uboot
        self.tx_drop, self.tx_corrupt, self.rx_drop = tx_drop, tx_corrupt, rx_drop
        self.latency = latency
        self.rng = random.Random(seed)
        self.t = 0.0
        self.turn = False
        self.tx_bytes = self.rx_bytes = 0
        self.sent = bytearray()          # everything the PC sent, for auditing

    def write(self, data):
        self.sent.extend(data)
        self.tx_bytes += len(data)
        self.t += len(data) * CHAR_T
        out = bytearray()
        for c in data:
            r = self.rng.random()
            if r < self.tx_drop:
                continue
            if r < self.tx_drop + self.tx_corrupt:
                c ^= 1 << self.rng.randrange(7)
            out.append(c)
        before = len(self.u.out)
        echo_len = len(out)
        e0 = self.u.exec_time
        self.u.feed(bytes(out))
        extra = len(self.u.out) - before - echo_len   # output beyond the echo
        self.t += max(0, extra) * CHAR_T + (self.u.exec_time - e0)
        self.turn = True

    def read(self, timeout):
        if self.u.out:
            if self.turn:
                self.t += self.latency
                self.turn = False
            d = bytes(b for b in self.u.out if self.rng.random() >= self.rx_drop)
            self.u.out.clear()
            self.rx_bytes += len(d)
            return d
        self.t += timeout
        return b''

    def now(self):
        return self.t

    def close(self):
        pass


# ---------------------------------------------------------------------------

CRC_RE = re.compile(rb'CRC32 for ([0-9a-f]{8}) \.\.\. ([0-9a-f]{8}) ==> ([0-9a-f]{8})')
MD_RE = re.compile(rb'^([0-9a-f]{8}):((?: [0-9a-f]{8}){1,4})', re.M)


class Console:
    def __init__(self, link, window=0, verbose=False, max_line=480):
        self.link = link
        self.max_line = self.line_cap = max_line
        self.good = self.fails = 0
        self.window = window          # 0 = no limit on un-echoed characters
        self.verbose = verbose
        self.aborts = 0
        self.lines = 0
        self.recent = []              # 1 = aborted, 0 = ok (last 20 lines)

    def _drain(self, quiet=0.03):
        buf = b''
        while True:
            d = self.link.read(quiet)
            if not d:
                return buf
            buf += d

    def sync(self, tries=8):
        """^C, then wait for the '# ' prompt followed by a quiet gap."""
        for _ in range(tries):
            self.link.write(b'\x03')
            buf = b''
            end = self.link.now() + 0.5
            while self.link.now() < end:
                # Leftover echo of the aborted line may still be arriving;
                # done when the buffer ends in the prompt and stays quiet.
                d = self.link.read(0.03)
                buf += d
                if buf.endswith(b'# ') and not d:
                    return
            if buf.endswith(b'> '):
                raise UploadError('U-Boot is in the hush PS2 ("> ") prompt; '
                                  'clear it by hand')
        raise UploadError('no U-Boot "# " prompt after ^C (got %r)' % buf[-60:])

    def _type(self, data):
        """Phase 1: type without terminator, demand an exact echo."""
        sent, echo = 0, b''
        last = self.link.now()
        while len(echo) < len(data):
            while sent < len(data) and (not self.window or sent - len(echo) < self.window):
                n = len(data) - sent
                if self.window:
                    n = min(n, self.window - (sent - len(echo)))
                self.link.write(data[sent:sent + n])
                sent += n
            d = self.link.read(0.02)
            if d:
                echo += d
                last = self.link.now()
                if not data.startswith(echo):
                    return False
            elif self.link.now() - last > 0.15 + (sent - len(echo)) * CHAR_T:
                return False
        return True

    def command(self, line, timeout=0.5, tries=12):
        """Type a line, verify the echo, run it, return its output text."""
        data = line.encode('ascii')
        if len(data) > MAX_LINE_HW - 9:
            raise UploadError('line too long')
        for attempt in range(tries):
            self.lines += 1
            ok = self._type(data)
            if ok:
                self.link.write(b'\r')
                resp = b''
                end = self.link.now() + timeout
                while self.link.now() < end:
                    d = self.link.read(0.02)
                    resp += d
                    # The prompt is the last thing U-Boot prints, so no quiet
                    # gap is needed (one would cost ~20 ms a line).
                    if resp.lstrip(b'\r').startswith(b'\n') and resp.endswith(b'\n# '):
                        self._note(0)
                        return resp.lstrip(b'\r')[1:-2].replace(b'\r', b'')
                if resp.endswith(b'> '):
                    raise UploadError('unexpected PS2 prompt after %r' % line[:40])
            self._note(1)
            self.aborts += 1
            if self.verbose:
                print('  line retry %d: %s...' % (attempt + 1, line[:40]))
            self.sync()
        raise LineFailed('line failed %d times: %s...' % (tries, line[:60]))

    def send_tokens(self, toks):
        """Pack ';'-chained commands into lines of at most self.max_line
        characters and run them. A line that keeps failing its echo check is
        repacked shorter (halving down to MIN_LINE); after 50 clean lines the
        length grows back towards the cap."""
        i = 0
        while i < len(toks):
            line, j = toks[i], i + 1
            while j < len(toks) and len(line) + 1 + len(toks[j]) <= self.max_line:
                line += ';' + toks[j]
                j += 1
            try:
                out = self.command(line, tries=3)
            except LineFailed:
                self.fails += 1
                if self.fails > 40:
                    raise UploadError('console too unreliable: 40 lines failed in a row')
                if self.max_line > MIN_LINE:
                    self.max_line = max(MIN_LINE, self.max_line // 2)
                    if self.verbose:
                        print('  repeated echo errors: lines now <= %d chars' % self.max_line)
                self.good = 0
                continue
            self.fails = 0
            if out.strip():
                # mw.l prints nothing. Output means a line split in transit
                # ran something else (e.g. a 'base' suffix): stop for a human.
                raise UploadError('unexpected output after a write line, stopping: %r' % out[:80])
            self.good += 1
            if self.good >= 50 and self.max_line < self.line_cap:
                self.max_line = min(self.line_cap, self.max_line + self.max_line // 4)
                self.good = 0
            i = j

    def _note(self, bad):
        # Only bookkeeping. The window is NOT shrunk automatically: every
        # window costs one USB turnaround, so --window 16 is ~3x slower and is
        # worth it only if the log shows drops that look like FIFO overrun
        # (runs of missing characters) rather than isolated ones.
        self.recent = (self.recent + [bad])[-20:]

    def crc32(self, addr, length):
        """Return U-Boot's crc32 of [addr, addr+length), or None."""
        for _ in range(3):
            out = self.command('crc32 %x %x' % (addr, length),
                               timeout=1.0 + length / 2e6)
            m = CRC_RE.search(out)
            if m and int(m.group(1), 16) == addr and int(m.group(2), 16) == addr + length - 1:
                return int(m.group(3), 16)
        return None

    def md(self, addr, nwords):
        """Read words back; missing/garbled rows are left out of the dict."""
        out = self.command('md.l %x %x' % (addr, nwords), timeout=1.0 + nwords * 20 * CHAR_T)
        words = {}
        for m in MD_RE.finditer(out):
            a = int(m.group(1), 16)
            for i, w in enumerate(m.group(2).split()):
                words[a + 4 * i] = int(w, 16)
        return words


def mw_tokens(addr, words):
    """mw.l commands for consecutive words, using the count form for runs."""
    toks, i = [], 0
    while i < len(words):
        j = i
        while j + 1 < len(words) and words[j + 1] == words[i]:
            j += 1
        n = j - i + 1
        a = addr + 4 * i
        single = 'mw.l %x %x' % (a, words[i])
        run = '%s %x' % (single, n)
        if n >= 2 and len(run) < (len(single) + 1) * n:
            toks.append(run)
            i = j + 1
        else:
            toks.append(single)
            i += 1
    return toks


def pack_lines(toks, max_line):
    lines, cur = [], ''
    for t in toks:
        if cur and len(cur) + 1 + len(t) > max_line:
            lines.append(cur)
            cur = t
        else:
            cur = t if not cur else cur + ';' + t
    if cur:
        lines.append(cur)
    return lines


def uimage_info(data):
    if len(data) < 64 or struct.unpack('>I', data[:4])[0] != UIMAGE_MAGIC:
        return None
    (magic, hcrc, tstamp, size, load, ep, dcrc, os_, arch, typ, comp
     ) = struct.unpack('>7I4B', data[:32])
    name = data[32:64].split(b'\0')[0].decode('latin1')
    hdr = bytearray(data[:64])
    hdr[4:8] = b'\0\0\0\0'
    return dict(hcrc_ok=zlib.crc32(bytes(hdr)) & 0xFFFFFFFF == hcrc,
                dcrc_ok=zlib.crc32(data[64:64 + size]) & 0xFFFFFFFF == dcrc,
                size=size, load=load, ep=ep, comp=comp, arch=arch, name=name,
                complete=len(data) >= 64 + size)


def fmt_t(s):
    s = int(s + 0.5)
    return '%d:%02d:%02d' % (s // 3600, s // 60 % 60, s % 60)


def upload(con, data, addr, chunk=4096, max_line=480, quiet=False):
    """Write data (padded to words) to RAM at addr and verify it. Returns stats."""
    pad = (-len(data)) % 4
    img = data + b'\0' * pad
    check_window(addr, len(img))
    if chunk % 4 or chunk <= 0:
        raise UploadError('--chunk must be a positive multiple of 4')
    words = list(struct.unpack('<%dI' % (len(img) // 4), img))
    link = con.link
    t0 = link.now()
    st = dict(chunk_retries=0, md_repairs=0, words_repaired=0)
    con.max_line = con.line_cap = max_line
    con.sync()
    for off in range(0, len(img), chunk):
        cw = words[off // 4:(off + chunk) // 4]
        caddr = addr + off
        want = zlib.crc32(img[off:off + chunk]) & 0xFFFFFFFF
        for attempt in range(4):
            if attempt == 0 or attempt >= 2:
                con.send_tokens(mw_tokens(caddr, cw))
            got = con.crc32(caddr, len(cw) * 4)
            if got == want:
                break
            st['chunk_retries'] += 1
            if attempt == 0:
                # Read back, rewrite only words that differ or did not parse.
                rb = con.md(caddr, len(cw))
                bad = [i for i, w in enumerate(cw) if rb.get(caddr + 4 * i) != w]
                st['md_repairs'] += 1
                st['words_repaired'] += len(bad)
                toks = []
                for i in bad:
                    toks.append('mw.l %x %x' % (caddr + 4 * i, cw[i]))
                con.send_tokens(toks)
            if not quiet:
                print('  chunk 0x%08x crc mismatch (got %s want %08x), attempt %d'
                      % (caddr, '%08x' % got if got is not None else 'none', want, attempt + 1))
        else:
            raise UploadError('chunk at 0x%08x would not verify' % caddr)
        done = off + len(cw) * 4
        el = link.now() - t0
        if not quiet:
            rate = done / el if el else 0
            eta = (len(img) - done) / rate if rate else 0
            sys.stdout.write('\r[%5.1f%%] 0x%08x  %d/%d B  %.2f KB/s  elapsed %s  ETA %s  '
                             'aborted lines %d  ' % (100.0 * done / len(img), caddr + len(cw) * 4,
                                                    done, len(img), rate / 1024, fmt_t(el),
                                                    fmt_t(eta), con.aborts))
            sys.stdout.flush()
    if not quiet:
        print()
    want = zlib.crc32(img) & 0xFFFFFFFF
    got = con.crc32(addr, len(img))
    if got != want:
        raise UploadError('final crc32 mismatch: U-Boot %s, local %08x'
                          % ('%08x' % got if got is not None else 'none', want))
    el = link.now() - t0
    st.update(bytes=len(img), seconds=el, crc=want, lines=con.lines, aborts=con.aborts)
    return st


def selftest():
    ok = True
    rng = random.Random(1234)

    def check(name, cond):
        nonlocal ok
        print('  %-58s %s' % (name, 'ok' if cond else 'FAIL'))
        ok = ok and cond

    # Window refusals
    for a, n in ((0x00400000, 16), (0x18000000, 16), (SAFE_HI - 8, 16), (0x02000002, 16)):
        try:
            check_window(a, n)
            check('refuse 0x%08x len %d' % (a, n), False)
        except UploadError:
            check('refuse 0x%08x len %d' % (a, n), True)

    cases = [
        ('64 KB random, clean link', rng.randbytes(65536), {}, 0.0),
        ('64 KB random, tx drop 0.3%% corrupt 0.05%%, rx drop 0.1%%',
         rng.randbytes(65536), dict(tx_drop=0.003, tx_corrupt=0.0005, rx_drop=0.001), 0.0),
        ('64 KB random + silent RAM bit flips 0.05%%, tx drop 0.2%%',
         rng.randbytes(65536), dict(tx_drop=0.002), 0.0005),
        ('odd length 4093 B with zero runs, tx drop 0.5%%',
         rng.randbytes(1000) + b'\0' * 2000 + rng.randbytes(1093), dict(tx_drop=0.005), 0.0),
    ]
    addr = 0x02000000
    for name, data, faults, ramc in cases:
        name = name.replace('%%', '%')
        print(name)
        u = FakeUBoot(ram_corrupt=ramc, rng=random.Random(7))
        link = FakeLink(u, seed=rng.randrange(1 << 30), **faults)
        con = Console(link)
        try:
            st = upload(con, data, addr, quiet=True)
        except UploadError as e:
            check('upload finished (%s)' % e, False)
            continue
        u.ram_corrupt = 0
        img = data + b'\0' * ((-len(data)) % 4)
        check('RAM == file (%d B, crc %08x)' % (len(img), st['crc']),
              u.read_mem(addr, len(img)) == img)
        check('no stray writes / forbidden commands', not u.violations)
        check('no empty line executed, nothing repeated', u.empty_lines == 0 and u.repeats == 0)
        # Audit what was actually submitted: text ended by CR (text ended by
        # ^C is thrown away by U-Boot's readline).
        sent_cmds, aborted = set(), 0
        for m in re.finditer(rb'([^\r\x03]*)([\r\x03])', bytes(link.sent)):
            if m.group(2) == b'\x03':
                aborted += bool(m.group(1))
                continue
            for c in m.group(1).split(b';'):
                if c.split():
                    sent_cmds.add(c.split()[0])
        check('only mw.l/md.l/crc32 submitted (%s; %d partial lines ^C-ed)'
              % (b','.join(sorted(sent_cmds)).decode(), aborted),
              sent_cmds <= {b'mw.l', b'md.l', b'crc32'})
        print('    lines %d, aborted+retyped %d, chunk retries %d, md repairs %d (%d words), '
              'tx %d B rx %d B, modelled %.1f s @4 ms latency'
              % (st['lines'], st['aborts'], st['chunk_retries'], st['md_repairs'],
                 st['words_repaired'], link.tx_bytes, link.rx_bytes, st['seconds']))
    # --check style handshake on the fake: ^C + md.l, never an empty line.
    u = FakeUBoot()
    link = FakeLink(u)
    con = Console(link)
    con.command('mw.l 2000000 1')
    check_prompt(con)
    check('check: ^C + md.l, no empty line sent', u.repeats == 0 and u.empty_lines == 0)
    print('modelled clean-link rate for random data at 115200 8N1:')
    for lat in (0.001, 0.004, 0.016):
        r = estimate(rng.randbytes(65536), addr, lat)
        print('  USB turnaround %2d ms: %6.1f KB/min  (%.2f KB/s, 4 MB in %s)'
              % (lat * 1000, r * 60 / 1024, r / 1024, fmt_t(4 * 1024 * 1024 / r)))
    print('SELFTEST', 'PASSED' if ok else 'FAILED')
    return 0 if ok else 1


def estimate(data, addr, latency, chunk=4096, max_line=480, window=0):
    u = FakeUBoot()
    link = FakeLink(u, latency=latency)
    st = upload(Console(link, window=window), data, addr, chunk, max_line, quiet=True)
    return st['bytes'] / st['seconds']


def check_prompt(con, addr=SAFE_LO):
    """^C (clears the repeat flag), then a 1-word md.l to prove it is U-Boot
    and not the Linux shell (whose prompt is also '# '). No bare CR is sent."""
    con.sync()
    out = con.command('md.l %x 1' % addr)
    if not re.search(rb'^%08x: [0-9a-f]{8}' % addr, out, re.M):
        raise UploadError('prompt is there but md.l output is not U-Boot\'s: %r' % out[:80])
    return out.decode('latin1').strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('port', nargs='?')
    ap.add_argument('file', nargs='?')
    ap.add_argument('loadaddr', nargs='?', type=lambda s: int(s, 16))
    ap.add_argument('--chunk', type=lambda s: int(s, 0), default=4096,
                    help='bytes per crc32-verified chunk (default 4096)')
    ap.add_argument('--line', type=int, default=480, help='max characters per line (<=500)')
    ap.add_argument('--window', type=int, default=0,
                    help='max un-echoed characters in flight (0 = whole line; '
                         '16 = can never overrun a 16-byte FIFO)')
    ap.add_argument('--dry-run', action='store_true',
                    help='run against the fake only and print the time estimate')
    ap.add_argument('--fake', action='store_true', help='use the built-in fake U-Boot')
    ap.add_argument('--fake-drop', type=float, default=0.002)
    ap.add_argument('--check', action='store_true', help='only confirm the U-Boot prompt')
    ap.add_argument('--addr', type=lambda s: int(s, 16), default=SAFE_LO,
                    help='address for the --check md.l (default %x)' % SAFE_LO)
    ap.add_argument('--log', help='save the raw serial transcript here')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('-v', '--verbose', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.line > 500 or a.line < 40:
        ap.error('--line must be 40..500')
    if a.check:
        if not a.port:
            ap.error('COMPORT required')
        check_window(a.addr, 4)
        link = FakeLink(FakeUBoot()) if a.fake else SerialLink(a.port, a.log)
        try:
            print('U-Boot prompt OK:', check_prompt(Console(link), a.addr))
        finally:
            link.close()
        return 0
    if a.fake and a.loadaddr is None:      # --fake FILE LOADADDR
        a.port, a.file, a.loadaddr = None, a.port, int(a.file, 16) if a.file else None
    if not a.file or a.loadaddr is None:
        ap.error('need COMPORT FILE LOADADDR')
    data = open(a.file, 'rb').read()
    padded = len(data) + (-len(data)) % 4
    check_window(a.loadaddr, padded)       # refuse before touching any port
    info = uimage_info(data)
    print('%s: %d bytes (%d padded) -> 0x%08x..0x%08x, crc32 %08x'
          % (a.file, len(data), padded, a.loadaddr, a.loadaddr + padded,
             zlib.crc32(data + b'\0' * (padded - len(data))) & 0xFFFFFFFF))
    if info:
        print('uImage "%s": size %d load 0x%x ep 0x%x comp %d, header crc %s, data crc %s'
              % (info['name'], info['size'], info['load'], info['ep'], info['comp'],
                 'ok' if info['hcrc_ok'] else 'BAD', 'ok' if info['dcrc_ok'] else 'BAD'))
        if not (info['hcrc_ok'] and info['dcrc_ok'] and info['complete']):
            raise UploadError('uImage header/data CRC bad or file truncated: refusing')
        if info['arch'] != 2 or info['comp'] not in (0, 1):
            raise UploadError('uImage arch %d comp %d: expected ARM (2), none/gzip'
                              % (info['arch'], info['comp']))
        if info['comp'] == 0 and info['load'] + info['size'] > a.loadaddr:
            raise UploadError('bootm would copy the kernel to 0x%x..0x%x, overlapping the '
                              'upload buffer' % (info['load'], info['load'] + info['size']))
    if a.dry_run:
        for lat in (0.001, 0.004, 0.016):
            u = FakeUBoot()
            st = upload(Console(FakeLink(u, latency=lat), window=a.window), data,
                        a.loadaddr, a.chunk, a.line, quiet=True)
            print('dry run, %2d ms USB turnaround: %d lines, %s (%.1f KB/min)'
                  % (lat * 1000, st['lines'], fmt_t(st['seconds']),
                     st['bytes'] / st['seconds'] * 60 / 1024))
        return 0
    if a.fake:
        link = FakeLink(FakeUBoot(), tx_drop=a.fake_drop, rx_drop=a.fake_drop / 2)
    else:
        link = SerialLink(a.port, a.log)
    try:
        con = Console(link, window=a.window, verbose=a.verbose)
        print('prompt:', check_prompt(con, a.loadaddr))
        st = upload(con, data, a.loadaddr, a.chunk, a.line)
    finally:
        link.close()
    print('done: %d bytes in %s (%.1f KB/min), %d lines, %d retyped, %d chunk retries'
          % (st['bytes'], fmt_t(st['seconds']), st['bytes'] / st['seconds'] * 60 / 1024,
             st['lines'], st['aborts'], st['chunk_retries']))
    print('verified: crc32 %x %x ==> %08x' % (a.loadaddr, st['bytes'], st['crc']))
    print('nothing was booted. Next steps are typed by hand (e.g. bootm %x).' % a.loadaddr)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except UploadError as e:
        sys.exit('error: %s' % e)
