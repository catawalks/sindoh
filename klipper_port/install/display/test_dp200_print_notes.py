"""Offline test of the owner's 11-12 screen notes, with a made-up printer
status (no Moonraker, nothing sent: post() and get() are stubbed):
  1  a paused print: HOME and the job banner, nothing that homes
  2  a LOAD that stops: the error page with UNLOAD / TRY AGAIN
  3  EMPTY BIN -> the empty-the-bin page -> DONE (BIN_EMPTIED)
  5  custom macro buttons (home -> MACROS, a JSON file)
  6  a print that is starting (bed question, PRINT_START): not "paused"
Runs anywhere with Pillow:  python3 test_dp200_print_notes.py
    python3 test_dp200_print_notes.py --demo DIR   also saves the pages as PNGs"""
import io, json, os, sys, tempfile, time, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dp200_screen as S

DEMO = sys.argv[sys.argv.index('--demo') + 1] if '--demo' in sys.argv else None
if not os.path.exists(S.FONT):            # a PC: any bold TrueType font for the PNGs
    for f in ('C:/Windows/Fonts/arialbd.ttf', '/Library/Fonts/Arial Bold.ttf'):
        if os.path.exists(f):
            S.FONT = f
            S.font.__defaults__ = (f,)
            break

sent, refuse = [], {}
def post(path, body=None):
    script = (body or {}).get('script')
    sent.append((path, script))
    for word, msg in refuse.items():      # a G-code Klipper refuses: HTTP 400 + its message
        if script and word in script:
            raise urllib.error.HTTPError(S.API, 400, 'Bad Request', {},
                                         io.BytesIO(json.dumps({'error': {'message': msg}}).encode()))
    return {'result': 'ok'}
S.post = post
S.get = lambda path: {'objects': ['gcode_macro PRINT_START', 'gcode_macro _DP200', 'gcode_macro MY_PURGE',
                                  'gcode_macro PARK_REAR', 'extruder', 'gcode_macro LAMP_TOGGLE']}
T = tempfile.mkdtemp()
S.MACROS_FILE = os.path.join(T, 'dp200_screen_macros.json')
S.SETTINGS = os.path.join(T, 'screen_settings.json')
fails = 0

def check(name, cond):
    global fails
    fails += not cond
    print('%-56s %s' % (name, 'ok' if cond else 'FAIL'))

def status(state='standby', homed='xyz', z=30.0, bins=3):
    return {'webhooks': {'state': 'ready', 'state_message': ''},
            'print_stats': {'state': state, 'filename': 'benchy_pla_0.2mm.gcode' if state != 'standby' else '',
                            'print_duration': 1800.0},
            'virtual_sdcard': {'progress': 0.42}, 'display_status': {'progress': 0.42},
            'extruder': {'temperature': 215.0, 'target': 215.0, 'can_extrude': True},
            'heater_bed': {'temperature': 60.0, 'target': 60.0},
            'output_pin lamp': {'value': 1.0},
            'gcode_move': {'homing_origin': [0.0, 0.0, 0.0, 0.0]},
            'toolhead': {'homed_axes': homed, 'position': [100.0, 190.0, z, 0.0]},
            'idle_timeout': {'state': 'Ready'},
            'filament_switch_sensor cartridge_lever': {'filament_detected': False},
            'filament_motion_sensor filament_encoder': {'enabled': True, 'filament_detected': True},
            'dp200_cartridge': {'present': False}, 'gcode_macro _DRY': {'active': 0},
            'gcode_macro BED_CLEAR': {'ok': 0, 'asking': 0}, 'manual_probe': {'is_active': False},
            'exclude_object': {'objects': []}, 'save_variables': {'variables': {'bin_count': bins}}}

ui = S.UI()
ui.settings = {}
ui.st = status()

labels = {}
_orig_button = S.UI.button
def button(self, d, box, label, action, *a, **k):
    labels[label] = action
    return _orig_button(self, d, box, label, action, *a, **k)
