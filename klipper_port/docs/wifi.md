# WiFi in Klipper mode

## Why we need our own

The stock `/etc/profile` loads the WiFi driver (Marvell 88W8782, `mlan` +
`usb8xxx`) and starts `wpa_supplicant` (v2.5, wext) **before** the
`/DEBUG_MACHINE` check, but with only a placeholder config (`MV-Guest`).
Joining the owner's network is done by the stock app at runtime, from the
networks saved in `/app/nvram/karas.db` (table `RECD_SSIDBOOK`). In Klipper
mode the stock app doesn't run, so nothing would join the network.

**Don't restart `wpa_supplicant`.** After a restart the driver returns 0
scan results for a while (tested 2026-10-21). A driver reload (`rmmod usb8xxx
mlan`, `insmod` from `/lib/modules/8782`) brings it back after ~15 s. So we
keep the stock daemon and talk to its control socket.

## Pieces

| File | Where it runs | What it does |
|---|---|---|
| `install/printer/dp200-wifi.sh` | stock side, from dp200-start.sh | First run: writes `<root>/etc/dp200/wpa_supplicant.conf` (mode 600) from the stock saved networks. **Only secured ones** (no auto-joining open hotspots); the network the radio is on gets top priority. Starts `wpa_cli -a dp200-wifi-action.sh`. |
| `install/printer/dp200-wifi-action.sh` | stock side | On every CONNECTED event: restarts `udhcpc`, so a new network gets an address. |
| dp200-start.sh | stock side | Bind-mounts `/var/run/wpa_supplicant` into the chroot (`<root>/run/wpa_supplicant`). |
| `install/display/dp200_wifi.py` | chroot (root) | Control-socket client. The client socket is in the abstract namespace, so the daemon outside the chroot can reply. `apply` (rc.dp200 start) loads the saved networks into the daemon, keeping the current connection if it's one of them. Also scan / connect / forget for the screen. Never calls SAVE_CONFIG (that would write the stock NAND file); it maintains our config file itself. |
| `install/display/dp200_screen.py` | chroot (root) | System → **WIFI** page. Also reachable from the "Waiting for Klipper" and error pages. |

## Touch-screen flow

- **WIFI:** shows network, address, state and the number of saved
  networks. Buttons: SCAN, HIDDEN, FORGET (asks first), BACK.
- **SCAN:** networks strongest first, 5 per page (MORE), with signal bars and
  lock/open.
  - A **secured** network opens the keyboard for its password.
  - An **open** network asks first: "anyone can listen in".
- **Keyboard:** digits row, QWERTY, a symbols page (all printable ASCII),
  one-shot SHIFT, space, DEL, SHOW/HIDE, CANCEL, CONNECT. Passwords must be
  8–63 characters, which is refused on the spot otherwise.
- **Connecting:**
  1. the network is added and selected; we wait up to 30 s for
     `wpa_state=COMPLETED`;
  2. on success it's saved with the top priority;
  3. on failure ("wrong password?") it's removed and the saved networks are
     re-applied, so the printer goes back to its previous network.
- **HIDDEN:** type the network name, then the password. An empty password
  means an open network.

Tests: `install/display/test_dp200_wifi_screen.py` simulates taps against a
fake backend (25 checks).

## Not done yet

- A setup hotspot when no saved network is in range (the chip has
  `uap0`; stock `/etc/init.d/uap_start.sh` shows how).
- A `wifi.txt` on the USB install stick.
- WEP and WPA-Enterprise are not supported (WPA/WPA2-PSK and open only).

## Changes after the first real test (2026-10-22)

- **Scanning without dropping the network:** a standard `wpa_supplicant`
  SCAN made the Marvell driver leave the network for ~10 s. The screen now
  runs the driver's own user scan
  (`mlanutl mlan0 setuserscan keep=1 dur=30`, ~2 s, association kept;
  `wpa_supplicant` picks up the results). `mlanutl` is copied from the stock
  firmware into the chroot at boot (`/run/mlanutl`); it isn't shipped.
- **DHCP:** the action script renews (SIGUSR1) instead of restarting
  `udhcpc`, so a re-association doesn't drop the IP address. The screen app
  runs a watchdog that forces a re-association after 60 s associated
  without an address.
- **apply()** gives a kept (connected) network its saved priority.
- **UI:**
  - pressed buttons light up and their label shifts down 2 px;
  - a padlock icon on the signal bars replaces the "lock"/"open" words;
  - "Hidden network…" is the last row of the network list (no HIDDEN
    button on the WiFi page);
  - ▲/▼ buttons with a page counter replace MORE.
- **Real test by the user:** scan, keyboard and connect to Niholedotcom
  worked; saved with priority 21.

## 2.4 GHz only (2026-11-14)

The WiFi module is an LG Innotek TWFM-M311D (88W8782, USB). The chip is
dual-band and says so to access points, but the module has no antenna
connector and no usable 5 GHz antenna: 8 ft from an access point it measured
-29 dBm on 2.4 GHz and -78 dBm on 5 GHz, associated on 5 GHz and never got an
address. `dp200_wifi.py` therefore gives every saved network
`freq_list` and `scan_freq` for channels 1-14 (in the saved file and in the
running daemon) and leaves 5 GHz networks out of the scan list. An SSID that
exists only on 5 GHz cannot be joined.

## How stock handles the bands (read on the dev printer, 2026-11-17)

Read on the stock system (Sindoh update 200730_2) while it held the
preferred network, read-only (`iwpriv` getters, `/proc/mwlan`, a scan):

- Driver: Marvell's own `mlan` + `usb8xxx` (USB8782-14.69.12.p50,
  "FP69"), firmware `mrvl/usb8782_uapsta.bin`, wpa_supplicant `-Dwext`.
- `bandcfg` 31 = b/g/a/n all allowed: stock does not block 5 GHz either.
  A scan found 15 cells, 5 of them 5 GHz (channel 40, all -77 dBm, the
  same weak antenna). Before the update its supplicant once associated
  on the access point's 5 GHz radio (-77 dBm) and lost it again.
- `regioncode` 48 (0x30, ETSI/Europe); 802.11d off; `iwlist freq`
  lists channels 1-11.
- Power save: IEEE power management on, `deepsleep` on (100 ms),
  `pscfg` 0 1 0 0 10 1000 1. Ours runs with power save off.
- The screen's list showed 6 entries: named networks with a strong
  signal, one row per access point (an SSID on two access points shows
  twice). Hidden networks and everything at -73 dBm or weaker (all the
  5 GHz cells and the distant neighbors) were left out. All 5 GHz
  cells here are weak, so this does not tell whether the app filters by
  band or by signal.

## Power save on with our kernel (2026-11-17)

With power save off, the access point dropped our kernel every 91-95 s;
with it on, no drop in hours. So our kernel now runs with it on:
init.mainline sets it at boot and dp200-wifi-action.sh after every
connection, on every printer; the USB-stick install on the stock
kernel (dp200-start.sh) turns it on too (owner: stock runs it that
way). It had been off since 2026-11-02, after reason 15 drops on the
dev printer, then running the stock kernel with the stick install. `/etc/dp200/wifi_power_save` holding `on` or
`off` overrides both.
