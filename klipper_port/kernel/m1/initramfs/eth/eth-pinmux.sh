#!/bin/sh
# eth-pinmux.sh, revision 2 (approved by the user 2026-10-29: "yes";
# m1-eth test 2 passed: PHY 0x01410dd1, link 100/Full, ~10.5 MB/s wget,
# docs/kernel/m1_eth_test2.md). ethload runs it before eth0 comes up.
#
# Revision 1 (approved 2026-10-29) routed bank 3 and pulsed the PHY reset;
# bank 3 then matched stock but MDIO still read all zeros. Revision 2 adds
# the pins the vendor table actually gives the GMAC.
#
# New in revision 2:
# 4. Bank 1 (GPIO 32-63, 0xf8041000) pin selects for pins 16-29 and 31
#    (GPIO 48-61 and 63) -> 0x00001001 (function 1), the exact stock value.
#    Evidence that this is the Ethernet RGMII + MDC/MDIO group:
#    - the vendor's gr_def_mpp_list (board_do_mpp_config, run
#      unconditionally at every stock boot) sets GPIO 48-61 and 63 to
#      function 1 with no GPIO direction or level;
#    - 14 pins = RGMII (TXC, TX_CTL, TXD0-3, RXC, RX_CTL, RXD0-3) + MDC +
#      MDIO, plus GPIO 63; they straddle GPIO 62, the PHY reset line the
#      vendor's GMAC driver pulses (mach_phyHWInit), and no code in the
#      vendor kernel image requests GPIO 48-61 or 63 by number (loadable
#      modules such as upc.ko were not scanned);
#    - U-Boot has no GMAC driver (its only network is usb_ether) and leaves
#      exactly these pins at GPIO (0x000c1000), which matches the symptom:
#      the MAC answers, MDIO reads 0.
#    Why it cannot drive printer hardware: in function 1 the pins belong
#    to the GMAC, which only drives TXD/TX_CTL/TXC/MDC toward the PHY (MDC
#    only during MDIO access, the rest only while eth0 is up). Nothing on banks 0, 2, 4, 5 or 6 (where the
#    rest of the vendor table and the printer engine pins are) is touched.
#    Today these pins are GPIO inputs (bank 1 dir 0x40000002 has only bits 1 and 30 set), so
#    nothing is driven by them now either. The direction register and every
#    other pin keep their current values.
#    Order: the pins are switched before the PHY reset is released, as the
#    vendor does, because the 88E1510 latches its configuration straps from
#    the RX pins at reset release; U-Boot's 0x000c1000 has pull bits set
#    that function 1 (0x00001001) clears, as in stock.
#
# Unchanged from revision 1 (already approved):
# 1. Bank 3 (GPIO 96-127, 0xf8043000) direction -> stock 0x00000000.
# 2. Bank 3 pin selects for pins 0-4, 6-22, 24-28 -> stock 0x00001002.
#    (Probably not Ethernet after all, but it is the stock state and was
#    harmless in test 1; kept so only one thing changes per test.)
# 3. GPIO 62 (bank 1 bit 30, PHY reset): low, output, 125 ms, high.
#
# Also fixed: the driver rebind uses plain echo (the echo -n form failed
# with "No such device" in test 1) and reports its result.
B3=0xf8043000
B1=0xf8041000

echo "eth-pinmux: before: bank3 dir $(devmem $((B3 + 8))) sel0 $(devmem $((B3 + 0x80))); bank1 out $(devmem $((B1 + 4))) dir $(devmem $((B1 + 8))) sel16 $(devmem $((B1 + 0xc0)))"

# 1. bank 3 direction
devmem $((B3 + 8)) 32 0x00000000

# 2. bank 3 pin selects
for n in 0 1 2 3 4 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 24 25 26 27 28; do
	devmem $((B3 + 0x80 + 4 * n)) 32 0x00001002
done

# 4. bank 1 pin selects: GMAC RGMII + MDC/MDIO (before the reset release)
for n in 16 17 18 19 20 21 22 23 24 25 26 27 28 29 31; do
	devmem $((B1 + 0x80 + 4 * n)) 32 0x00001001
done

# 3. PHY reset pulse on GPIO 62
bit=$((1 << 30))
out=$(devmem $((B1 + 4)))
dir=$(devmem $((B1 + 8)))
devmem $((B1 + 4)) 32 $((out & ~bit))
devmem $((B1 + 8)) 32 $((dir | bit))
usleep 125000
devmem $((B1 + 4)) 32 $((out | bit))

echo "eth-pinmux: after: bank3 dir $(devmem $((B3 + 8))) sel0 $(devmem $((B3 + 0x80))); bank1 out $(devmem $((B1 + 4))) dir $(devmem $((B1 + 8))) sel16 $(devmem $((B1 + 0xc0))) sel31 $(devmem $((B1 + 0xfc)))"
# stmmac probed at boot, before the pins were routed, and registered a PHY
# with ID 0: rebind it so MDIO rescans now that the PHY is out of reset
sleep 1
D=/sys/bus/platform/drivers/stmmaceth
[ -e $D/f9050000.ethernet ] && { echo f9050000.ethernet > $D/unbind || echo "eth-pinmux: unbind failed"; }
echo f9050000.ethernet > $D/bind || echo "eth-pinmux: bind failed"
sleep 1
echo "eth-pinmux: MDIO PHYs: $(for p in /sys/bus/mdio_bus/devices/*:*; do echo "$p $(cat $p/phy_id)"; done)"
