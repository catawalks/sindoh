# UPC driver test 1 (2026-10-29): driver load and safety paths, no firmware

m1-upc (c500c0c5, SMP), booted through the Ethernet fast path; the user approved it. No
firmware was loaded onto the UPC cores, and there was no heat and no motion.

- dmesg: `mv61x0-upc f9200000.upc: APB config 01dde22d -> 01dde26d`, then
  `cores held, outputs safe (CPUSoftReset was 0, GPStatus 00000000)`.
- /dev/upc0 and /dev/upc1 exist; IRQs 126 and 127 are registered, with 0 counts.
- Read-back: CPUSoftReset 0 (held), PWM CTRL blocks 1-4 0x00000000, stepper
  CFG 0-4 0x00000001 (driver off), UPC APB clocks 0xf8000180 = 0x01DDE26D.
  **Stock 3.2 with upc.ko loaded reads 0x01DDE26D too**, so it's an exact match.
- `upctool info`: DTCM base 0xf9280000. FM and IO cores show "magic none" with
  random-looking fw/heartbeat words (uninitialised DTCM, no firmware loaded):
  as expected. rc 0.
- `upctool safe`: rc 0.
- `reboot -f`: logs `mv61x0-upc f9200000.upc: reboot: cores held, outputs off`
  and resets.
- `echo c > /proc/sysrq-trigger`: `Kernel panic - not syncing`, then
  `mv61x0-upc: panic: cores held, outputs off`, `Rebooting in 10 seconds..`,
  and it reset to U-Boot and stock on its own.

Next (needs the user watching): the passive probe firmware (`upc_fw/probe`),
then repeat both safety paths while it runs.
