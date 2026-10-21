"""Push files to the DP200 over its serial console (BusyBox uudecode, base64).
usage: serial_push.py COMPORT DEST_DIR file [file...]

The console occasionally drops input characters, so each file is sent in
small chunks; every chunk is checked with md5sum on the printer and resent
until it matches, then the chunks are joined and the whole file is checked
with sha256sum."""
import base64, hashlib, os, sys, time
import serial

CHUNK = 1536
port, dest = sys.argv[1], sys.argv[2]
files = sys.argv[3:]
s = serial.Serial(port, 115200, timeout=0.2)

def cmd(line, wait=1.0, until=None):
    s.read(65536)
    s.write(line.encode() + b'\r')
    buf = b''
    end = time.time() + wait
    while time.time() < end:
        buf += s.read(4096)
        if until and until.encode() in buf:
            break
    return buf.decode(errors='replace')

def send_chunk(path, data):
    b64 = base64.b64encode(data).decode()
    s.write(("cat > %s.uu << 'EOF_DP'\r" % path).encode())
    s.write(('begin-base64 644 %s\r' % path).encode())
    for i in range(0, len(b64), 76):
        s.write(b64[i:i + 76].encode() + b'\r')
        if (i // 76) % 8 == 7:
            s.flush(); time.sleep(0.05)
    s.write(b'====\rEOF_DP\r')
    s.flush(); time.sleep(0.3)
    out = cmd('uudecode -o %s %s.uu 2>&1; rm -f %s.uu; md5sum %s' % (path, path, path, path),
              3, '  ' + path)
    return hashlib.md5(data).hexdigest() in out

cmd('')
cmd('mkdir -p %s' % dest, 1)
cmd('stty -echo', 1)
for src in files:
    name = os.path.basename(src)
    data = open(src, 'rb').read()
    t0 = time.time()
    parts = []
    retries = 0
    for n, off in enumerate(range(0, len(data), CHUNK)):
        part = '%s/.%s.part%03d' % (dest, name, n)
        for attempt in range(8):
            if send_chunk(part, data[off:off + CHUNK]):
                break
            retries += 1
        else:
            sys.exit('chunk %d of %s failed repeatedly' % (n, name))
        parts.append(part)
    cmd('cat %s > %s/%s && rm -f %s && chmod 755 %s/%s'
        % (' '.join(parts), dest, name, ' '.join(parts), dest, name), 3)
    out = cmd('sha256sum %s/%s' % (dest, name), 3, name)
    ok = hashlib.sha256(data).hexdigest() in out
    print('%-16s %6d bytes  %5.1fs  %d chunk retries  %s'
          % (name, len(data), time.time() - t0, retries, 'OK' if ok else 'HASH MISMATCH'))
cmd('stty echo', 1)
print(cmd('ls -l %s' % dest, 2))
s.close()
