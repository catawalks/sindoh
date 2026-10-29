"""Check that every line of a Kconfig fragment ended up in a .config.

usage: python3 checkconfig.py .config fragment
"""
import re
import sys

have = {}
for line in open(sys.argv[1]):
    m = re.match(r"(CONFIG_\w+)=(.*)", line)
    if m:
        have[m.group(1)] = m.group(2).strip()

bad = []
for line in open(sys.argv[2]):
    line = line.strip()
    m = re.match(r"(CONFIG_\w+)=(.*)", line)
    if m:
        if have.get(m.group(1)) != m.group(2):
            bad.append(f"{line}  (got {have.get(m.group(1), 'unset')})")
        continue
    m = re.match(r"# (CONFIG_\w+) is not set", line)
    if m and have.get(m.group(1)) not in (None, "n"):
        bad.append(f"{line}  (got {have[m.group(1)]})")

for b in bad:
    print("config mismatch:", b)
sys.exit(1 if bad else 0)
