Creating 7 MTD partitions on "mv61x0_nand":


/dev/mtd0 - `0x000000000000-0x000000800000` : "kernel" - u-boot & kernel - pa6170_karas_nand.bin or pa6170_rodin_nand.bin

/dev/mtd1 - `0x000000800000-0x000000820000` : "u-boot-env"

/dev/mtd2 - `0x000000820000-0x0000008a0000` : "bbt"

/dev/mtd3 - `0x0000008a0000-0x0000009a0000` : "boot-logo" - boot-logo images - boot-logo.bin or boot-logo_rodin.bin

/dev/mtd4 - `0x0000009a0000-0x0000011a0000` : "backup" - attached mtd4 to ubi1

/dev/mtd5 - `0x0000011a0000-0x00000d9a0000` : "recovery"

/dev/mtd6 - `0x00000d9a0000-0x000020000000` : "filesystem" - root filesystem - nandrootfs.ubifs (mounted via UBI /dev/ubi0 **check system_recovery.sh**)
