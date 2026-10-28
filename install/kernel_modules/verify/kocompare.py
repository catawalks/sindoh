"""Compare struct layouts (DWARF) between our vanilla-3.2 build and the vendor
kernel's own modules, and check cdc-acm's imports against the kernel exports.
Usage: python -I kocompare.py DIR"""
import os, sys
sys.path.insert(0, os.path.join(os.environ['TEMP'], 'pdflib'))
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

D = sys.argv[1]


def structs(path):
    """name -> (byte_size, {member: offset}) for named, complete structs."""
    out = {}
    with open(path, 'rb') as f:
        elf = ELFFile(f)
        dw = elf.get_dwarf_info()
        for cu in dw.iter_CUs():
            for die in cu.iter_DIEs():
                if die.tag not in ('DW_TAG_structure_type', 'DW_TAG_union_type'):
                    continue
                if 'DW_AT_name' not in die.attributes or 'DW_AT_byte_size' not in die.attributes:
                    continue
                name = die.attributes['DW_AT_name'].value.decode()
                size = die.attributes['DW_AT_byte_size'].value
                mem = {}
                for c in die.iter_children():
                    if c.tag != 'DW_TAG_member':
                        continue
                    n = c.attributes.get('DW_AT_name')
                    if 'DW_AT_bit_size' in c.attributes:
                        continue                       # bitfields: encoded differently by GCC 4.6 / 14
                    loc = c.attributes.get('DW_AT_data_member_location')
                    off = loc.value if loc is not None else 0
                    if isinstance(off, list):          # old GCC: DW_OP_plus_uconst <ULEB128>
                        v, sh = 0, 0
                        for byte in off[1:]:
                            v |= (byte & 0x7f) << sh
                            sh += 7
                            if not byte & 0x80:
                                break
                        off = v
                    mem[n.value.decode() if n else '?%d' % len(mem)] = off
                key = ('union ' if die.tag == 'DW_TAG_union_type' else '') + name
                out.setdefault(key, (size, mem))
    return out


def compare(a, b, title):
    """a, b: struct dicts (or paths)."""
    a = structs(a) if isinstance(a, str) else a
    b = structs(b) if isinstance(b, str) else b
    common = sorted(set(a) & set(b))
    bad = []
    for s in common:
        (sa, ma), (sb, mb) = a[s], b[s]
        diffs = [m for m in ma if m in mb and ma[m] != mb[m]]
        missing = sorted(set(ma) ^ set(mb))
        if sa != sb or diffs or missing:
            bad.append((s, sa, sb, diffs[:6], missing[:6]))
    print('== %s: %d structs in common, %d differ' % (title, len(common), len(bad)))
    for s, sa, sb, diffs, missing in bad:
        print('   %-28s size ours %4d vendor %4d  offset diffs %s  members only in one: %s'
              % (s, sa, sb, diffs, missing))
    return common, bad


ours = os.path.join(D, 'x_cdcacm_debug.ko.bin')
# 1. sanity: the same source file built both ways (mbcache)
compare(os.path.join(D, 'x_mbcache_ours.ko.bin'), os.path.join(D, 'x_mbcache_stock.ko.bin'),
        'mbcache.ko ours vs vendor (same source)')
# 2. the structures cdc-acm uses vs every vendor-built module with debug info
vendor = {}
for m in ('x_ext4.ko.bin', 'x_jbd2.ko.bin', 'x_upc.ko.bin', 'x_m2m.ko.bin', 'x_dmcrypt.ko.bin',
          'x_mbcache_stock.ko.bin'):
    for k, v in structs(os.path.join(D, m)).items():
        vendor.setdefault(k, v)
mine = structs(ours)
print('   cdc-acm defines %d structs, vendor modules %d' % (len(mine), len(vendor)))
common, bad = compare(mine, vendor, 'cdc-acm vs vendor modules')
key = ['usb_device', 'usb_interface', 'urb', 'usb_host_endpoint', 'usb_endpoint_descriptor',
       'usb_host_interface', 'usb_driver', 'device', 'kobject', 'kref', 'mutex', 'spinlock',
       'list_head', 'work_struct', 'delayed_work', 'timer_list', 'wait_queue_head',
       'usb_anchor', 'usb_device_id', 'usb_ctrlrequest', 'device_driver',
       'tty_struct', 'tty_port', 'tty_driver', 'tty_operations', 'ktermios', 'raw_spinlock']
print('   key structs present in both:', [k for k in key if k in common])
print('   key structs NOT checkable here:', [k for k in key if k not in common])

# 3. imports vs exports
exports = set(open(os.path.join(D, 'x_exports.txt')).read().split())
with open(os.path.join(D, 'x_cdcacm.ko.bin'), 'rb') as f:
    elf = ELFFile(f)
    und = sorted({s.name for sec in elf.iter_sections() if isinstance(sec, SymbolTableSection)
                  for s in sec.iter_symbols() if s['st_shndx'] == 'SHN_UNDEF' and s.name})
missing = [s for s in und if s not in exports]
print('== cdc-acm imports %d symbols; not exported by the running kernel: %s' % (len(und), missing))
print('   imports:', ' '.join(und))
