#!/bin/sh
# nand variant: read-only checks (patch 0006, CONFIG_MTD_RAW_NAND_READ_ONLY:
# ROM, -EROFS paths, command-byte guard; no BBT, no bad-block markers read)
dmesg | grep -i 'nand\|mtd\|marvell-nfc\|read-only'
cat /proc/mtd
echo "--- partition flags (must not contain 0x400 = writeable):"
for d in /sys/class/mtd/mtd[0-9]; do
	echo "  $(basename $d) $(cat $d/name) type=$(cat $d/type) flags=$(cat $d/flags) size=$(cat $d/size) writesize=$(cat $d/writesize) erasesize=$(cat $d/erasesize)"
done

# mtd0 per 128 KiB block. ECC is off (raw reads), so each block is graded:
#   COR  = equals the ECC-corrected stock dump (nanddump, nand_images/mtd0.bin)
#   RAW  = equals the raw T48 programmer dump (same uncorrected bitflips)
#   diff = neither (other or new bitflips)
# Blocks 55-63 are erased (0xff) and equal in both. 40 of 64 blocks carry
# raw bitflips in the T48 dump (73 bits in total).
COR="acde4a72 9fa350bc 541c5b5d 1f049187 955f23d4 73310fe7 b7765781 26b1a09a 7453664c 7066d4bb 7f2953e1 c1127ce3 37184f2d 02e5aa61 c40d050a 7bcc28f8 e51e2b7b 1b0509d0 75f906d0 6c089641 952cfe3d b46fbe86 0934e7d5 be01f1e7 966f0c18 d71d40fc 041a816f cc0eb6eb daf806ac effc46eb 9c4ca716 4fd915cb 713c33d1 578575e5 83484f9d e3e50404 12655ab5 ca81dcad e7dd8af0 06960621 33dcb1db fd673b2a 1e758623 92d7c511 bc5f6a83 dfd8dff4 cca09b38 6ba638e5 9234745e 44e04012 a08c9687 de43212a 3948bf6f b81aea63 3e71e40b 41d2e2c0 41d2e2c0 41d2e2c0 41d2e2c0 41d2e2c0 41d2e2c0 41d2e2c0 41d2e2c0 41d2e2c0"
RAW="a0eee630 6610d7c1 541c5b5d 59ad18c8 4aa17e52 b8cf89cc a548560d e053bb7c 1f1b5b46 7066d4bb af26a7a3 977260e3 37184f2d 99ec8b06 ea63c703 f82acc84 ede830ad 2f5fc508 240256a5 6c089641 952cfe3d b46fbe86 e19a2bd8 75ea696a 966f0c18 d71d40fc 75aa89d5 3422990e daf806ac 43c680af 9c4ca716 e37af7e2 4dc7e7a9 9d5ad745 2066a75b 34ea7b8b 12655ab5 f88575a8 e7dd8af0 06960621 cfb112c7 db522ddf b7ca0e6a 53b8c91b 8656c34b 2530bbf7 cca09b38 97198477 d1507987 19838ff0 fbae1221 68733260 132a3820 b81aea63 e148526a 41d2e2c0 41d2e2c0 41d2e2c0 41d2e2c0 41d2e2c0 41d2e2c0 41d2e2c0 41d2e2c0 41d2e2c0"
echo "--- mtd0 by 128 KiB block (raw reads):"
i=0 ncor=0 nraw=0 ndiff=0 line=
set -- $RAW
for c in $COR; do
	r=$1; shift
	h=$(dd if=/dev/mtd0 bs=131072 skip=$i count=1 2>/dev/null | md5sum | cut -c1-8)
	if [ "$h" = "$c" ]; then g=COR; ncor=$((ncor + 1))
	elif [ "$h" = "$r" ]; then g=RAW; nraw=$((nraw + 1))
	else g=diff; ndiff=$((ndiff + 1)); fi
	line="$line $i:$g"
	i=$((i + 1))
done
echo "$line"
echo "--- mtd0 blocks: $ncor COR, $nraw RAW, $ndiff diff (COR on the 24 clean blocks proves the read path)"
echo "--- mtd3 raw md5: $(dd if=/dev/mtd3 bs=131072 2>/dev/null | md5sum | cut -d' ' -f1) (stock ECC-corrected: 8357ce02..., the Klipper test boot logo of 2026-10-27; raw may differ by bitflips)"
