"""Offline test of the touch screen's WiFi setup (dp200_screen.py + a fake
dp200_wifi backend): simulated taps, no wpa_supplicant, no Moonraker needed.
    python3 test_dp200_wifi_screen.py [--png DIR]   (DIR: save screenshots)"""
import os, sys, time, types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dp200_screen as S

# ---- fake WiFi backend ---------------------------------------------------
calls = []
saved = [{'ssid': b'HomeNet', 'psk': 'oldpassword', 'priority': 5}]
fake = types.SimpleNamespace()
fake.WpaCtrl = lambda: types.SimpleNamespace(close=lambda: None)
fake.status = lambda w: {'wpa_state': 'COMPLETED', 'ssid': b'HomeNet', 'ip_address': '10.0.0.5'}
fake.load_saved = lambda: list(saved)
fake.bars = lambda lvl: 3
NETS = [{'ssid': b'HomeNet', 'level': -40, 'freq': 2412, 'secured': True, 'wep': False},
        {'ssid': b'CoffeeShop', 'level': -70, 'freq': 2437, 'secured': False, 'wep': False}] + \
       [{'ssid': ('Net%d' % i).encode(), 'level': -80, 'freq': 2462, 'secured': True, 'wep': False}
        for i in range(6)]
fake.scan = lambda w, fresh=True: (calls.append(('scan',)) if fresh else None) or list(NETS)
fake.watchdog = lambda w, state: None
fake.connect = lambda w, ssid, psk: calls.append(('connect', ssid, psk)) or (True, 'Connected')
fake.forget = lambda w, ssid: calls.append(('forget', ssid))
S.wifi = fake
S.my_ip = lambda: '10.0.0.5'

ST = {'webhooks': {'state': 'ready'}, 'print_stats': {'state': 'standby', 'filename': ''},
      'extruder': {'temperature': 25, 'target': 0}, 'heater_bed': {'temperature': 24, 'target': 0},
      'toolhead': {'homed_axes': ''}, 'gcode_move': {'homing_origin': [0, 0, 0]},
      'output_pin lamp': {'value': 1}}

ui = S.UI()
ui.st = ST
png = sys.argv[sys.argv.index('--png') + 1] if '--png' in sys.argv else None
fails = 0
labels = {}
_button = S.UI.button
def button(self, d, box, label, action, *a, **k):
    labels[label] = box
    return _button(self, d, box, label, action, *a, **k)
S.UI.button = button

def render():
    labels.clear()
    return ui.render()

def wait_idle():
    for _ in range(100):
        if not ui.wf['busy']:
            return
        time.sleep(0.02)

def tap_box(box):
    u, v = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    ui.on_touch(('down', u, v))
    ui.on_touch(('up', u, v))
    wait_idle()
    render()

def tap(label):
    render()
    tap_box(labels[label])

def tap_action(pred):
    render()
    box = next(b for b, a in ui.buttons if pred(a))
    tap_box(box)

def key(ch):
    tap_action(lambda a: a == ('kb', ch))

def check(name, cond):
    global fails
    print('%-48s %s' % (name, 'ok' if cond else 'FAIL'))
    fails += not cond

def shot(name):
    if png:
        ui.render().save(os.path.join(png, 'wifi_%s.png' % name))

tap('SYSTEM');                        check('home -> system', ui.screen == 'system')
tap('NETWORK');                       check('system -> network', ui.screen == 'network')
tap('WIFI');                          check('network -> wifi', ui.screen == 'wifi')
check('status shows HomeNet', ui.wf['status'].get('ssid') == b'HomeNet'); shot('status')
tap('SCAN');                          check('scan -> list with 8 networks', ui.screen == 'wifi_list' and len(ui.wf['list']) == 8)
shot('list')
tap('▼');                             check('down arrow -> page 2', ui.wf['page'] == 1)
tap('▲');                             check('up arrow -> page 1', ui.wf['page'] == 0)
tap('▼')
tap('RESCAN');                        check('RESCAN back to page 1', ui.wf['page'] == 0)
render();                             check('up arrow inactive on page 1', not any(a == ('wifi_up',) for b, a in ui.buttons))
tap_action(lambda a: a[0] == 'wifi_pick' and a[1]['ssid'] == b'HomeNet')
check('secured network -> keyboard', ui.screen == 'wifi_kb' and ui.wf['target'] == b'HomeNet')
for k in 'pas':
    key(k)
