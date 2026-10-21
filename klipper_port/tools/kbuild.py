"""Mimic Klipper's make for MACH_UPC on Windows using zig as the cross compiler.
usage: kbuild.py KLIPPER_TREE PORT_DIR CONFIG_FILE OUTDIR [extra cflags...]"""
import os, re, shutil, subprocess, sys

kl, port, cfg, out = [os.path.abspath(a) for a in sys.argv[1:5]]
extra = sys.argv[5:]
here = os.path.dirname(os.path.abspath(__file__))
zig = os.path.join(here, '..', 'zig', 'ziglang', 'zig.exe')
target = ['-target', 'thumb-freestanding-eabi' if '-mthumb' in sys.argv else 'arm-freestanding-eabi', '-mcpu=arm946e_s']
sys.argv = [a for a in sys.argv if a != '-mthumb']

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        print('FAILED:', ' '.join(cmd)); print(r.stdout); print(r.stderr); sys.exit(1)
    if r.stderr.strip():
        print(r.stderr.strip())
    return r

# 1. install port (same logic as install_port.sh)
dst = os.path.join(kl, 'src', 'upc')
shutil.rmtree(dst, ignore_errors=True)
shutil.copytree(os.path.join(port, 'klipper', 'src', 'upc'), dst)
for h in ('upc_hw.h', 'upc_ipc.h'):
    shutil.copy(os.path.join(port, 'common', h), dst)
kc = os.path.join(kl, 'src', 'Kconfig')
s = open(kc).read()
if 'MACH_UPC' not in s:
    s = s.replace('    config MACH_AR100\n', '    config MACH_UPC\n        bool "Marvell 88PA6170 UPC (Sindoh DP200)"\n    config MACH_AR100\n', 1)
    s = s.replace('source "src/ar100/Kconfig"\n', 'source "src/ar100/Kconfig"\nsource "src/upc/Kconfig"\n', 1)
    open(kc, 'w', newline='\n').write(s)

# 2. kconfig
shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
env = dict(os.environ, KCONFIG_CONFIG=os.path.join(out, '.config'), KCONFIG_AUTOHEADER=os.path.join(out, 'autoconf.h'))
shutil.copy(cfg, env['KCONFIG_CONFIG'])
run([sys.executable, 'lib/kconfiglib/olddefconfig.py', 'src/Kconfig'], cwd=kl, env=env)
run([sys.executable, 'lib/kconfiglib/genconfig.py', 'src/Kconfig'], cwd=kl, env=env)
conf = {}
for l in open(env['KCONFIG_CONFIG']):
    m = re.match(r'(CONFIG_\w+)=(.*)', l)
    if m: conf[m.group(1)] = m.group(2).strip('"')
run([sys.executable, 'lib/kconfiglib/savedefconfig.py', '--kconfig', 'src/Kconfig', '--out', os.path.join(out, 'defconfig')], cwd=kl, env=env)

# 3. board links (copies on Windows)
shutil.copytree(os.path.join(kl, 'src', 'upc'), os.path.join(out, 'board'))
os.makedirs(os.path.join(out, 'board-generic'))
shutil.copytree(os.path.join(kl, 'src', 'generic'), os.path.join(out, 'board-generic', 'board'))

# 4. source list from src/Makefile + src/upc/Makefile
srcs = []
for mk in ('src/Makefile', 'src/upc/Makefile'):
    txt = open(os.path.join(kl, mk)).read().replace('\\\n', ' ')
    for m in re.finditer(r'^src-(y|\$\((CONFIG_\w+)\))\s*\+=\s*(.*)$', txt, re.M):
        if m.group(1) == 'y' or conf.get(m.group(2)) == 'y':
            srcs += m.group(3).split()
print('sources:', ' '.join(srcs))

cflags = target + ['-std=gnu11', '-Os', '-Wall', '-Wold-style-definition', '-ffunction-sections', '-fdata-sections',
          '-fno-delete-null-pointer-checks', '-mfloat-abi=soft',
          '-iquote', out, '-iquote', os.path.join(kl, 'src'), '-iquote', os.path.join(out, 'board-generic'), '-I', os.path.join(kl, 'src', 'upc', 'include')] + extra
objs = []
ctr = b''
plain = [f for f in cflags if f != '-flto']
for c in srcs:
    o = os.path.join(out, c.replace('/', '_') + '.o')
    run([zig, 'cc'] + plain + ['-c', os.path.join(kl, 'src', c), '-o', o])
    from elftools.elf.elffile import ELFFile
    with open(o, 'rb') as fh:
        sec = ELFFile(fh).get_section_by_name('.compile_time_request')
        if sec is not None:
            ctr += sec.data() + b'\0'
    if '-flto' in cflags:
        o = o[:-2] + '.lto.o'
        run([zig, 'cc'] + cflags + ['-c', os.path.join(kl, 'src', c), '-o', o])
    objs.append(o)
open(os.path.join(out, 'compile_time_request.txt'), 'w', newline='\n').write(
    '\n'.join(x for x in ctr.decode().split('\0') if x) + '\n')
run([sys.executable, 'scripts/buildcommands.py', '-d', os.path.join(out, 'klipper.dict'), '-k', os.path.join(out, 'defconfig'),
     '-t', 'zig;zig;zig;zig;zig;zig', os.path.join(out, 'compile_time_request.txt'), os.path.join(out, 'compile_time_request.c')], cwd=kl)
ctro = os.path.join(out, 'compile_time_request.o')
run([zig, 'cc'] + cflags + ['-c', os.path.join(out, 'compile_time_request.c'), '-o', ctro])
objs.append(ctro)
starto = os.path.join(out, 'start.o')
run([zig, 'cc'] + target + ['-iquote', out, '-c', os.path.join(kl, 'src', 'upc', 'start.S'), '-o', starto])
objs.append(starto)

# 5. link
ld = os.path.join(out, 'upc.ld')
r = run([zig, 'cc'] + target + ['-E', '-P', '-x', 'c', '-I', out, os.path.join(kl, 'src', 'upc', 'upc.lds.S')])
open(ld, 'w', newline='\n').write(r.stdout)
elf = os.path.join(out, 'klipper.elf')
run([zig, 'cc'] + target + extra + ['-Os'] + objs + ['-nostartfiles', '-static', '-T', ld, '-Wl,--gc-sections', '-o', elf])
binf = os.path.join(out, 'klipper.bin')
run([zig, 'objcopy', '-O', 'binary', elf, binf])
print('klipper.bin size:', os.path.getsize(binf), 'of', int(conf.get('CONFIG_UPC_ITCM_SIZE', '0x4000'), 0))
print('dict size:', os.path.getsize(os.path.join(out, 'klipper.dict')))
