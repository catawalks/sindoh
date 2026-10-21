"""Compile every gcode template the way Klipper does (jinja2 with { } delimiters),
and check macro names against Klipper's G-code parser.
usage: cfglint.py file.cfg [file.cfg ...]"""
import configparser, re, sys
import jinja2
env = jinja2.Environment('{%', '%}', '{', '}')
# klippy/gcode.py splits a line with ([A-Z_]+|[A-Z*]): a name whose first
# letter run is followed by digits and then more text (e.g. _DP200_HOME_Z)
# parses as command "_DP200" + junk -> "Malformed command". Digits are only
# safe at the very end of a name (_LV_TRY1).
args_r = re.compile('([A-Z_]+|[A-Z*])')
def macro_name_ok(name):
    parts = args_r.split(name.upper())
    return len(parts) >= 3 and (parts[1] + parts[2].strip()) == name.upper()
bad = 0; n = 0
for path in sys.argv[1:]:
    cp = configparser.RawConfigParser(strict=False, inline_comment_prefixes=None)
    cp.read(path, encoding='utf-8')
    for sec in cp.sections():
        if sec.startswith('gcode_macro '):
            name = sec.split(None, 1)[1]
            if not macro_name_ok(name):
                bad += 1
                print('BAD [%s]: Klipper would parse this name as "%s" (Malformed command)'
                      % (sec, ''.join(args_r.split(name.upper())[1:3])))
        for key, val in cp.items(sec):
            if key.endswith('gcode') or key == 'gcode':
                n += 1
                try:
                    env.from_string(val)
                except jinja2.TemplateSyntaxError as e:
                    bad += 1
                    print('BAD [%s] %s line %s: %s' % (sec, key, e.lineno, e.message))
print('%d templates, %d errors' % (n, bad))
sys.exit(1 if bad else 0)