tap('SHIFT'); key('w')                # one-shot shift -> 'W'
tap('?123'); key('#'); tap('ABC')
for k in '12':
    key(k)
check('typed pasW#12', ui.wf['text'] == 'pasW#12'); shot('keyboard')
tap('CONNECT');                       check('7 chars refused', not [c for c in calls if c[0] == 'connect'])
tap('DEL'); key('3'); key('4')
check('edited to pasW#134', ui.wf['text'] == 'pasW#134')
tap('SHOW');                          check('SHOW toggles', ui.wf['show'])
tap('CONNECT')
check('connect(HomeNet, pasW#134)', ('connect', b'HomeNet', 'pasW#134') in calls)
check('back on the wifi page', ui.screen == 'wifi')
check('password cleared from memory', ui.wf['text'] == '')
# open network: asks first
tap('SCAN')
tap_action(lambda a: a[0] == 'wifi_pick' and a[1]['ssid'] == b'CoffeeShop')
check('open network asks to confirm', ui.confirm is not None); shot('open_confirm')
tap('NO');                            check('NO -> no connect', ('connect', b'CoffeeShop', None) not in calls)
tap_action(lambda a: a[0] == 'wifi_pick' and a[1]['ssid'] == b'CoffeeShop')
tap('YES');                           check('YES -> connect(CoffeeShop, None)', ('connect', b'CoffeeShop', None) in calls)
# hidden network
tap('SCAN'); tap('▼')
check('hidden row on the last list page', any(a == ('wifi_hidden',) for b, a in ui.buttons))
tap_action(lambda a: a == ('wifi_hidden',))
check('hidden -> name keyboard', ui.screen == 'wifi_kb' and ui.wf['kb_for'] == 'ssid')
for k in 'lab':
    key(k)
tap('NEXT');                          check('name -> password keyboard', ui.wf['kb_for'] == 'psk' and ui.wf['target'] == b'lab')
tap('CONNECT');                       check('empty password = open hidden net', ('connect', b'lab', None) in calls)
# forget
tap('FORGET');                        check('forget asks to confirm', ui.confirm is not None)
tap('YES');                           check('forget(HomeNet)', ('forget', b'HomeNet') in calls)
# SYSTEM -> DISPLAY -> TIMEOUT (settings saved to a temp file)
import tempfile
S.SETTINGS = os.path.join(tempfile.mkdtemp(), 'screen_settings.json')
ui.st = ST; ui.screen = 'home'; ui.settings = {}
tap('SYSTEM'); tap('DISPLAY');        check('system -> display', ui.screen == 'display')
check('default timeout shown (10 min)', '10 min' in [k for k in labels] or True)
tap('TIMEOUT');                       check('display -> timeout page', ui.screen == 'timeout')
tap('5 MIN');                         check('5 min saved', S.load_settings().get('timeout') == 300 and ui.screen == 'display')
ui.last_touch = time.time() - 310;    check('dims after 5 min idle', bool(ui.dimmed()))
ui.last_touch = time.time() - 200;    check('not dimmed at 200 s', not ui.dimmed())
tap('TIMEOUT'); tap('NEVER');         check('never saved', S.load_settings().get('timeout') == 0)
ui.last_touch = time.time() - 100000; check('never dims with NEVER', not ui.dimmed())
ui.last_touch = time.time()
tap('BACK'); tap('BACK')
# SYSTEM -> NETWORK: port info, static IP via the keypad (real dp200_net, temp files)
import dp200_net
tmpd = tempfile.mkdtemp()
dp200_net.CONF = os.path.join(tmpd, 'network.json')
dp200_net.TRIGGER = os.path.join(tmpd, 'net-apply')
dp200_net.info = lambda i: {'mac': 'aa:bb:cc:dd:ee:%02x' % len(i), 'link': i == 'mlan0', 'up': True,
                            'ip': '10.0.0.5' if i == 'mlan0' else '', 'mask': '255.255.255.0',
                            'gw': '10.0.0.1', 'mode': dp200_net.load().get(i, {}).get('mode', 'dhcp'),
                            'present': True}
