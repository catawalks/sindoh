#!/bin/sh
# Fast test-kernel loop (2026-10-29): copy a uImage onto the 2 GB rescue card
# from stock Linux over the network, then stop at U-Boot, route the two SD
# pins like stock (user-approved: f8041080/84 = 0x1002, RAM-only register
# state), ext2load it and bootm. ~35 s instead of ~20 min over serial.
# Nothing is written to NAND or the U-Boot env. Needs the 2 GB card in the
# printer, stock Linux up with Klipper stopped, and the PC's HTTP server:
#   (cd /d/DP200/kernel/out && python -m http.server 8099 --bind <PC IP>)
# usage: tools/sd_kernel_boot.sh IMAGE.uimg [CAPTURE_SECONDS] [PC_IP]
set -e
img=$1; secs=${2:-60}; pc=${3:-10.10.0.85}
name=$(basename "$img")
here=$(dirname "$0")
md5=$(md5sum "$img" | cut -d' ' -f1)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-Location '$here/..'; & .\\tools\\serial_cmd.ps1 'mkdir -p /mnt/sd/kernels && wget -q http://$pc:8099/$name -O /mnt/sd/kernels/$name && md5sum /mnt/sd/kernels/$name; sync' 120" | grep -q "$md5" || { echo "copy to the card failed or md5 mismatch"; exit 1; }
py -3.15t "$here/uboot_cmd.py" COM3 --catch | tail -1
py -3.15t "$here/uboot_cmd.py" COM3 --pinmux-sd | tail -1
py -3.15t "$here/uboot_cmd.py" COM3 "mmc rescan 0" "ext2load mmc 0:1 2000000 /kernels/$name" | tail -1
py -3.15t "$here/uboot_cmd.py" COM3 --log "${TEMP:-/tmp}/${name%.uimg}_boot.bin" --bootm 2000000 "$secs"
