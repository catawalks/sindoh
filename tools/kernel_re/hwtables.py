"""Dump the vendor kernel's static hardware tables from the decompressed
Image + System.map (see kallsyms.py):

  * gogin_io_desc  - the static virtual->physical I/O map (struct map_desc),
                     needed to turn the driver's 0xfeXXXXXX addresses into
                     physical ones;
  * every struct resource in .data/.init.data with an MMIO address in the
    SoC register window or an IRQ number, grouped under the nearest symbol
    (platform device resources);
  * the ATAGS machine record (struct machine_desc: number, name, hooks).

    python -I tools/kernel_re/hwtables.py Image System.map > hwtables.txt
"""
import bisect
import struct
import sys

BASE = 0xc0008000
MT = {0: 'DEVICE', 1: 'DEVICE_NONSHARED', 2: 'DEVICE_CACHED', 3: 'DEVICE_WC',
      9: 'MEMORY', 11: 'MEMORY_NONCACHED'}
IORESOURCE_MEM, IORESOURCE_IRQ = 0x200, 0x400


def main():
    img = open(sys.argv[1], 'rb').read()
    syms = sorted((int(l.split()[0], 16), l.split()[2]) for l in open(sys.argv[2]))
    addrs = [a for a, _ in syms]
    byname = {n: a for a, n in syms}

    def u32(va):
        return struct.unpack_from('<I', img, va - BASE)[0]

    def near(va):
        i = bisect.bisect_right(addrs, va) - 1
        a, n = syms[i]
        return n if a == va else f'{n}+0x{va - a:x}'

    def cstr(va):
        o = va - BASE
        if not 0 <= o < len(img):
            return None
        e = img.find(b'\0', o, o + 64)
        s = img[o:e]
        return s.decode() if e > o and all(32 <= c < 127 for c in s) else None

    def symend(va):
        i = bisect.bisect_right(addrs, va)
        return addrs[i] if i < len(addrs) else va + 0x1000

    # 1. static I/O map
    if 'gogin_io_desc' in byname:
        va = byname['gogin_io_desc']
        print('== gogin_io_desc (virtual -> physical, length, type)')
        rows = []
        while va + 16 <= symend(va):
            v, pfn, ln, t = struct.unpack_from('<4I', img, va - BASE)
            if ln == 0 or v < 0xf0000000 or ln > 0x10000000:
                break
            rows.append((v, pfn << 12, ln, t))
            va += 16
        for v, p, ln, t in rows:
            print(f'  virt {v:08x}  phys {p:08x}  len {ln:08x}  {MT.get(t, t)}')
        print(f'  ({len(rows)} entries)')

    # 2. struct resource arrays: start, end, name, flags, parent, sibling, child
    print('\n== struct resource entries (MMIO in f8000000-fa3fffff, or IRQ)')
    lo = byname.get('_sdata', 0xc0980000)
    lo = min(lo, byname.get('__init_begin', lo))
    last_owner = None
    for va in range(byname.get('__init_begin', 0xc056f000), BASE + len(img) - 28, 4):
        s, e, nm, fl, p, sib, ch = struct.unpack_from('<7I', img, va - BASE)
        if p or sib or ch:
            continue
        kind = fl & 0x1f00
        if kind == IORESOURCE_MEM and 0xf8000000 <= s <= e <= 0xfa3fffff and e - s < 0x200000:
            what = f'MEM {s:08x}-{e:08x}'
        elif kind == IORESOURCE_IRQ and s == e and 0 < s < 604:
            what = f'IRQ {s}'
        else:
            continue
        name = cstr(nm) if nm else None
        owner = near(va).split('+')[0]
        if owner != last_owner:
            print(f'  [{owner}]')
            last_owner = owner
        print(f'    {va:08x}  {what:24s} flags {fl:08x}  {name or ""}')

    # 3. machine_desc: nr, name, boot_params, ... search .arch.info.init
    print('\n== machine_desc')
    for nm in ('__arch_info_begin',):
        if nm in byname:
            va = byname[nm]
            nr, name = u32(va), cstr(u32(va + 4))
            print(f'  machine nr {nr} (0x{nr:x}) name {name!r}')
            for k in range(2, 24):
                w = u32(va + 4 * k)
                if 0xc0008000 <= w < 0xc0a62000:
                    print(f'    +0x{4 * k:02x}: {w:08x} {near(w)}')
                elif w:
                    print(f'    +0x{4 * k:02x}: {w:08x}')


if __name__ == '__main__':
    main()
