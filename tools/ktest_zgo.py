"""Paper-test helper: put the cold nozzle at an exact Z (test coordinates: Z switch = 3.1, pre-calibration) over (X, Y),
then switch the drivers off (the Z leadscrew holds the bed). Run repeatedly with smaller Z while
the user slides paper under the nozzle; the Z where it starts to drag is nozzle zero.
Every run re-homes Z on the top switch (Z = 3.1) and approaches the target from below
(bed rising, like a probe touch), so backlash is the same each time. The probe is stowed first.
usage: ktest_zgo.py KLIPPER_TREE PRINTER_IP Z [X Y]
  with X Y: also homes X/Y and moves there (first call); without: X/Y stay where they are."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kmove
kl, ip, Z = sys.argv[1], sys.argv[2], float(sys.argv[3])
XY = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else None
if not -1.0 <= Z <= 30.0:
    sys.exit('refusing: Z must be within -1.0 .. 30.0')
if XY and not (0 <= XY[0] <= 200 and 10 <= XY[1] <= 195):
    sys.exit('refusing: X 0..200, Y 10..195')

m = kmove.Motion(kl, ip)
try:
    m.enable()
    if m.q('P') != 1 or XY:
        # bed well clear of the head before any X/Y travel or probe toggling
        m.pos['Z'] = 0.0
        m.home('Z', 3.0)
        m.move('Z', 13.1, 5.0)
        m.home('X', 10.0)
        if m.q('P') != 1:
            m.set_probe(1, 'stow')
            m.say('probe stowed')
        if XY:
            m.home('Y', 5.0)
            m.move('Y', XY[1], 20.0)
            m.move('X', XY[0], 20.0)
            m.say('at X %.1f Y %.1f' % XY)
        else:
            m.say('NOTE: X was homed to stow the probe; X is now %.1f' % m.pos['X'])
    m.pos['Z'] = 0.0
    m.home('Z', 3.0)
    # approach from below: go 1 mm past (bed lower), then rise slowly to the target
    m.move('Z', max(Z, 3.1) + 1.0, 3.0)
    m.move('Z', Z, 0.5)
    m.say('NOZZLE AT Z %.3f (bed %.3f mm %s the Z-switch height)'
          % (m.pos['Z'], abs(3.1 - m.pos['Z']), 'above' if m.pos['Z'] < 3.1 else 'below'))
    m.finish('holding Z %.3f' % m.pos['Z'])
except SystemExit:
    raise
except BaseException as e:
    m.finish('ABORT: %r' % e)
    raise
