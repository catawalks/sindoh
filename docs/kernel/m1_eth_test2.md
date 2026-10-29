# m1-eth test 2 (2026-10-29): mainline Ethernet works

Image m1-eth.uimg md5 c6f4addfc4eda882a67416220dbccb8d, booted through
tools/sd_kernel_boot.sh. Before running /etc/eth-pinmux.sh, wrote by hand the
bank 1 pin selects proposed in eth-pinmux.sh.proposed (the user approved them):
GPIO 48-61 and 63 (0xf80410c0..0xf80410f4 and 0xf80410fc) set to 0x00001001,
the stock value. GPIO 62's select stays 0x000c1000.

Result:
- PHY found at MDIO address 0 on stmmac-1: ID 0x01410dd1 (Marvell 88E1xxx),
  Generic PHY driver, rgmii mode
- "Link is Up - 100Mbps/Full"; carrier 1, speed 100
- ping 10.10.0.1 (router) OK, 2-7 ms. Ping to the PC (10.10.0.85) gets no reply
  because the Windows firewall drops ICMP
- wget of a 1,221,778 B file from the PC's http.server: md5 correct
- wget of 2,203,158 B in 0.21 s, about 10.5 MB/s (line rate)
- RX 857 / TX 359 packets, 0 errors

So the missing piece in test 1 was the bank 1 group (the RGMII + MDC/MDIO pins).
Bank 3 alone was not enough.
