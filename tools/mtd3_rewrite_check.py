# mtd3 rewrite test helper (2026-11-01, owner-approved): compare raw dumps
# (2048 data + 64 OOB per page, nanddump -n format) and corrected images.
#   pages RAW            programmed pages ("programz" in OOB 24-31)
#   diff RAW_A RAW_B     per-page bit differences, data / OOB 0-61 / 62-63
import sys

P, O = 2048, 64


def pages(raw):
    return [raw[i:i + P + O] for i in range(0, len(raw), P + O)]


def bits(a, b):
    return sum(bin(x ^ y).count('1') for x, y in zip(a, b))


cmd = sys.argv[1]
if cmd == 'pages':
    pg = pages(open(sys.argv[2], 'rb').read())
    prog = [i for i, p in enumerate(pg) if p[P + 24:P + 32] == b'programz']
    erased = [i for i, p in enumerate(pg) if p.count(0xff) >= len(p) - 8]
    other = len(pg) - len(prog) - len(erased)
    print('PAGES', len(pg), 'programmed', len(prog),
          'range', prog[0] if prog else None, prog[-1] if prog else None,
          'contiguous', prog == list(range(len(prog))),
          'erased', len(erased), 'other', other)
elif cmd == 'diff':
    a = pages(open(sys.argv[2], 'rb').read())
    b = pages(open(sys.argv[3], 'rb').read())
    tot_d = tot_e = tot_x = 0
    worst = []
    for i, (x, y) in enumerate(zip(a, b)):
        d, e, t = bits(x[:P], y[:P]), bits(x[P:P + 62], y[P:P + 62]), bits(x[P + 62:], y[P + 62:])
        tot_d += d; tot_e += e; tot_x += t
        if d or e or t:
            worst.append((i, d, e, t))
    print('DIFF pages', len(a), len(b), 'data_bits', tot_d, 'oob_bits', tot_e,
          'oob62_63_bits', tot_x, 'pages_differing', len(worst),
          'max_per_page', max((w[1] + w[2] for w in worst), default=0))
    for w in worst[:12]:
        print('  page %d: data %d, oob %d, oob62-63 %d' % w)
