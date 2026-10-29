# UPC driver for mainline (design, offline)

Goal: run what already works on the stock kernel unchanged on mainline.
That covers the Klipper MCU firmware on both UPC cores (`klipper/src/upc/`),
`host/upctool` (load, stop, safe, info, bridge) and klippy. The stock
driver is the module `upc.ko` (`/app/upc.ko`, also
`/lib/modules/3.2.0-g67a8e16/kernel/arch/arm/mach-gogin/upc.ko`).
Everything below comes from its disassembly (2026-10-29) and
`docs/hardware_notes.md`.

## What upctool needs from the kernel

| Interface | Used for |
|---|---|
| `/dev/upc0` (IO core), `/dev/upc1` (FM core) | ioctls below, `write()` into ITCM/DTCM, `read()` |
| `/dev/mem` | DTCM rings for the bridge, finding DTCM with a nonce, PWM (0xf81xxxxx) and stepper engine (0xf8150000) registers for `safe` |
| `/proc/iomem` | candidate DTCM addresses |
| UNIX98 PTYs | the bridge's serial ports for klippy |
| TCP | `bridge -f tcp:9100 -i tcp:9101` for a remote klippy |

## Stock driver, register level

Resources (board file): UPC0 = 0xf9200000-0xf920ffff, IRQ 126 (SPI 94);
UPC1 = 0xf9210000-0xf92bffff, IRQ 127 (SPI 95). Each is its own platform
device and char device (minor = core).

| Item | Address | Stock code |
|---|---|---|
| ITCM, core n | resource n base + offset; 0x4000 bytes per core, written and read byte by byte | `upc_write_itcm`, `upc_read_itcm` |
| DTCM (shared) | UPC1 base + 0x70000 = **0xf9280000** + offset; driver window 0x20000, the cores see 0x40000 | `upc_write_dtcm`, `upc_read_dtcm` |
| XENA register block | UPC0 base + 0x8000 = **0xf9208000** | `upc_get_regbase_addr` |
| CPUSoftReset | XENA + 0x154; 1 = both cores run, 0 = both held (no per-core reset) | `upc_soft_reset` |
| GPStatus | XENA + 0x150; bit 0/1 raised by the cores, cleared by the IRQ handler | `upc_get/set_gp_status`, `upc_platform_irq` |
| Mailboxes 0-5 | XENA + 0x128, +0x12c, +0x1130, +0x1134, +0x1138, +0x113c | `upc_write/read_mailbox` |
| UPC clocks | APB config 0xf8000180: bits 12:8 IO clock, bits 7:5 XCPU clock (exported helpers; upc.ko itself does not call them) | `upc_set_apb_io_clock`, `upc_set_apb_xcpu_clock` |

ioctls (one global mutex):

| Number | Effect |
|---|---|
| `0xc0017522` | CPUSoftReset = 0 (hold) |
| `0xc0017521` | CPUSoftReset = 1 (run) |
| `0x7523` | the next `write()`/`read()` on this file goes to ITCM |
| `0xc0047524` | the same for DTCM; the argument (by value) is the DTCM offset |
| `0xc0087530` | mailbox write `{u32 box, u32 value}`. Box 0 or 5 then waits (interruptibly) for the GPStatus bit 0 IRQ, box 1 for bit 1, still holding the mutex |
| `0xc0087531` | mailbox read `{box, value}` |

`write()`/`read()` use the file position with no `lseek`, so callers reopen
for each transfer. Probe touches no hardware: it maps the resource, requests
the IRQ (the handler clears GPStatus bits 0 and 1, then `complete()`s) and
creates `/dev/upcN`. A register-table ioctl (`upc_register_setup`, per entry
skip/set/OR/AND) exists for the stock app; upctool does not use it.

## Mainline driver

`drivers/misc/mv61x0-upc.c`, ABI-compatible with the stock driver:

```
upc: upc@f9200000 {
	compatible = "marvell,88pa6170-upc";
	reg = <0xf9200000 0x10000>, <0xf9210000 0xb0000>;
	interrupts = <GIC_SPI 94 IRQ_TYPE_LEVEL_HIGH>,
		     <GIC_SPI 95 IRQ_TYPE_LEVEL_HIGH>;
};
```

- **Device nodes:** one platform device, two misc devices `upc0`/`upc1`
  with the ioctls, read/write semantics, limits and mutex above.
  `MISC_DYNAMIC_MINOR`; devtmpfs creates `/dev/upc0` and `/dev/upc1`.
- **Mailbox wait:** a shared completion, as stock;
  `wait_for_completion_interruptible`, so Ctrl-C works.
- **Memory access:** `ioremap` only. It does not reserve the regions with
  `request_mem_region`, so `/dev/mem` (DEVMEM=y, STRICT_DEVMEM allows I/O,
  IO_STRICT_DEVMEM off) keeps working for upctool unchanged.
- **Later improvements:** an `mmap` of DTCM on `/dev/upcN` would let upctool
  drop `/dev/mem` and the nonce search; a safe-state hook (below).
- **Probe does nothing to the cores**, like stock: no reset change, no clock
  change. Nothing starts until `upctool load`.
- **Safety hooks (new):** a reboot notifier and a panic notifier that hold
  the cores (CPUSoftReset = 0) and apply upctool's `safe` state: every PWM
  block's CTRL loses LEVEL then RUN, every stepper engine gets
  `SMOT_ABORT = 0x100` and `SMOT_CFG |= 1` (addresses in
  `common/upc_hw.h`). With `panic=10` that turns heaters and drivers off
  before the reset; on stock, a kernel crash leaves the cores running. The
  Klipper heater `max_duration` stays the firmware-side backstop.
- **Clocks:** read `0xf8000180` on stock Linux and on m1 (both read-only
  `devmem`). If m1 differs, the driver sets the stock value from a DT
  property at probe, before any load. Klipper's `CONFIG_CLOCK_FREQ` assumes
  the stock FM clock (~396 MHz).

Size: about 300 lines. Kernel config extras: `UNIX98_PTYS` (devpts mounted
by init) for the bridge, plus Wi-Fi association for a remote klippy.

## Bring-up order (each step with the user present)

1. Driver + DT in an image; probe only. Check `/dev/upc0`, `/dev/upc1`, and
   `upctool info` (reads only).
2. `upctool safe` while the cores are held: verify the PWM/stepper
   registers read back in the safe state.
3. Load the passive probe firmware (`upc_fw/probe/`): cores alive, timer
   rates, clock estimate.
4. Klipper firmware + `upctool bridge`, klippy remote over Wi-Fi.
   identify, endstops, thermistors first. Heaters and motion only with
   the user watching, after the safe hooks are verified.
