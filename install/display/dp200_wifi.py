#!/usr/bin/python3
"""WiFi client control for the DP200 in Klipper mode.

The stock boot starts wpa_supplicant (wext, control socket in
/var/run/wpa_supplicant, bind-mounted into the chroot by dp200-start.sh) with
a placeholder config. Restarting wpa_supplicant leaves the Marvell driver
unable to scan for a while, so it is never restarted: our saved networks are
loaded into the running daemon over the control socket instead.

Saved networks: /etc/dp200/wpa_supplicant.conf (wpa_supplicant syntax,
created from the stock firmware's saved networks by dp200-wifi.sh). This
module rewrites that file itself; it never calls SAVE_CONFIG (that would
write the stock /etc/wpa_supplicant.conf on NAND).

    dp200_wifi.py apply          load saved networks into wpa_supplicant (boot)
    dp200_wifi.py status | scan  print state / visible networks
Used as a module by dp200_screen.py (scan/connect/forget)."""
import os, re, socket, sys, time

CONF = '/etc/dp200/wpa_supplicant.conf'
CTRL = '/var/run/wpa_supplicant/mlan0'
HEADER = ('# Saved WiFi networks (dp200_wifi.py / the touch screen).\n'
          'ctrl_interface=/var/run/wpa_supplicant\n')

class WpaError(Exception):
    pass

class WpaCtrl:
    """wpa_supplicant control-socket client. The client socket lives in the
    abstract namespace, so the daemon (outside the chroot) can reply."""
    def __init__(self, path=CTRL):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.s.bind('\0dp200-wifi-%d-%d' % (os.getpid(), id(self) & 0xffff))
        self.s.settimeout(3)
        try:
            self.s.connect(path)
        except OSError as e:
            self.s.close()
            raise WpaError('wpa_supplicant not reachable (%s)' % e.strerror)

    def close(self):
        self.s.close()

    def cmd(self, c):
        self.s.send(c.encode())
        while True:
            try:
                r = self.s.recv(8192).decode('utf-8', 'replace')
            except socket.timeout:
                raise WpaError('no answer to %s' % c.split()[0])
            if not r.startswith('<'):          # skip unsolicited event messages
                return r

    def ok(self, c):
        r = self.cmd(c).strip()
        if r != 'OK':
            raise WpaError('%s -> %s' % (c.split()[0], r))

# ---------------------------------------------------------------------------
# saved networks (our own config file)
# ---------------------------------------------------------------------------
def _unquote(v):
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] == '"' else v

def load_saved(path=CONF):
    """-> list of {'ssid': bytes, 'psk': str|None, 'priority': int}"""
    nets, cur = [], None
    try:
        lines = open(path, encoding='utf-8', errors='replace').read().splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if line.startswith('network={'):
            cur = {'ssid': b'', 'psk': None, 'priority': 0}
        elif line == '}' and cur is not None:
            if cur['ssid']:
                nets.append(cur)
            cur = None
        elif cur is not None and '=' in line:
            k, v = line.split('=', 1)
            if k == 'ssid':
                cur['ssid'] = _unquote(v).encode() if v.startswith('"') else bytes.fromhex(v)
            elif k == 'psk':
                cur['psk'] = _unquote(v)
            elif k == 'priority':
                cur['priority'] = int(v)
    return nets

def write_saved(nets, path=CONF):
    out = [HEADER]
    for n in nets:
        out.append('network={\n\tssid=%s\n' % n['ssid'].hex())
        if n['psk']:
            out.append('\tpsk="%s"\n\tkey_mgmt=WPA-PSK\n' % n['psk'])
        else:
            out.append('\tkey_mgmt=NONE\n')
        out.append('\tpriority=%d\n}\n' % n['priority'])
    tmp = path + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(''.join(out))
    os.replace(tmp, path)

# ---------------------------------------------------------------------------
# daemon state
# ---------------------------------------------------------------------------
def _decode_ssid(s):
    """wpa_supplicant prints SSIDs printf-escaped (\\xNN, \\\\, \\")."""
    out, i = bytearray(), 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            if s[i + 1] == 'x' and i + 3 < len(s):
                out.append(int(s[i + 2:i + 4], 16))
                i += 4
                continue
            out += {'n': b'\n', 'r': b'\r', 't': b'\t', 'e': b'\x1b'}.get(s[i + 1], s[i + 1].encode())
            i += 2
            continue
        out += s[i].encode()
        i += 1
    return bytes(out)

def status(w):
    st = {}
    for line in w.cmd('STATUS').splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            st[k] = v
    if 'ssid' in st:
        st['ssid'] = _decode_ssid(st['ssid'])
    return st

def list_networks(w):
    """-> list of (id, ssid bytes, flags)"""
    nets = []
    for line in w.cmd('LIST_NETWORKS').splitlines()[1:]:
        p = line.split('\t')
        if len(p) >= 2:
            nets.append((int(p[0]), _decode_ssid(p[1]), p[3] if len(p) > 3 else ''))
    return nets

def scan_results(w):
    """-> list of dicts (ssid, level, secured, freq), one per SSID, strongest first"""
    best = {}
    for line in w.cmd('SCAN_RESULTS').splitlines()[1:]:
        p = line.split('\t')
        if len(p) < 5 or not p[4]:
            continue                                   # hidden networks have no SSID
        ssid = _decode_ssid(p[4])
        n = {'ssid': ssid, 'level': int(p[2]), 'freq': int(p[1]),
             'secured': any(k in p[3] for k in ('WPA', 'RSN', 'WEP')),
             'wep': 'WEP' in p[3] and 'WPA' not in p[3]}
        if ssid not in best or n['level'] > best[ssid]['level']:
            best[ssid] = n
    return sorted(best.values(), key=lambda n: -n['level'])