S.UI.button = button

def render(name=None):
    labels.clear()
    im = ui.render()
    if DEMO and name:
        os.makedirs(DEMO, exist_ok=True)
        im.save(os.path.join(DEMO, name + '.png'))
    return im

def wait():
    for _ in range(300):
        if not ui.busy:
            break
        time.sleep(0.01)

def tap(label):
    render()
    a = labels.get(label)
    if a is None:
        return False
    if ui.confirm and a[0] != 'cancel':
        ui.confirm = None                 # as on_touch does
    ui.run(a)
    wait()
    render()
    return True

# ---- 1: a paused print ----------------------------------------------------
ui.st = status('printing')
ui.screen = 'home'; render()
check('printing: home shows the print page', ui.screen == 'print')
render(); check('printing: no HOME button on the print page', '' not in labels)
ui.st = status('paused')
render('1_print_paused')
check('paused: HOME button on the print page', '' in labels)
tap('');  render('1_home_paused')
check('paused: HOME -> home page (stays there)', ui.screen == 'home')
check('home shows the job: RESUME, CANCEL, JOB', all(k in labels for k in ('RESUME', 'CANCEL', 'JOB')))
tap('RESUME'); check('RESUME asks first', ui.confirm is not None and 'Resume' in ui.confirm[0])
n = len(sent); tap('YES'); check('YES sends RESUME', sent[n:] == [('/printer/gcode/script', 'RESUME')])
tap('JOB'); check('JOB -> print page', ui.screen == 'print')
n = len(sent); tap('RESUME')
check('print page RESUME asks first too', ui.confirm is not None and len(sent) == n)
tap('YES'); check('  YES sends RESUME', sent[n:] == [('/printer/gcode/script', 'RESUME')])
ui.st = status('printing'); render()
n = len(sent); tap('PAUSE'); check('PAUSE: no question (it stops motion)', sent[n:] == [('/printer/gcode/script', 'PAUSE')])
ui.st = status('paused')
tap(''); tap('MOVE'); render('1_move_paused')
check('paused MOVE: HOME, MOTORS OFF, CALIBRATE, BED LEVEL off',
      all(labels.get(k) is None for k in ('HOME', 'MOTORS OFF', 'CALIBRATE', 'BED LEVEL')))
tap('LOWER BED')
check('paused LOWER BED: no homing macro', ui.confirm and ui.confirm[1][1] == 'G90\nG1 Z%d F600' % S.LOWER_BED_Z)
tap('NO')
ui.st = status('paused', z=150.0); render()
check('paused, bed already low: LOWER BED off', labels.get('LOWER BED') is None)
ui.st = status('paused')
tap('CLEAN'); check('paused CLEAN still asks (no homing)', ui.confirm is not None and 'EMPTY' not in ui.confirm[0])
tap('NO')
n = len(sent); ui.run(('confirm', 'x', ('gcode', 'BED_CLEAR\nG28', 'Home all')))
check('paused: a G28 confirm is refused', ui.confirm is None and len(sent) == n)
ui.screen = 'bedlevel'; render(); check('paused: the bed level page is left', ui.screen == 'move')
ui.st = status('paused', homed='')
render('1_move_paused_unhomed')
check('paused + not homed: nothing left on MOVE',
      [k for k in ('HOME', 'LOWER BED', 'CLEAN', 'MOTORS OFF', 'EMPTY BIN', 'CALIBRATE', 'BED LEVEL')
       if labels.get(k) is not None] == [])
