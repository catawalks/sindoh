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