def bars(level):
    return 4 if level > -55 else 3 if level > -65 else 2 if level > -75 else 1

def _add(w, n):
    nid = int(w.cmd('ADD_NETWORK').strip())
    w.ok('SET_NETWORK %d ssid %s' % (nid, n['ssid'].hex()))
    if n['psk']:
        w.ok('SET_NETWORK %d psk "%s"' % (nid, n['psk']))
    else:
        w.ok('SET_NETWORK %d key_mgmt NONE' % nid)
    w.ok('SET_NETWORK %d priority %d' % (nid, n['priority']))
    return nid

def apply(w, nets):
    """Make the daemon's network list match `nets`. The current connection is
    kept if it is one of them."""
    wanted = {n['ssid']: n for n in nets}
    cur = status(w)
    connected = cur.get('wpa_state') == 'COMPLETED' and cur.get('ssid') in wanted
    have = list_networks(w)
    for nid, ssid, flags in have:
        if connected and ssid == cur.get('ssid'):
            # keep the live connection, but give it its saved priority
            w.ok('SET_NETWORK %d priority %d' % (nid, wanted[ssid]['priority']))
        else:
            w.ok('REMOVE_NETWORK %d' % nid)
    present = {ssid for nid, ssid, flags in list_networks(w)}
    for n in nets:
        if n['ssid'] not in present:
            _add(w, n)
    w.ok('ENABLE_NETWORK all')
    if not connected:
        w.ok('REASSOCIATE')

# ---------------------------------------------------------------------------
# touch-screen operations (blocking; call from a worker thread)
# ---------------------------------------------------------------------------
MLANUTL = '/run/mlanutl'      # Marvell's tool, copied from the stock firmware by dp200-start.sh

def scan(w, wait=8.0, fresh=True):
    """fresh=False: just the daemon's latest scan results.
    A standard wpa_supplicant SCAN while connected makes this Marvell driver
    leave the network for ~10 s (about 7 s off-channel, 200 ms per channel).
    The driver's own user scan with a 30 ms dwell takes ~2 s, keeps the
    association, and wpa_supplicant picks up its results (tested 2026-10-22)."""
    if fresh:
        if os.access(MLANUTL, os.X_OK):
            import subprocess
            subprocess.run([MLANUTL, 'mlan0', 'setuserscan', 'keep=1', 'dur=30'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            time.sleep(1)
        else:
            w.cmd('SCAN')
            time.sleep(wait)
    return scan_results(w)

def watchdog(w, state):
    """Call every few seconds. If the radio stays associated without an IP
    address for 60 s, force a re-association (seen after scans: the driver's
    data path stalls until then). `state` is a dict kept by the caller."""
    st = status(w)
    if st.get('wpa_state') == 'COMPLETED' and not st.get('ip_address'):
        since = state.setdefault('no_ip_since', time.time())
        if time.time() - since > 60:
            w.ok('REASSOCIATE')
            state['no_ip_since'] = time.time()
            return 'reassociated'
    else:
        state.pop('no_ip_since', None)
    return None

def connect(w, ssid, psk, timeout=30.0, path=CONF):
    """Join ssid (psk None = open network). On success the network is saved
    with the top priority; on failure the previous configuration is restored.
    -> (ok, message)"""
    if psk is not None and not 8 <= len(psk) <= 63:
        return False, 'Password must be 8-63 characters'
    saved = load_saved(path)
    for nid, s, flags in list_networks(w):
        if s == ssid:
            w.ok('REMOVE_NETWORK %d' % nid)
    top = max([n['priority'] for n in saved] + [0]) + 1
    new = {'ssid': ssid, 'psk': psk, 'priority': top}
    nid = _add(w, new)
    w.ok('SELECT_NETWORK %d' % nid)                    # temporarily disables the others
    t0, ok = time.time(), False
    while time.time() - t0 < timeout:
        st = status(w)
        if st.get('wpa_state') == 'COMPLETED' and st.get('ssid') == ssid:
            ok = True
            break
        time.sleep(1)
    if ok:
        saved = [n for n in saved if n['ssid'] != ssid] + [new]
        write_saved(saved, path)
        w.ok('ENABLE_NETWORK all')
        return True, 'Connected'
    w.ok('REMOVE_NETWORK %d' % nid)
    apply(w, saved)                                    # back to the saved networks
    return False, 'Could not connect - wrong password?' if psk else 'Could not connect'

def forget(w, ssid, path=CONF):
    saved = [n for n in load_saved(path) if n['ssid'] != ssid]
    write_saved(saved, path)
    for nid, s, flags in list_networks(w):
        if s == ssid:
            w.ok('REMOVE_NETWORK %d' % nid)
    w.ok('ENABLE_NETWORK all')
    w.ok('REASSOCIATE')

# ---------------------------------------------------------------------------
def main():
    what = sys.argv[1] if len(sys.argv) > 1 else 'status'
    w = None
    for _ in range(30):                                # wpa_supplicant may still be starting
        try:
            w = WpaCtrl()
            break
        except WpaError:
            time.sleep(1)
    if w is None:
        sys.exit('dp200_wifi: wpa_supplicant not reachable')
    if what == 'apply':
        nets = load_saved()
        apply(w, nets)
        print('dp200_wifi: %d saved network(s) loaded' % len(nets))
    elif what == 'scan':
        for n in scan(w):
            print('%4d dBm %s %s' % (n['level'], 'lock' if n['secured'] else 'open',
                                     n['ssid'].decode('utf-8', 'replace')))
    else:
        st = status(w)
        print('state=%s ssid=%s ip=%s' % (st.get('wpa_state'), st.get('ssid', b'').decode('utf-8', 'replace'),
                                          st.get('ip_address', '')))

if __name__ == '__main__':
    main()