ui.screen = 'fil_mat'; n = len(sent); tap('PLA')
check('paused + not homed: LOAD refused (would home Z)', ui.confirm is None and len(sent) == n)
ui.st = status('paused')
tap('PLA'); check('paused, homed: LOAD asks (no bed question)', ui.confirm and 'EMPTY' not in ui.confirm[0])
tap('NO')
ui.screen = 'home'; render()
tap('COOL DOWN'); check('paused: COOL DOWN asks first', ui.confirm is not None and 'paused' in ui.confirm[0])
tap('NO')
ui.screen = 'filament'
ui.st = status('printing'); render()
check('resumed: a filament page goes to the print page', ui.screen == 'print')
ui.st = status('cancelled'); render()
check('cancelled: print page -> home', ui.screen == 'home')
tap('MOVE'); check('cancelled: HOME on MOVE works again', labels.get('HOME') == ('screen', 'homing'))
tap('HOME'); tap('HOME Z')
check('cancelled: HOME Z still asks BED_CLEAR', ui.confirm and 'EMPTY' in ui.confirm[0]
      and ui.confirm[1][1] == 'BED_CLEAR\nG28 Z')
tap('NO')

# ---- 2: a LOAD that stops -------------------------------------------------
ui.st = status()
ui.screen = 'fil_mat'; ui.fil['mode'] = 'load'
jam = ('LOAD_FILAMENT stopped: the filament encoder saw no movement (jam, or the feeder did not '
       'grab the filament). Check the inlet, then UNLOAD and try again')
refuse['LOAD_FILAMENT'] = jam
tap('PLA'); tap('YES')
render('2_load_stopped')
check('stopped LOAD -> error page', ui.screen == 'fil_error')
check('  with Klipper\'s whole message', ui.fil_fail and ui.fil_fail['msg'] == jam)
check('  no "complete" flash', not (ui.msg and 'complete' in ui.msg[0]))
tap('UNLOAD'); check('UNLOAD asks first', ui.confirm is not None)
del refuse['LOAD_FILAMENT']
tap('YES')
check('UNLOAD sends UNLOAD_FILAMENT MATERIAL=PLA', sent[-1] == ('/printer/gcode/script', 'UNLOAD_FILAMENT MATERIAL=PLA'))
check('  and says it finished', ui.msg and 'complete' in ui.msg[0] and ui.screen == 'filament')
ui.screen = 'fil_error'
tap('TRY AGAIN'); tap('YES')
check('TRY AGAIN sends the same LOAD', sent[-1] == ('/printer/gcode/script', 'LOAD_FILAMENT MATERIAL=PLA'))
check('  ok this time: "complete", back to FILAMENT', ui.msg and 'Load complete' in ui.msg[0]
      and ui.screen == 'filament')
ui.screen = 'fil_error'; tap('OK'); check('OK -> filament page', ui.screen == 'filament')
ui.st = status(homed='')
ui.screen = 'fil_mat'; tap('PETG'); tap('YES')
check('unhomed LOAD still sends BED_CLEAR first', sent[-1][1] == 'BED_CLEAR\nLOAD_FILAMENT TEMP=240')
refuse['UNLOAD_FILAMENT'] = 'Homing cancelled: the bed is not confirmed empty'
ui.st = status()
ui.fil['mode'] = 'unload'; tap('ABS'); tap('YES')
render('2_unload_stopped')
check('stopped UNLOAD -> error page, TRY AGAIN, no UNLOAD',
      ui.screen == 'fil_error' and 'TRY AGAIN' in labels and 'UNLOAD' not in labels)
del refuse['UNLOAD_FILAMENT']

# ---- 3: EMPTY BIN ---------------------------------------------------------
ui.st = status(bins=16)
ui.screen = 'home'; render('3_home_bin_full')
ui.screen = 'move'; render('3_move')
check('EMPTY BIN on MOVE', labels.get('EMPTY BIN') is not None)
n = len(sent); tap('EMPTY BIN')
check('EMPTY BIN asks first', ui.confirm is not None and len(sent) == n)
tap('NO'); check('NO: nothing sent', len(sent) == n)
tap('EMPTY BIN'); tap('YES')
check('YES sends EMPTY_BIN', sent[-1] == ('/printer/gcode/script', 'EMPTY_BIN'))
render('3_bin')
check('then the empty-the-bin page', ui.screen == 'bin' and 'DONE' in labels)
n = len(sent); tap('DONE')
check('DONE sends BIN_EMPTIED and confirms', sent[n:] == [('/printer/gcode/script', 'BIN_EMPTIED')]
      and ui.screen == 'move' and 'Bin emptied' in ui.msg[0])
