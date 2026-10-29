#!/bin/sh
# Ethernet fast path (2026-10-29): boot the m1-eth loader from the 2 GB
# rescue card, which then fetches the test kernel from the PC over Ethernet
# (~10 MB/s) and kexecs it. The card only needs m1-eth.uimg once (copy it
# with tools/sd_kernel_boot.sh m1-eth.uimg). After that, each test is: publish
# the image as next-zImage-dtb.bin, catch U-Boot, route the SD pins
# (user-approved, RAM-only), ext2load the loader, check its CRC against the
# local build, bootm. The loader's init runs ethload after a 3 s countdown
# (Enter on the console stops it). Nothing is written to NAND or the U-Boot
# env, and no setenv: the PC address and file name are built into m1-eth
# (build.sh: ETHLOAD_PC, ETHLOAD_PORT, ETHLOAD_FILE).
# Needs the 2 GB card in the printer, a Linux shell on the console (stock with
# Klipper stopped, or an m1 kernel), the Ethernet cable, and the PC's server:
#   (cd /d/DP200/kernel/out && python -m http.server 8099 --bind <PC IP>)
# usage: tools/eth_kernel_boot.sh IMAGE [CAPTURE_SECONDS] [PC_IP]
#   IMAGE: m1*-zImage-dtb.bin, or the .uimg next to one
set -e
img=$1; secs=${2:-90}; pc=${3:-10.10.0.85}
[ -n "$img" ] || { echo "usage: $0 IMAGE [CAPTURE_SECONDS] [PC_IP]"; exit 1; }
case $img in *.uimg) img=${img%.uimg}-zImage-dtb.bin ;; esac
[ -f "$img" ] || { echo "$img: not found"; exit 1; }
out=$(cd "$(dirname "$img")" && pwd)
here=$(dirname "$0")
loader=$out/m1-eth.uimg
[ -f "$loader" ] || { echo "$loader: not found (VARIANT=eth build.sh)"; exit 1; }

# 1. publish the test kernel under the name the loader fetches
# and its DTB as next.dtb (kexec-tools drops an appended DTB: netload
# passes it with --dtb)
if [ "$(basename "$img")" != next-zImage-dtb.bin ]; then
	dtb=${img%-zImage-dtb.bin}.dtb
	[ -f "$dtb" ] || { echo "$dtb: not found"; exit 1; }
	cp "$img" "$out/next-zImage-dtb.bin"
	cp "$dtb" "$out/next.dtb"
fi
echo "next: $(basename "$img"), md5 $(md5sum "$out/next-zImage-dtb.bin" | cut -d' ' -f1)"
for f in next-zImage-dtb.bin next.dtb; do
	curl -sf -o /dev/null "http://$pc:8099/$f" ||
		{ echo "no HTTP server at $pc:8099 serving $out/$f"; exit 1; }
done

# 2. U-Boot: load the loader from the card and check it is this build
size=$(wc -c < "$loader")
crc=$(py -3.15t -I -c "import sys, zlib; print('%08x' % zlib.crc32(open(sys.argv[1], 'rb').read()))" "$loader")
py -3.15t "$here/uboot_cmd.py" COM3 --catch | tail -1
py -3.15t "$here/uboot_cmd.py" COM3 --pinmux-sd | tail -1
res=$(py -3.15t "$here/uboot_cmd.py" COM3 "mmc rescan 0" \
	"ext2load mmc 0:1 2000000 /kernels/m1-eth.uimg" \
	"crc32 2000000 $(printf %x "$size")")
echo "$res" | tail -3
if ! echo "$res" | grep -qi "==> *$crc"; then
	echo "the card's /kernels/m1-eth.uimg is missing or not this build (crc $crc):"
	echo "resetting to stock; then run tools/sd_kernel_boot.sh $loader"
	py -3.15t "$here/uboot_cmd.py" COM3 --reset | tail -1
	exit 1
fi

# 3. boot it; the loader fetches next-zImage-dtb.bin and kexecs it
py -3.15t "$here/uboot_cmd.py" COM3 --log "${TEMP:-/tmp}/eth_$(basename "${img%-zImage-dtb.bin}")_boot.bin" \
	--bootm 2000000 "$secs"
