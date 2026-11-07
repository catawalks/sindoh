"""Offline test of the screen app's back-to-stock popup (stick_tick ->
two confirmations -> marker + reboot). Nothing is mounted, written or
rebooted: the stick probe, the marker path and the power request are
stubbed. Runs anywhere with Pillow:  python3 test_dp200_revert_popup.py"""
import os, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dp200_screen as S

T = tempfile.mkdtemp()
S.OUR_KERNEL = T                          # "our kernel": the path exists
S.REVERT_MARK = os.path.join(T, 'mark')
disks, sindoh, powered = [], set(), []
S.usb_disks = lambda: list(disks)
S.sindoh_stick = lambda d: d in sindoh
fails = 0

def check(name, cond):
    global fails
    fails += not cond
    print('%-52s %s' % (name, 'ok' if cond else 'FAIL'))

def tick(ui):
    ui.stk['checked'] = 0
    ui.stick_tick()
    for _ in range(100):                  # the probe runs in a thread
        if not ui.stk['busy']:
            break
        time.sleep(0.01)
    ui.stk['checked'] = 0
    ui.stick_tick()

def new_ui(state='standby'):
    ui = S.UI()
    ui.st = {'print_stats': {'state': state}}
    ui.power_request = lambda what: powered.append(what)
    return ui

def tap(ui, which):                       # YES / NO of the shown confirm
    q = ui.confirm
    ui.confirm = None                     # as on_touch does
    ui.run(q[1] if which == 'yes' else (q[2] if len(q) > 2 else ('cancel',)))

ui = new_ui()
tick(ui)
check('no stick: no popup', ui.confirm is None)
disks[:] = ['sda']
tick(ui)
check('plain stick: no popup', ui.confirm is None)

disks[:], sindoh = [], {'sdb'}
tick(ui)
disks[:] = ['sdb']
tick(ui)
check('Sindoh stick: first question', ui.confirm is not None and 'Sindoh' in ui.confirm[0])
tap(ui, 'yes')
check('first YES: second question', ui.confirm is not None and 'returns the printer' in ui.confirm[0])
check('  nothing written yet', not os.path.exists(S.REVERT_MARK) and not powered)
tap(ui, 'no')
check('second NO: nothing written, no reboot', not os.path.exists(S.REVERT_MARK) and not powered)
tick(ui)
check('same stick still in: not asked again', ui.confirm is None)
disks[:] = []
tick(ui)
disks[:] = ['sdb']
tick(ui)
check('plugged in again: asked again', ui.confirm is not None)
tap(ui, 'no')
check('first NO: nothing written', not os.path.exists(S.REVERT_MARK) and not powered)

disks[:] = []
tick(ui)
disks[:] = ['sdb']
tick(ui)
tap(ui, 'yes')
tap(ui, 'yes')
check('YES, YES: marker written, reboot requested',
      os.path.exists(S.REVERT_MARK) and powered == ['reboot'])
os.remove(S.REVERT_MARK)
powered.clear()

ui = new_ui('printing')
disks[:] = []
tick(ui)
disks[:] = ['sdb']
tick(ui)
check('while printing: no popup', ui.confirm is None)
ui.st = {'print_stats': {'state': 'complete'}}
tick(ui)
check('after the print: asked', ui.confirm is not None)

ui = new_ui()
S.OUR_KERNEL = os.path.join(T, 'absent')  # the stock kernel (interim install)
disks[:] = []
tick(ui)
disks[:] = ['sdb']
tick(ui)
check('stock kernel: never asks', ui.confirm is None)

print('all ok' if not fails else '%d FAILED' % fails)
sys.exit(1 if fails else 0)
