# Booting the Debian root on mainline (prepared offline, 2026-10-30)

## The card rule comes first

From the start of the mainline work, the user's rule has been that a
mainline kernel only ever sees the **2 GB rescue card**, never the **4 GB
working card** that holds the Debian root. Booting the Debian root means
lifting that rule for the 4 GB card. That is the user's decision, asked
directly; nothing below runs before it. Until then, `sdroot-test` (which
refuses cards over 3 GB) covers the 2 GB card.

## Images (same kernel, different bootargs)

| Image | What it does |
|---|---|
| `m1-full` | Initramfs userspace (BusyBox), as before |
| `m1-debian-ro` | Mounts **/dev/mmcblk0p1 read-only** as the root, with `rootflags=noload` (no ext4 journal replay, which would write) and `init=/bin/sh`: a root shell on the console, no services, no Klipper, nothing started |

`rdinit=/nonexistent` makes the kernel skip the built-in initramfs and mount
`root=` instead. The kernel is `m1-full` with these additions:
- **Userspace basics** a Debian root needs, which tinyconfig strips: MULTIUSER, epoll/signalfd/timerfd/eventfd, inotify, file locks, tmpfs, SysV IPC, AIO, membarrier, packet sockets and IPv6.
- **devtmpfs automount**, so `/dev/console` exists before init.
- **The proven blocks**: SD, UPC with its pads behind the safety check, read-only NAND/UBI, Wi-Fi, RTC.

## Step D1: read-only shell from the Debian root (needs the card OK)

1. The user swaps in the 4 GB working card.
2. Run `tools/eth_kernel_boot.sh D:/DP200/kernel/out/m1-debian-ro-zImage-dtb.bin`. The fast-path loader itself lives on the 2 GB card, so the cards need a plan: copy `m1-eth.uimg` to the 4 GB card's root (/kernels), or put the loader in RAM via serial.
3. **Expected:** "VFS: Mounted root (ext4 filesystem) readonly", then a `#` prompt from the Debian `/bin/sh`.
4. **Read-only checks:** `cat /etc/os-release`, `mount`, `ls /lib/firmware/mrvl`, `python3 -V`, `ls /home/klipper`. Leave with `reboot -f` (the BusyBox reboot needs a running init).
5. **Nothing is written.** The root is mounted ro, the journal isn't replayed, and no service runs.

## Step D2: the real init (later, with the user)

`init=/etc/dp200/init.mainline` (install/rootfs/etc/dp200/init.mainline)
**remounts / read-write** and runs `rc.dp200 start`, the full Klipper stack
with heaters and motors. It needs the user present and their OK.

Things to settle first:
- **Wi-Fi:** it uses Debian's wpa_supplicant with `/etc/dp200/wpa_supplicant.conf`, which holds the credentials; it's never published.
- **The touch device** is `/dev/input/event0`, and the touchscreen driver itself is still pending (docs/kernel/touch_bu21029.md).
- **Power-off:** `rc.dp200 stop` must hold the UPC cores before reboot or poweroff, as init.mainline's traps do.
- **The RTC** keeps time across reboots on mainline now (vendor setup on). `hwclock -w` needs `marvell,set-time`, which is off until the user OKs it.

## Step D1 result (2026-10-30 evening): the Debian root runs on mainline, read-only

The user lifted the card rule for this read-only test and swapped in the 4 GB card.
- **U-Boot can't load from the 4 GB card:** its ext4 uses extents, which U-Boot
  2011's ext2 reader can't follow ("File not found" for a file that exists).
  The SD fast path only works with the 2 GB card. With the 4 GB card in, the
  m1-eth loader goes in over the serial uploader (10:45), followed by
  `uboot_cmd.py --pinmux-sd`.
  Forgetting --pinmux-sd once left the kernel at "Waiting for root device"
  (no card detected). A serial BREAK + SysRq `b` rebooted it.
- **With the pads:** the loader fetched m1-debian-ro (21c8d519) and kexec'd it.
  "mmcblk0: mmc0:59b4 SD 3.68 GiB", "mounted filesystem ... ro without
  journal", "VFS: Mounted root (ext4 filesystem) readonly", "Run /bin/sh as
  init process".
