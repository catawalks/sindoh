"""Check printer.cfg pin references against the built MCU data dictionaries.
usage: cfgcheck.py printer.cfg fm_klipper.dict io_klipper.dict"""
import sys, json, re, configparser
cfg_path, fm_dict, io_dict = sys.argv[1:4]
dicts = {'mcu': json.load(open(fm_dict)), 'io': json.load(open(io_dict))}
def expand(enums):
    # Same expansion as klippy/msgproto.py fill_enumerations()
    out = set()
    for name, v in enums.items():
        if isinstance(v, list) and len(v) == 2:
            root = name.rstrip('0123456789')
            start = int(name[len(root):] or 0)
            out.update('%s%d' % (root, start + i) for i in range(v[1]))
        else:
            out.add(name)
    return out
pins = {m: expand(d['enumerations']['pin']) for m, d in dicts.items()}
cp = configparser.RawConfigParser(inline_comment_prefixes=('#', ';'), strict=False)
cp.read(cfg_path)
bad = 0; n = 0
for sec in cp.sections():
    for key, val in cp.items(sec):
        if not (key.endswith('_pin') or key == 'pin'):
            continue
        n += 1
        v = val.strip().lstrip('^~!').strip()
        mcu, _, name = v.rpartition(':')
        mcu = mcu or 'mcu'
        ok = name in pins.get(mcu, ())
        if not ok:
            bad += 1
        print(('ok  ' if ok else 'BAD ') + f'[{sec}] {key} = {val}  -> {mcu}:{name}')
        # adc pins only exist on the IO core build (CONFIG_WANT_ADC)
for m, d in dicts.items():
    c = d['config']
    cmds = d['commands']
    print(m, 'MCU', c.get('MCU'), 'ADC_MAX', c.get('ADC_MAX'), 'PWM_MAX', c.get('PWM_MAX'),
          'has analog_in:', any(k.startswith('config_analog_in') for k in cmds),
          'has hard pwm:', any(k.startswith('config_pwm_out') for k in cmds),
          'has stepper:', any(k.startswith('config_stepper') for k in cmds))
print(f'{n} pin references, {bad} bad')
sys.exit(1 if bad else 0)
