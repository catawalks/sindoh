"""Rebuild a System.map from the kallsyms tables inside a decompressed
3.2 ARM kernel Image (CONFIG_KALLSYMS_ALL, absolute 32-bit addresses).

    python -I tools/kernel_re/kallsyms.py Image System.map [--base 0xc0008000]

3.2 layout; each table starts on a 16-byte boundary (scripts/kallsyms.c emits
".align 4", which ARM gas reads as 2^4):
kallsyms_addresses[n] u32, kallsyms_num_syms u32, kallsyms_names
(len byte + token indices), kallsyms_markers[(n+255)/256] u32,
kallsyms_token_table (256 NUL-terminated), kallsyms_token_index[256] u16."""
import struct
import sys


def find_addresses(img, lo, hi):
    """Longest run of non-decreasing in-range u32 words followed by its own
    length (kallsyms_num_syms)."""
    n = len(img) // 4
    w = struct.unpack_from(f'<{n}I', img)
    best = None
    i = 0
    while i < n:
        if not lo <= w[i] < hi:
            i += 1
            continue
        j = i + 1
        while j < n and lo <= w[j] < hi and w[j] >= w[j - 1]:
            j += 1
        run = j - i
        if run > 1000:
            # num_syms may follow directly or after alignment padding
            for k in range(j, min(j + 4, n)):
                if w[k] == run or (w[k] < run and w[k] > run - 4):
                    cnt = w[k]
                    if best is None or cnt > best[1]:
                        best = (i * 4, cnt, k * 4)
                    break
        i = j
    return best


def main():
    img = open(sys.argv[1], 'rb').read()
    base = 0xc0008000
    if '--base' in sys.argv:
        base = int(sys.argv[sys.argv.index('--base') + 1], 0)
    hi = base + len(img) + 0x200000  # .bss lies past the image
    found = find_addresses(img, 0xc0000000, hi)
    if not found:
        sys.exit('kallsyms_addresses not found')
    a_off, num, n_off = found
    addrs = struct.unpack_from(f'<{num}I', img, a_off)
    p = (n_off + 4 + 15) & ~15
    names_off = p
    entries = []
    for _ in range(num):
        ln = img[p]
        entries.append(img[p + 1:p + 1 + ln])
        p += 1 + ln
    p = (p + 15) & ~15
    p += 4 * ((num + 255) // 256)  # markers
    p = (p + 15) & ~15
    tok_off = p
    tokens = []
    for _ in range(256):
        e = img.index(b'\0', p)
        tokens.append(img[p:e].decode('latin-1'))
        p = e + 1
    out = []
    for a, ent in zip(addrs, entries):
        s = ''.join(tokens[b] for b in ent)
        out.append(f'{a:08x} {s[0]} {s[1:]}')
    open(sys.argv[2], 'w').write('\n'.join(out) + '\n')
    print(f'{num} symbols; addresses at Image+0x{a_off:x}, names at +0x{names_off:x}, '
          f'tokens at +0x{tok_off:x}')


if __name__ == '__main__':
    main()
