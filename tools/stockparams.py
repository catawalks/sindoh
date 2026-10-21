"""Map stock karas.db CONF_ENGINE_* columns to the main program's globals (engine_loadDBValue)
and print row NO=4 values (the row db_get_var() reads for CONF tables) with unit conversions.
usage: stockparams.py RE_snapshot.zip karas.db"""
import re, sqlite3, sys, zipfile
zf, db = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(zf)
def get(f):
    return z.read([x for x in z.namelist() if x.endswith('/' + f)][0]).decode(errors='replace')
c = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
def val(table, col):
    try:
        return c.execute('select "%s" from "%s" where NO=4' % (col, table)).fetchone()[0]
    except Exception:
        return None
t = get('engine_loadDBValue.c')
pat = re.compile(r'(xRam00361[0-9a-f]{3}) = db_get_var_\w+\(0x[0-9a-f]+ /\*"(CONF_ENGINE_\w+)"\*/,'
                 r'0x[0-9a-f]+ /\*"([^"]+)"')
seen = set()
out = []
for m in pat.finditer(t):
    g, tab, col = m.groups()
    if g in seen:
        continue
    seen.add(g)
    out.append((int(g[4:], 16), tab, col, val(tab, col)))
out.sort()
for addr, tab, col, v in out:
    print('%#x  %-22s %-34s %s' % (addr, tab[12:], col, v))
for f in ('UpcSetInsertParam.c', 'UpcSetRejectParam.c'):
    s = get(f)
    print(f, re.findall(r'0xc0047524,(0x[0-9a-f]+)', s), re.findall(r'write\(\w+,\w+,(0x[0-9a-f]+)\)', s))
