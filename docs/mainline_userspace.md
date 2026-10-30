# Running our Klipper stack on the mainline kernel (audit, 2026-10-29)

Today, stock Linux 3.2 boots from NAND and its BusyBox side runs
`install/printer/dp200-start.sh`, which enters our Debian root (SD card or
NAND UBI volume) as a chroot and starts everything there through
`install/rootfs/etc/dp200/rc.dp200`. On mainline there is no stock side, so
the Debian root has to boot directly, and everything the stock side does today
has to come from the kernel or from Debian.

## What already works unchanged

| Piece | Why it works on mainline |
|---|---|
| `upctool load/stop/safe/info` | Same ioctl numbers as upc.ko (`mv61x0-upc.c` uses the vendor values), same `/dev/upc0` / `/dev/upc1` names. `load` ran on mainline (UPC test 2) |
| `upctool bridge` (klippy's two serial ports) | Uses PTYs (`UNIX98_PTYS=y`) and the DTCM through `/dev/mem` (`DEVMEM=y`). The DTCM search falls back to 0xf9280000, which is where `upctool info` found it on mainline |
| Klipper MCU firmware and config | Unchanged: the same firmware runs on the UPC cores; endstop pins `xena42/43/44` read correctly since the bank 5 pad fix (test 2c, now in the driver) |
| Power button (`dp200-powerkey.sh`, screen `PowerKey`) | Reads GPIO bank 5 bit 27 through `/dev/mem`; the pad stays GPIO on mainline |
| Network names | mwifiex names the Wi-Fi interface `mlan0` like the vendor driver, and Ethernet is `eth0` |
| Wi-Fi scan in `dp200_wifi.py` | Falls back to wpa_supplicant `SCAN` when Marvell's `mlanutl` is missing (it will be: `mlanutl` only works with the vendor driver) |
| Webcam shim (`v4l2_time32_shim.so`) | Kept: mainline is built with `COMPAT_32BIT_TIME`, so the time32 v4l2 ioctls still work, and the shim's MJPEG end-marker repair is needed on any kernel |
| Touch event format | `input_event` is 16 bytes on 32-bit ARM with either kernel (`'<llHHi'`) |

## Changed tonight (work on both kernels)

| File | Change |
|---|---|
| `install/display/dp200_screen.py` | Framebuffer pages come from `/sys/class/graphics/fb0/virtual_size`: stock has two (800x960), mainline simplefb one (800x480, 752 KiB reserved), and writing a second page would run past its end. Touch device: `/dev/event0` (stock) or `/dev/input/event0` (mainline) |
| `install/display/touch_cal.py` | The same touch-device lookup |
| `install/rootfs/etc/dp200/rc.dp200` | The screen starts when either touch-device name exists |

Tested offline: one-page and two-page framebuffers both draw correctly, with
nothing written past the end. The full `test_dp200_screen.py` needs a live
Moonraker, so it runs on the printer later.

## Still needed for a full system on mainline

### Kernel config (a "full" variant)

Missing from the m1-* test images today:

- `EXT4_FS` (the SD card's Debian root), and later `MTD_UBI` + `UBIFS_FS`
  for the NAND install (needs the mainline NAND driver first).
- `INPUT_EVDEV`, plus the touch controller driver (touch test pending).
- `USB_ACM` (the Klipper accelerometer board for input shaping). Stock needed
  the `usb-serial generic` new_id trick because 3.2 had no CDC-ACM.
- An RTC driver. The clock is on the SoC: the vendor's `gogin-rtc` at
  0xf8100000 (GIC SPI 32), not an I2C chip. Stock sets it to 1970 at every
  boot, so it probably doesn't keep time over power-off (check whether the
  CR2032 holder actually powers it). dp200-start.sh runs `hwclock -w` after
  NTP; on mainline, NTP at boot is what matters.
- `consoleblank=0` on the command line, which replaces the `setterm -blank 0`
  escape codes.
- The Marvell 8782 firmware in `/lib/firmware/mrvl/` of the root. It's taken
  from the printer at install time and **never published**.

### What the stock side does today, and what replaces it

| Stock side (dp200-start.sh) | Mainline replacement |
|---|---|
| Mounts the root, /proc, /sys, /dev | The kernel mounts the root (`root=/dev/mmcblk0p1 rootwait`); devtmpfs + an init |
| `insmod /app/upc.ko` | Nothing: the driver is built in and probes from the DT |
| Kills the stock app, lighttpd, mjpg_streamer, crond lines | Nothing: they don't exist |
| Stock wpa_supplicant + `dp200-wifi.sh` | Debian wpa_supplicant `-D nl80211 -i mlan0`; same control socket path |
| `dp200-netd.sh` (DHCP/static per port) | Unchanged in principle (BusyBox tools on stock: check that Debian has ifconfig/udhcpc, or port it to `ip`/`dhclient`) |
| ntpd + `hwclock -w` | Debian ntpsec/chrony + the RTC driver |
| Power key loop (outside the chroot) | The same script, run by the init |
| The `usb-serial` new_id for the accelerometer | `USB_ACM` |

### The init

rc.dp200 still assumes no systemd ("the vendor kernel is 3.2"). On mainline,
Debian's systemd would work, but the smallest change is a tiny `/sbin/init`
wrapper. It mounts proc/sys/devtmpfs/devpts/tmpfs, starts wpa_supplicant,
netd and the power key, then runs `rc.dp200 start`, and reaps children. That
keeps one startup path for both kernels.

### How a mainline system would boot every day (decision for the user, later)

Nothing below is done; NAND and the U-Boot env stay untouched.

1. **Fast path as today** (no U-Boot change): U-Boot autoboots stock from
   NAND unless interrupted, so a mainline boot needs a PC to catch U-Boot.
   Good for development only.
2. **Kexec from stock** (no U-Boot change): the stock side starts, then
   kexecs mainline from the SD card. **The stock kernel has no kexec**
   (`# CONFIG_KEXEC is not set` in docs/kernel/vendor_3.2.0-g67a8e16.config),
   so this needs an out-of-tree kexec module built for the vendor kernel
   (install/kernel_modules/ can already build vermagic-matched modules). Some
   Android devices have done this, but on ARM it has to stop the second CPU
   and the caches itself: real work, and only worth it if option 3 is refused.
3. **U-Boot env change** (`saveenv`, the user's decision): bootcmd tries
   `ext2load mmc 0:1` from the SD card with the two SD pad writes first, then
   falls back to NAND. That means one env write and a risk to weigh: a bad env
   with bootdelay=0 would make the prompt unreachable. Keep bootdelay ≥ 1.
4. **NAND install** of mainline: only after the mainline NAND driver is proven
   read-only and then read-write. Last.

Option 3 is the simplest real answer. Option 2 avoids touching U-Boot, at the
cost of a kexec module.

## Offline config check

`tools/klippy_batch_check.sh DEPS` runs klippy in batch mode in WSL with our
config and the UPC firmware's data dictionaries. On 2026-10-29 the full config
(printer.cfg + dp200_printer.cfg + dp200_macros.cfg) loaded with no errors.
A deliberately misspelled option was caught ("Config error ... is not valid").
Batch mode can't get past homing (upc_clockcheck waits for real MCU clocks),
so it checks config and macro syntax, not motion.
