"""Check that every line of a Kconfig fragment ended up in a .config.

usage: python3 checkconfig.py .config fragment

The fragment may be several fragments concatenated: the last assignment of
a symbol wins. "# m1-ignore: CONFIG_A CONFIG_B" skips symbols that a later
fragment makes disappear (e.g. NR_CPUS without SMP).
"""
import re
import sys

have = {}
for line in open(sys.argv[1]):
    m = re.match(r"(CONFIG_\w+)=(.*)", line)
    if m:
        have[m.group(1)] = m.group(2).strip()

want = {}
ignore = set()
for line in open(sys.argv[2]):
    line = line.strip()
    m = re.match(r"(CONFIG_\w+)=(.*)", line)
    if m:
        want[m.group(1)] = m.group(2)
        continue
    m = re.match(r"# (CONFIG_\w+) is not set", line)
    if m:
        want[m.group(1)] = None
        continue
    m = re.match(r"# m1-ignore:(.*)", line)
    if m:
        ignore.update(m.group(1).split())

bad = []
for sym, val in want.items():
    if sym in ignore:
        continue
    got = have.get(sym)
    if val is None:
        if got not in (None, "n"):
            bad.append(f"# {sym} is not set  (got {got})")
    elif got != val:
        bad.append(f"{sym}={val}  (got {got or 'unset'})")

for b in bad:
    print("config mismatch:", b)
sys.exit(1 if bad else 0)