- **Read-only checks:** Debian GNU/Linux 13 (trixie) on 6.18.59, Python
  3.13.5, and /home/klipper has klipper, klippy-env, moonraker, moonraker-env,
  mainsail and printer_data. **/lib/firmware/mrvl is missing**: the 8782
  firmware has to be added to the root for mainline Wi-Fi (Wi-Fi failed to
  start in this boot: cmd 0xa9 timeout).
- Left with SysRq `b`. Nothing on the card was written by mainline; the only
  write was the loader copy in /kernels from stock, which was removed again.

## D2 preparation (offline, 2026-10-30 night)

### Images, all with the same m1-full kernel

| Image | bootargs (beyond the console) | Use |
|---|---|---|
| `m1-debian-ro` | `root=/dev/mmcblk0p1 rootwait ro rootflags=noload ubi.mtd=filesystem rdinit=/nonexistent init=/bin/sh` | D1 again, read-only |
| `m1-debian` | `root=/dev/mmcblk0p1 rootwait ro ubi.mtd=filesystem rdinit=/nonexistent init=/etc/dp200/init.mainline` | **D2: read-write root plus rc.dp200 (Klipper, heaters, motors). Only with the user present and their OK** |

The m1-full kernel now sets the SD and Ethernet pads itself, through gpio1's
board setup with the user-approved values: SD pins 0/1 = 0x1002, RGMII +
MDC/MDIO pins 16-29 and 31 = 0x1001, and GPIO 62 (PHY reset) high. A boot
straight from U-Boot therefore no longer needs `--pinmux-sd` or the eth
loader's script. `ubi.mtd=filesystem` attaches the stock NAND root at boot.
It is read-only, since the MTD has no MTD_WRITEABLE.

### 8782 firmware into the root (never published)

- **Stock side:** `install/printer/dp200-start.sh` now copies
  /lib/firmware/mrvl/usb8782_uapsta.bin into the Debian root when it is
  missing or different. It runs at every stock boot, next to the existing
  mlanutl copy.
- **Mainline side:** `init.mainline`, when the file is missing, mounts the
  stock UBIFS read-only (ubi0:filesystem, attached by the kernel), copies the
  file, unmounts, and re-enumerates the 8782 (USB `authorized` 0/1). mwifiex
  then retries the download it failed at boot.

### init.mainline / helpers review (fixed)

| Finding | Fix |
|---|---|
| `dp200-wifi.sh` checks for a running supplicant with `ps \| grep`. Debian's procps `ps` only lists the current terminal's processes, so it would start a second, `-Dwext` supplicant next to init.mainline's nl80211 one | `pidof` first (stock BusyBox has it too), `ps` as the fallback; `ps -ef` for the wpa_cli check |
| `dp200-powerkey.sh` shuts down with the stock-side `dp200-start.sh stop`, which unmounts the chroot's mounts. With ROOT=/ that would hit the real root | With ROOT=/ it signals PID 1 instead (TERM = reboot, USR2 = poweroff). init.mainline's traps run `rc.dp200 stop` (UPC cores held), remount / read-only and reboot or power off |
| The power key reads GPIO 187 (0xf8045000 bit 27) with `devmem` | Works on mainline (the input register shows the pad level whatever its function). Needs BusyBox `devmem` in the root, which init.mainline already lists |
| cdc-acm | Built into m1-full: nothing to insmod. rc.dp200 has no insmod |
| upctool | /usr/local/bin/upctool with /dev/upc0/1 and /dev/mem for DTCM. All present on mainline (test 1/2 and the motion test used the same) |
| `iwpriv regioncode` in dp200-wifi.sh | wext-only; it fails quietly on mwifiex (stderr to /dev/null), harmless |
| Stock Wi-Fi import (/app/nvram/karas.db) | Only when wpa_supplicant.conf is missing; on mainline the conf written under stock is used |
| `mount -o remount,rw /` | Works with `m1-debian` (root `ro` without noload). With `m1-debian-ro` (noload) it would fail, as intended |

