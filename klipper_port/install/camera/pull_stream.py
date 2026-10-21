"""Act as a webcam viewer: pull an MJPEG stream for N seconds, report frames/s and kB/s.
usage: pull_stream.py URL SECONDS"""
import sys, time, urllib.request
url, secs = sys.argv[1], float(sys.argv[2])
t0 = time.time(); n = 0; nbytes = 0; buf = b''
with urllib.request.urlopen(url, timeout=10) as r:
    while time.time() - t0 < secs:
        d = r.read(65536)
        if not d:
            break
        nbytes += len(d)
        buf = buf[-3:] + d
        n += d.count(b'\xff\xd8\xff')       # JPEG start-of-image markers
dt = time.time() - t0
print('client: %d frames in %.1f s = %.1f fps, %.0f kB/s' % (n, dt, n / dt, nbytes / dt / 1024))