ui.st = status(homed='')
tap('EMPTY BIN'); check('unhomed EMPTY BIN asks about the bed', 'EMPTY?' in ui.confirm[0]
                        and ui.confirm[1][1] == 'BED_CLEAR\nEMPTY_BIN')
tap('NO')
ui.st = status('paused')
tap('EMPTY BIN'); tap('YES')
check('paused EMPTY BIN allowed', sent[-1] == ('/printer/gcode/script', 'EMPTY_BIN') and ui.screen == 'bin')
render('3_bin_paused')
ui.st = status()

# ---- 5: custom macro buttons ----------------------------------------------
ui.screen = 'home'; render('5_home')
check('MACROS on the home page', labels.get('MACROS') == ('screen', 'macros'))
ui.screen = 'move'; render(); check('no MACROS on MOVE', 'MACROS' not in labels)
ui.screen = 'home'; tap('MACROS'); render('5_macros_empty')
check('MACROS: no file -> no buttons, EDIT', ui.screen == 'macros' and 'EDIT' in labels)
check('MACROS BACK -> home', ui.back_action() == ('screen', 'home'))
tap('EDIT'); render('5_macros_edit')
check('EDIT lists the macros without _ names', ui.mac['all'] == ['LAMP_TOGGLE', 'MY_PURGE', 'PARK_REAR', 'PRINT_START'])
tap('MY_PURGE'); tap('PARK_REAR')
saved = json.load(open(S.MACROS_FILE))
check('tapping two adds two buttons to the file', [b['gcode'] for b in saved['buttons']] == ['MY_PURGE', 'PARK_REAR'])
render('5_macros_edit_on')
tap('PARK_REAR')
check('tapping again removes it', [b['gcode'] for b in json.load(open(S.MACROS_FILE))['buttons']] == ['MY_PURGE'])
with open(S.MACROS_FILE, 'w') as f:      # as edited in Mainsail
    json.dump({'buttons': [{'label': 'PURGE', 'gcode': 'MY_PURGE'},
                           {'label': 'PARK', 'gcode': 'PARK_REAR', 'confirm': 'Park the head at the back?'},
                           {'gcode': 'M117 hello'}]}, f)
ui.screen = 'home'; tap('MACROS'); render('5_macros')
check('file edited elsewhere: re-read', all(k in labels for k in ('PURGE', 'PARK', 'M117')))
n = len(sent); tap('PURGE')
check('a macro button asks first', ui.confirm is not None and 'MY_PURGE' in ui.confirm[0] and len(sent) == n)
tap('YES'); check('YES runs it', sent[-1] == ('/printer/gcode/script', 'MY_PURGE'))
tap('PARK'); check('own question from the file', ui.confirm[0] == 'Park the head at the back?')
tap('NO')
ui.st = status('paused'); render('5_macros_paused')
n = len(sent); tap('PURGE')
check('paused: a macro still asks first', ui.confirm is not None and len(sent) == n)
tap('YES'); check('  and runs on YES (the user answers for it)', sent[-1] == ('/printer/gcode/script', 'MY_PURGE'))
ui.screen = 'home'; render('5_home_paused')
check('paused home page: MACROS there', labels.get('MACROS') == ('screen', 'macros'))
ui.st = status()
open(S.MACROS_FILE, 'w').write('{"buttons": [ {"label": "x"} ]}')
ui.screen = 'home'; tap('MACROS'); render('5_macros_broken')
check('broken file: shown, no buttons', ui.mac['error'] and 'gcode' in ui.mac['error'])
tap('EDIT'); check('broken file: EDIT refuses (file kept)', ui.screen == 'macros'
                   and json.load(open(S.MACROS_FILE)) == {'buttons': [{'label': 'x'}]})
