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
- **Still open:** NTP (Debian's busybox has no ntpd applet; done, see "Clock sync on mainline"), real touch taps.
- **Touch taps (the user at the panel):** raw ABS_MT X/Y from /dev/input/event0 at the
  four corners: TL (3480, 1010), TR (3440, 3280), BR (620, 3165),
  BL (545, 930). Through dp200_screen.py's stock calibration (u = 0.14471*y
  - 66.6, v = -0.22272*x + 856.2) they map to (80, 81), (408, 90), (391, 718)
  and (68, 735) on the 480x800 portrait screen: the right corners. The mainline
  driver's raw values match stock's, and the screen app needs no change.

## No console on the panel (2026-10-31)

The stock kernel never drew a text console on the panel: U-Boot's boot logo
stayed up until the screen app drew. The m1-full kernel had fbcon and
`console=tty0`, so the logo was wiped when simplefb registered, kernel
messages scrolled over the panel during boot, and later over the screen app
(the stopgap: init.mainline unbinds fbcon).
- **Kernel:** `variants/full.config` turns `CONFIG_FRAMEBUFFER_CONSOLE` off.
  simplefb keeps /dev/fb0 for the screen app and never touches the buffer,
  so the logo stays. The serial console (ttyS0) is unchanged.
- **Bootargs:** no `console=tty0` (and no `consoleblank`) in full.dts or the
  boot DTS files.
- **m1-debian / m1-debian-ro** now come from `variants/full.boot/*.dts`
  (build.sh step 9b), built with `VARIANT=full`; they were hand-made DTBs
  before.
- **Console on request:** the screen app's Display page has CONSOLE, which
  shows the kernel log (`dmesg -S`, which also works on stock 3.2) full screen
  until the panel is tapped.

## Clock sync on mainline (2026-10-31)

Debian's busybox has no ntpd applet, so init.mainline's one-shot NTP did
nothing ("ntpd: applet not found"). It now runs `/dp200/dp200-sntp.py`
(install/printer): SNTP in Python's standard library, so no new packages. It
retries for up to 120 s while the network comes up, sets the clock, and saves
it to the RTC with `busybox hwclock -w -u`. Tested on the printer: the clock
was 629 s fast (RTC drift since the last set). After the sync, the system
clock and /sys/class/rtc/rtc0 agree with the PC.

## Boot logo on mainline: confirmed (2026-10-31)

The owner watched a mainline boot (m1-debian 695966b6, loader by serial).
The logo stayed up with no text, but with **no loading bar**. The bar is
drawn by the vendor kernel's panel driver: `mv61tft.boot_time=17` and
`mv61tft.bar_color=${bar_color}` in the stock bootargs (uboot_facts.txt). It
is not drawn by U-Boot, so mainline needs its own bar. Not done yet.

The screen app's waiting page showed `[Errno 111] Connection refused` until
Moonraker listened. It now reads "Moonraker is starting (not answering
yet)" (err_text).

## Boot progress bar on mainline (2026-10-31)

`src/drivers/video/fbdev/dp200-bootbar.c` (CONFIG_DP200_BOOTBAR, patch 0009)
draws the bar the vendor's `rodin_progress_bar` (mv61tft) draws:
- **Look:** a 14 x 280 px rounded outline, filled one line at a time over
  `boot_time` s. It stays full at the end. White for `bar_color=0`, black
  for 1.
- **Settings:** `bar_color`, `boot_time`, `bar_shift_x` and `bar_shift_y`
  come from the U-Boot env (MTD u-boot-env, read-only; the CRC'd env is
  4 KB). The kernel command line can override them as
  `dp200_bootbar.{bar_color,boot_time,shift_x,shift_y}`.
- **Position:** the vendor's bar is not centered. It spans screen x 90-369 of
  480, so 90 px on the left and 110 px on the right, at y 480-493 of 800. The
  default `bar_shift_x` is +10, which centers it. 0/0 is the stock spot; the
  stock kernel ignores both variables.
- **End:** the screen app writes 1 to
  /sys/module/dp200_bootbar/parameters/stop before its first frame. That
  waits for the thread, so the bar never draws over the app.
- **Tested** (m1-debian ed50a2af, before the shift): "white bar, 17 s" at
  1.3 s, stopped at 23 s. The owner saw the bar on the panel.

init.mainline's reboot/power-off path called `reboot -f` / `poweroff -f`,
which the Debian root doesn't have; it now uses BusyBox's.

## Fast boot from raw SD sectors (2026-10-31, the owner approved the write)

U-Boot 2011 can't `ext2load` from the 4 GB card's ext4, but it can
`mmc read` raw blocks. The card has one partition, starting at sector 8192.
So the gap in front of it now holds `m1-debian.uimg` (build.sh makes a
.uimg for each boot DTS), from **sector 64** (5986 sectors, about 1 MB
spare).
- **The gap wasn't empty:** sectors from about 4033 held leftover data
  (incrementing 32-bit words, from an earlier formatting; no partition uses
  it). All of sectors 1-8191 were saved first to
  `/var/backups/sd_gap_sectors_1-8191.bin` on the card's root (md5 84e3ceea).
- **Install:** `tools/sd_raw_install.sh [IMAGE]`, from either kernel. It
  refuses if the image would reach partition 1, and reads the image back to
  compare the md5.
- **Boot:** `tools/sd_raw_boot.sh`. It stops the stack, catches U-Boot, sets
  the SD pins (`--pinmux-sd`, RAM only), runs `mmcinfo` and
  `mmc read 2000000 40 <blocks>`, compares the CRC with the local build,
  then `bootm`. uboot_cmd.py allows `mmc read` only into the upload window.
- **First boot:** the image was read and its CRC matched (c1088c1c). Init
  ran at 5.3 s and the screen app at 23 s; Klipper was ready, and NTP set the
  clock (it was 18.8 s off). About 1 minute from Linux to Linux, instead of
  about 13 with the serial loader.
- **Unclean stock reboot:** stock's catch reboot leaves the ext4 unclean, so
  mainline replays the journal ("recovery complete"). The stock-side tool
  now stops the stack first; the card stays mounted, though.
- **Not automatic yet:** U-Boot still needs the commands typed each boot.
  Making it the default boot is the owner's saveenv decision
  (docs/printer_checks.md).
