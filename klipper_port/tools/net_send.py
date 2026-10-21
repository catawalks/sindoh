"""Send a file to the DP200 over TCP (printer side: busybox 'nc -l -p PORT > FILE').
The PC connects out to the printer, so no inbound firewall rule is needed.
usage: net_send.py PRINTER_IP PORT FILE"""
import hashlib, socket, sys, time
ip, port, path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
data = open(path, 'rb').read()
for attempt in range(20):
    try:
        s = socket.create_connection((ip, port), timeout=5)
        break
    except OSError:
        time.sleep(0.5)
else:
    sys.exit('could not connect to %s:%d' % (ip, port))
t0 = time.time()
s.sendall(data)
s.shutdown(socket.SHUT_WR)
s.close()
print('%s: %d bytes in %.2fs, sha256 %s' % (path, len(data), time.time() - t0,
                                           hashlib.sha256(data).hexdigest()))
