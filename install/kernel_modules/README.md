# Kernel modules for the DP200's vendor kernel (3.2.0-g67a8e16)

Built 2026-10-28 without Marvell's SDK. Not loaded on the printer yet:
the first `insmod` is a test with the user present (plan below).

## cdc-acm.ko - USB CDC-ACM serial (Klipper USB boards)

The vendor kernel has no CDC-ACM driver, which Klipper's USB boards use
(e.g. RP2040 ADXL345 accelerometers for input shaping, docs/input_shaping.md).
The first workaround is the generic usb-serial binding in dp200-start.sh; this
module is the proper driver if that isn't enough.

| | |
|---|---|
| File | `cdc-acm.ko`, 28,404 bytes (debug info stripped) |
| sha256 | `885c002695591c8db3b0a64e4f3ba5ee778c574cbdcd1d963b272756bcbfff89` |
| vermagic | `3.2.0-g67a8e16 SMP preempt mod_unload ARMv7 p2v8`, identical to the stock modules |
| Source | vanilla `linux-3.2.tar.xz` from cdn.kernel.org, sha256 `dd96ed02...e7ba7` checked against kernel.org's sha256sums.asc |
| Config | the printer's own `docs/kernel/vendor_3.2.0-g67a8e16.config` + `CONFIG_USB_ACM=m`, `LOCALVERSION="-g67a8e16"` |
| Compiler | Debian armel GCC 14.2.0, native on the printer (`build_cdc_acm.sh`) |

### How it was built

`build_cdc_acm.sh`, inside the printer's Debian chroot. The vendor kernel has
`CONFIG_MODVERSIONS` off, so the kernel checks only the vermagic string, not
per-symbol CRCs. Points that needed care:
- vanilla 3.2 has no `ARCH_MV61X0`: Versatile Express CA9 (another ARMv7 SMP
  machine) stands in; generic code and structures come from the vendor
  config;
- the config's `CONFIG_CROSS_COMPILE` names Marvell's toolchain path: cleared;
- 2012 kernel with a 2025 compiler: `compiler-gcc14.h` (copy of gcc4),
  `-fno-pie -fno-pic -fno-stack-protector -fgnu89-inline -fcommon
  -mno-unaligned-access -fpermissive`;
- Debian packages xz-utils and bc were installed in the chroot for the build.

### How it was checked (all read-only on the printer)

1. **Struct layouts from debug info** (`verify/kocompare.py`). The vendor
   built its stock modules with debug info.
   - `mbcache.ko`, same source built both ways: **156 structures in
     common, 0 differ** (size and every field offset; bitfields skipped).
   - `cdc-acm.ko` against the stock ext4/jbd2/upc/m2m_dma/dm-crypt/mbcache
     modules: **165 structures in common, 0 differ**, including `device`,
     `kobject`, `mutex`, spinlocks, `work_struct`, `delayed_work`,
     `timer_list`, `device_driver`, `module`.
2. **USB and tty structures** (no stock module with debug info uses them),
   checked against the running kernel's own code (`verify/kdump.sh` reads
   25 USB-core and tty functions from /dev/kmem; `verify/kref.sh` compiles
   the same functions from vanilla 3.2; `verify/offcompare.py` compares the
   field offsets in their memory accesses). **145 of 148 vendor offsets also
   appear in our build.** All three differences were checked by hand:
   - in `usb_control_msg` and `usb_submit_urb` our compiler reads packed
     16-bit fields byte by byte;
   - in `usb_ifnum_to_if` the loop starts at 0x4c and pre-increments, where
     the vendor starts at 0x50; both read 0x50;
   - in `tty_register_driver` the offsets are global-variable placement
     (`tty_mutex` / `tty_drivers`), not struct fields; `driver->tty_drivers`
     is at 0xb4/0xb8 in both.
3. **Imports:** all 65 symbols cdc-acm needs are exported by the running
   kernel (`/proc/kallsyms` `__ksymtab_*`, 5,028 exports).
4. **Relocations:** only `R_ARM_ABS32` and `R_ARM_CALL`, both handled by
   the 3.2 module loader.
5. **Config options lost** in the vanilla build (vanilla doesn't know them):
   Marvell platform drivers, PJ4B errata, EHCI/gadget glue, WEXT, DMA
   engine, `ARMV7_TLB_OPTIMIZATION` and `FORCE_MAX_ZONEORDER=12`. None of
   them changes the structures cdc-acm uses. The zone order only adds a
   larger kmalloc size class at the end of the table, so the indices of
   cdc-acm's small fixed-size allocations are unchanged.

**Risk assessment:** low. The remaining unknowns are code paths no check
could see, e.g. a Marvell change inside a USB-core function's behaviour (not
its layout), and GCC 14 code running in a GCC 4.6 kernel (same EABI;
no stack protector, no PIE, no unaligned accesses). If loading goes wrong,
the expected failure is an oops in the kernel log or a hang, and a power
cycle returns to the stock state: nothing is installed permanently.

### Test plan (main session, user present, Klipper idle, no heat/motion)

1. Copy `cdc-acm.ko` to the printer (e.g. `/mnt/sd/dp200/cdc-acm.ko`),
   check the sha256.
2. On the stock shell: `insmod /mnt/sd/dp200/cdc-acm.ko`, then
   `dmesg | tail` - expect `usbcore: registered new interface driver
   cdc_acm` and no oops. `lsmod` shows it.
3. Remove the generic-serial binding for Klipper's ID first if it is active
   (it would grab the board instead):
   `echo 1d50 614e > /sys/bus/usb-serial/drivers/generic/remove_id` (or
   reboot without that line).
4. Plug in the accelerometer: expect `cdc_acm 1-1:1.0: ttyACM0: USB ACM
   device` in dmesg. Create the node in the chroot
   (`mknod /mnt/sd/dev/ttyACM0 c 166 0`, group klipper, 660) and use
   `serial: /dev/ttyACM0` in dp200_adxl.cfg.
5. `rmmod cdc_acm` must work (unplug first). Back out: rmmod, or power cycle.
6. If it works: load it at boot from dp200-start.sh (instead of the
   generic binding), create ttyACM0-3 in dp200-mounts.sh, update
   docs/input_shaping.md.

### Rebuilding

`chroot /mnt/sd sh /usr/src/dp200/klipper_port/install/kernel_modules/build_cdc_acm.sh`
(needs `/usr/src/kbuild/linux-3.2.tar.xz`; about 15 minutes; ~150 MB of free
space). The verification scripts in `verify/` are the ones used above.
