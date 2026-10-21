"""Dump karas.db tables whose name or variable names match a keyword.
usage: dbdump.py karas.db [keyword ...]"""
import sqlite3, sys
db = sys.argv[1]
keys = [k.upper() for k in sys.argv[2:]] or ['']
c = sqlite3.connect('file:%s?mode=ro' % db, uri=True)
tabs = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
for t in tabs:
    cols = [r[1] for r in c.execute('pragma table_info("%s")' % t)]
    rows = c.execute('select * from "%s"' % t).fetchall()
    for row in rows:
        line = ' | '.join(str(x) for x in row)
        if any(k in t.upper() or k in line.upper() for k in keys):
            print('%s: %s' % (t, line[:220]))
