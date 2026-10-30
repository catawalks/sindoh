# Wi-Fi join test 1 (2026-10-29): mainline Wi-Fi works

- m1-net (uniprocessor, 68a96768): the 8782 firmware loads ("WLAN FW is
  active"), then the first command (0xa9) times out and the driver unregisters
  the card. This happens through the fast path and through a direct U-Boot bootm
  from the SD card alike, and with Ethernet effectively off (PHY not routed).
  Every Wi-Fi run that worked was an SMP kernel, so it's not the DDR drain.
- m1-net-smp (d1826127, the DDR drain on), through the Ethernet fast path:
  firmware loads, mlan0 comes up, and a passive scan lists the nearby networks
  (names and BSSIDs are not recorded here).
- The user ran `wifi-join` on the serial console and typed the credentials. Nothing was logged.
  - `iw dev mlan0 link`: connected, signal -22 to -25 dBm, tx 65 Mb/s MCS 7,
    rx 72.2 Mb/s.
  - DHCP lease 10.10.0.21 from 10.10.0.1, but **udhcpc didn't apply it**.
    Running /usr/share/udhcpc/default.script by hand (interface/ip/subnet/router
    set) did. To be fixed in the image.
  - With eth0 down: router ping 3/3, 2.5-17 ms. wget of 2.2 MB from the PC in
    0.54 s (~4 MB/s), md5 correct.
- Left with `rm -f /tmp/wpa.conf; reboot -f` back to stock.

Follow-ups: build m1-net as SMP by default, and fix udhcpc not running its
default.script.
