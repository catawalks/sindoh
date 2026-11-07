# lowmem_check.py: model of arm/mm/mmu.c map_lowmem() on 2-level ARM for a RAM
# layout with no-map holes: a 2 MB first-level pair whose one 1 MB half is a
# section and whose other half needs a PTE table hits BUG_ON(pmd_bad()).
MB = 1 << 20
RAM = (0, 0x20000000)


def regions(nomap):
    out, cur = [], RAM[0]
    for s, e in sorted(nomap):
        if s > cur:
            out.append((cur, s))
        cur = max(cur, e)
    if cur < RAM[1]:
        out.append((cur, RAM[1]))
    return out


def check(name, nomap):
    pairs = {}  # pair base -> {half: 'sect'|'pte'}
    bug = None
    for s, e in regions(nomap):
        addr = s
        while addr < e:
            nxt = min((addr // MB + 1) * MB, e)  # pmd_addr_end per 1 MB half
            pair, half = addr // (2 * MB), (addr // MB) % 2
            kind = 'sect' if addr % MB == 0 and nxt % MB == 0 else 'pte'
            st = pairs.setdefault(pair, {})
            if kind == 'pte':
                # arm_pte_alloc looks at the first entry of the pair
                if st.get(0) == 'sect' or st.get(1) == 'sect':
                    bug = bug or (addr, pair * 2 * MB)
            elif 'pte' in st.values():
                pass  # a section next to a table is written into the pair: fine
            st[half] = kind
            addr = nxt
    print("%-34s %s" % (name, "BUG at %#x (pair %#x)" % bug if bug else "ok"))


fb = (0x18000000, 0x180bc000)
check("dc3b5f20 (framebuffer only)", [fb])
check("errata-dbg (ramoops reserve only)", [fb])
check("nanddbg 0685c985 (4 KB no-map)", [fb, (0x1e100000, 0x1e101000)])
check("nanddbg fixed (2 x 1 MB no-map)", [fb, (0x1e000000, 0x1e200000)])