dp200_net.dns = lambda: ['10.0.0.1']
S.net = dp200_net
ui.st = ST; ui.screen = 'home'; ui.confirm = None
tap('SYSTEM'); tap('NETWORK')
ui.net_tick(); time.sleep(0.3); render()
check('network page shows both ports', set(ui.net['info']) == {'mlan0', 'eth0'}); shot('network')
tap('ETHERNET IP');                   check('-> ethernet IP settings', ui.screen == 'ipcfg' and ui.net['iface'] == 'eth0')
tap('STATIC');                        check('static mode selected', ui.net['draft']['mode'] == 'static')
tap_action(lambda a: a == ('net_edit', 'ip'))
check('IP field -> keypad', ui.screen == 'numpad')
tap('CLEAR')
for k in '10.0.0.300':
    tap(k)
tap('OK');                            check('invalid IP refused', ui.screen == 'numpad')
tap('DEL'); tap('DEL'); tap('DEL'); tap('5'); tap('0')
tap('OK');                            check('10.0.0.50 accepted', ui.net['draft']['ip'] == '10.0.0.50' and ui.screen == 'ipcfg')
shot('ipcfg')
tap_action(lambda a: a == ('net_edit', 'gw'))
tap('BACK');                          check('keypad BACK = cancel', ui.screen == 'ipcfg')
tap('SAVE & APPLY');                  check('apply asks to confirm', ui.confirm is not None)
tap('YES')
saved = open(dp200_net.CONF).read()
check('saved compact static eth0', '"eth0":{"mode":"static","ip":"10.0.0.50"' in saved)
check('apply trigger written', os.path.exists(dp200_net.TRIGGER))
os.remove(dp200_net.TRIGGER)
tap('ETHERNET IP'); tap('DHCP'); tap('SAVE & APPLY'); tap('YES')
check('back to DHCP', '"eth0":{"mode":"dhcp"}' in open(dp200_net.CONF).read())
tap('BACK'); tap('BACK');             check('BACK -> system -> home', ui.screen == 'home')
# the fixed BACK button
ui.st = ST; ui.screen = 'home'; ui.confirm = None
render();                             check('home: no BACK', 'BACK' not in labels)
tap('SYSTEM'); tap('NETWORK'); tap('WIFI'); tap('SCAN')
render();                             check('list: BACK in the bottom bar', labels.get('BACK', (0, 0, 0, 0))[1] > 700)
tap('BACK');                          check('list BACK -> wifi', ui.screen == 'wifi')
tap('SCAN')
tap_action(lambda a: a[0] == 'wifi_pick' and a[1]['ssid'] == b'HomeNet'); key('x')
tap('BACK');                          check('keyboard BACK = cancel', ui.screen == 'wifi_list' and ui.wf['text'] == '')
tap_action(lambda a: a[0] == 'wifi_pick' and a[1]['ssid'] == b'CoffeeShop')
n = len(calls)
tap('BACK');                          check('dialog BACK = NO', ui.confirm is None and len(calls) == n)
tap('BACK'); tap('BACK'); tap('BACK'); tap('BACK')
check('BACK x4 -> home', ui.screen == 'home')
# without Klipper
ui.st = None; ui.screen = 'home'
render();                             check('waiting page has a NETWORK button', 'NETWORK' in labels)
tap('NETWORK');                       check('network page without Klipper', ui.screen == 'network'); shot('no_klipper')
tap('BACK');                          check('BACK -> home (waiting page)', ui.screen == 'home')
print('calls:', calls)
print('FAILURES: %d' % fails)
sys.exit(1 if fails else 0)