Still open for D2:
- the touchscreen driver (docs/kernel/touch_bu21029.md) and GPIO interrupts;
- RTC set_time (`marvell,set-time`);
- the UPC output pads are applied by the kernel, but heat and motion stay the user's call at each step.

## Step D2 (2026-10-30 night, the user approved): the full Klipper stack runs on mainline

- **Card prep from stock:** updated init.mainline, rc.dp200, dp200-start/
  mounts/wifi/powerkey.sh, dp200_screen.py and cdc-acm.ko deployed, with a
  `.bak` of each old file. The 8782 firmware was copied from stock's
  /lib/firmware/mrvl into the root.
- **First D2 boot:** init.mainline ran, the UPC firmware loaded and "started:
  web UI on port 80, moonraker on 7125". But there was no network: the root
  had no `ifconfig`, `busybox`, `wpa_supplicant` or `wpa_cli` (the stock side
  always provided them). Left with SysRq s/u/b.
- **Fix (the user approved):** `apt-get install --no-install-recommends busybox
  wpasupplicant` in the root (Debian trixie armel, from stock with internet);
  symlinks /usr/local/bin/{ifconfig,route,udhcpc,ntpd} -> busybox (Debian's
  busybox package installs no applet links); the m1 udhcpc event script as
  /etc/udhcpc/default.script and /usr/share/udhcpc/default.script.
- **Second D2 boot (loader by serial, m1-debian 7533df00):** eth0 DHCP 10.10.0.9.
  **Moonraker** API 1.5.0, klippy_connected, no failed components. **Klipper
  "Printer is ready"** (software 9cb9975-dirty, 2-core ARMv7, as user klipper):
  extruder 26.49 °C / target 0, bed 19.27 °C / target 0, no axes homed.
  **Mainsail** on port 80: HTTP 200. **Webcam** snapshot: 200, 13.8 KB.
- **Not yet:** Wi-Fi (mlan0 has no address; to check in dp200-init.log), the
  touchscreen driver (BU21029, pending), and RTC set_time (off).

## D2 round 2 (2026-10-31 ~03:00 UTC): Wi-Fi, webcam, touch device and RTC set_time

m1-debian 6a60c25f (909c509), loader by serial, init.mainline with the device
groups, the serial root shell and nl80211 Wi-Fi.

- **Wi-Fi works:** "WLAN FW is active", no 0xa9 timeout. mlan0 joined the
  user's saved network (wpa_state COMPLETED, IP 10.10.0.21, the same address
  as on stock). eth0 10.10.0.144. **Klipper is "ready" over Wi-Fi.**
- **Webcam works:** /dev/video0 root:video 660, ustreamer online at 15 fps,
  and a snapshot (71.7 KB) shows the bed with the head lamp on (the earlier
  NO SIGNAL came from root-only devtmpfs nodes).
- **Touch:** "input: bu21029 as .../i2c-2/2-0040/input/input0"; the screen
  app (dp200_screen.py) runs as root on /dev/input/event0. Real taps not yet
  tested (needs the user at the panel).
- **RTC:** vendor setup, "set_time enabled", system clock set from the RTC
  (2026-10-31T03:01:44Z); /sys/class/rtc/rtc0 counts. (The user approved set_time.)
- **Accelerometer:** /dev/ttyACM0 root:klipper 660.
- **Still open:** NTP (Debian's busybox has no ntpd applet), real touch taps.
- **Touch taps (the user at the panel):** raw ABS_MT X/Y from /dev/input/event0 at the
  four corners: TL (3480, 1010), TR (3440, 3280), BR (620, 3165),
  BL (545, 930). Through dp200_screen.py's stock calibration (u = 0.14471*y
  - 66.6, v = -0.22272*x + 856.2) they map to (80, 81), (408, 90), (391, 718)
  and (68, 735) on the 480x800 portrait screen: the right corners. The mainline
  driver's raw values match stock's, and the screen app needs no change.
