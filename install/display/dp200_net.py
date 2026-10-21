#!/usr/bin/python3
"""Network information and settings for the DP200 touch screen.

Reads the state of the WiFi (mlan0) and Ethernet (eth0) ports from inside
the Klipper chroot (/sys, /proc, `ip`) and stores per-port settings in
/etc/dp200/network.json. Applying them is done on the stock side by
dp200-netd.sh: we write the file and touch /run/dp200/net-apply.

    dp200_net.py            print both ports"""
import fcntl, json, os, socket, struct

CONF = '/etc/dp200/network.json'
TRIGGER = '/run/dp200/net-apply'
PORTS = (('mlan0', 'WiFi'), ('eth0', 'Ethernet'))

def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ''

def prefix_to_mask(n):
    m = (0xffffffff << (32 - n)) & 0xffffffff if n else 0
    return '.'.join(str(m >> s & 255) for s in (24, 16, 8, 0))

def valid_ip(s):
    p = s.split('.')
    return len(p) == 4 and all(x.isdigit() and len(x) <= 3 and int(x) <= 255 for x in p)

def valid_mask(s):
    if not valid_ip(s):
        return False
    n = 0
    for x in s.split('.'):
        n = n << 8 | int(x)
    inv = ~n & 0xffffffff
    return n != 0 and inv & (inv + 1) == 0           # contiguous ones

def gateway(iface):
    for line in _read('/proc/net/route').splitlines()[1:]:
        p = line.split()
        if len(p) > 3 and p[0] == iface and p[1] == '00000000' and int(p[3], 16) & 2:
            g = int(p[2], 16)
            return '.'.join(str(g >> s & 255) for s in (0, 8, 16, 24))
    return ''

def dns():
    return [l.split()[1] for l in _read('/etc/resolv.conf').splitlines()
            if l.startswith('nameserver') and len(l.split()) > 1]

def info(iface):
    """-> dict: mac, link (bool), up, ip, mask, gw, mode"""
    d = {'mac': _read('/sys/class/net/%s/address' % iface),
         'link': _read('/sys/class/net/%s/carrier' % iface) == '1',
         'up': _read('/sys/class/net/%s/operstate' % iface) == 'up',
         'ip': '', 'mask': '', 'gw': gateway(iface),
         'mode': load().get(iface, {}).get('mode', 'dhcp'),
         'present': os.path.isdir('/sys/class/net/%s' % iface)}
    # classic ioctls: Debian's `ip ... dev X` needs netlink features kernel 3.2 lacks
    d['ip'] = _ioctl_addr(iface, 0x8915)               # SIOCGIFADDR
    d['mask'] = _ioctl_addr(iface, 0x891b) if d['ip'] else ''   # SIOCGIFNETMASK
    return d

def _ioctl_addr(iface, req):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        r = fcntl.ioctl(s.fileno(), req, struct.pack('256s', iface.encode()[:15]))
        return socket.inet_ntoa(r[20:24])
    except OSError:
        return ''                                       # no IPv4 address
    finally:
        s.close()

def load():
    try:
        with open(CONF) as f:
            c = json.load(f)
        return c if isinstance(c, dict) else {}
    except (OSError, ValueError):
        return {}

def save(conf):
    """Write the settings (compact JSON: dp200-netd.sh parses it with sed)
    and ask dp200-netd.sh to apply them."""
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    tmp = CONF + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(conf, f, separators=(',', ':'))
    os.replace(tmp, CONF)
    os.makedirs(os.path.dirname(TRIGGER), exist_ok=True)
    open(TRIGGER, 'w').close()

def check_static(c):
    """-> error text or None"""
    if not valid_ip(c.get('ip', '')):
        return 'IP address is not valid'
    if not valid_mask(c.get('mask', '')):
        return 'Netmask is not valid'
    for k, name in (('gw', 'Gateway'), ('dns', 'DNS')):
        if c.get(k) and not valid_ip(c[k]):
            return '%s is not valid' % name
    return None

if __name__ == '__main__':
    for iface, name in PORTS:
        print(name, info(iface))
    print('dns', dns())
