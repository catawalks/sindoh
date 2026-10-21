"""Print karas.db tables column-wise (one line per column, one value per row).
usage: dbcols.py karas.db TABLE [TABLE ...]"""
import sqlite3, sys
c = sqlite3.connect('file:%s?mode=ro' % sys.argv[1], uri=True)
for t in sys.argv[2:]:
    cols = [r[1] for r in c.execute('pragma table_info("%s")' % t)]
    rows = c.execute('select * from "%s"' % t).fetchall()
    print('==', t)
    for i, col in enumerate(cols):
        print('  %-30s %s' % (col, '  '.join(str(r[i]) for r in rows)))
