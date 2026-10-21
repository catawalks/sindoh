"""Simulate Mainsail's 'mjpegstreamer-adaptive' webcam mode: request snapshots at a
target rate and report failures, slow answers and size outliers (truncated frames).
usage: snapshot_hammer.py URL SECONDS [rate_hz=15]"""
import sys, time, urllib.request, statistics
url, secs = sys.argv[1], float(sys.argv[2])
rate = float(sys.argv[3]) if len(sys.argv) > 3 else 15.0
t_end = time.time() + secs
sizes, lat, fails, bad = [], [], [], 0
while time.time() < t_end:
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            d = r.read()
        dt = time.time() - t0
        lat.append(dt)
        sizes.append(len(d))
        if not (d[:2] == b'\xff\xd8' and b'\xff\xd9' in d[-64:]):
            bad += 1
    except Exception as e:
        fails.append('%.1fs %s' % (time.time() - t0, type(e).__name__))
    time.sleep(max(0.0, 1.0 / rate - (time.time() - t0)))
n = len(sizes)
print('requests ok=%d failed=%d incomplete_jpeg=%d' % (n, len(fails), bad))
if n:
    lat.sort()
    print('latency ms: median %.0f  p95 %.0f  max %.0f' % (1000 * statistics.median(lat), 1000 * lat[int(0.95 * (n - 1))], 1000 * lat[-1]))
    print('size bytes: min %d median %d max %d' % (min(sizes), statistics.median(sizes), max(sizes)))
    small = [s for s in sizes if s < 0.5 * statistics.median(sizes)]
    print('frames < 50%% of median size: %d' % len(small))
for f in fails[:5]:
    print('  fail:', f)