open(S.MACROS_FILE, 'w').write('not json')
tap('BACK') if 'BACK' in labels else None
ui.screen = 'home'; tap('MACROS'); check('not JSON: error shown', ui.mac['error'] is not None)

# ---- 6: a print that is starting (Klipper: paused) ---------------------------
def starting(pending='', start=0, **kw):
    st = status('paused', **kw)
    st['gcode_macro PRINT_START'] = {'pending': pending, 'starting': start}
    return st

ui.screen, ui.confirm, ui.last_pstate = 'home', None, 'standby'
ui.st = starting(pending='BED=60 EXTRUDER=210 MESH=4', homed='')
ui.st['gcode_macro BED_CLEAR'] = {'ok': 0, 'asking': 1}
ui.bed_answered = 0.0
render('6_bed_question')
check('bed question: the print page, not home', ui.screen == 'print')
check('  the bed dialog is up', ui.confirm is not None and 'EMPTY' in ui.confirm[0])
check('  no PRINT PAUSED banner, no RESUME', 'RESUME' not in labels and 'JOB' not in labels)
tap('YES')
check('YES sends BED_CLEAR', sent[-1] == ('/printer/gcode/script', 'BED_CLEAR'))
check('  without holding the busy slot (the start takes ~7 min)', ui.busy is None)
ui.st = starting(start=1, homed='')
ui.st['extruder'] = {'temperature': 60.0, 'target': 150.0}
ui.st['heater_bed'] = {'temperature': 30.0, 'target': 60.0}
render('6_starting_home')
check('starting: "Starting print", step Homing', S.start_phase(ui.st) == 'home')
check('  only CANCEL and LAMP', [k for k in labels if k] == ['CANCEL', 'LAMP'])
check('  no HOME button', '' not in labels)
ui.st['toolhead'] = dict(ui.st['toolhead'], homed_axes='xyz')
check('homed, bed cold: Heating the bed', S.start_phase(ui.st) == 'bed')
ui.st['heater_bed'] = {'temperature': 59.6, 'target': 60.0}
render('6_starting_mesh')
check('bed hot, nozzle at 150: Probing', S.start_phase(ui.st) == 'mesh')
ui.st['extruder'] = {'temperature': 170.0, 'target': 215.0}
check('nozzle heating to print temp: Heating the nozzle', S.start_phase(ui.st) == 'nozzle')
ui.st['extruder'] = {'temperature': 214.0, 'target': 215.0}
check('nozzle hot: Purging', S.start_phase(ui.st) == 'purge')
ui.screen = 'home'; render()
check('starting: home goes to the print page', ui.screen == 'print')
n = len(sent); tap('CANCEL'); check('CANCEL asks first', ui.confirm is not None and len(sent) == n)
tap('YES'); check('  YES sends CANCEL_PRINT', sent[-1] == ('/printer/gcode/script', 'CANCEL_PRINT'))
n = len(sent); ui.run(('confirm', 'x', ('gcode', 'BED_CLEAR\nG28', 'Home all')))
check('starting: homing refused', ui.confirm is None and len(sent) == n)
ui.screen = 'bedlevel'; render(); check('starting: no pause pages (back to print)', ui.screen == 'print')
ui.st = status('printing'); render()
check('start done -> printing: normal print page', 'PAUSE' in labels)
ui.st = status('paused'); render()
check('a real pause: RESUME and HOME again', 'RESUME' in labels and '' in labels)

# ---- STOP is on every new page ----------------------------------------------
for page in ('fil_error', 'bin', 'macros', 'macros_edit', 'print'):
    ui.screen, ui.confirm = page, None
    if page == 'print':
        ui.st = starting(start=1)
    ui.render()
    check('STOP on %s' % page, any(a == ('estop',) for _, a in ui.buttons))
print('FAILURES: %d' % fails)
sys.exit(1 if fails else 0)
