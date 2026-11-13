# mcsync A/B test (2026-10-29): DDR write-buffer drain on mb()

Both kernels were booted through the Ethernet fast path (loader m1-eth f3331420),
with the same commands on each.

| | m1-sd-mcsync (drain on) | m1-sd (drain off) |
|---|---|---|
| zImage md5 | 3946523e | 26c2e03f |
| "DDR write-buffer drain on mb()" in dmesg | yes | no |
| CPUs / SD / Ethernet 100 Full / USB (hub, 8782, webcam) | all OK | all OK |
| dd 64 MB from mmcblk0 (read-only) | 6.34 s | 6.39 s |
| wget 3 x 2.2 MB from the PC | 0.66 s | 0.66 s |
| md5 of the fetched file | OK | OK |
| dd 512 MB /dev/zero to /dev/null | 0.72 s | 0.73 s |
| shell loop, 100k iterations | 3.58 s | 3.61 s |
| oops/BUG/warn lines in dmesg | 0 | 0 |

The drain costs nothing measurable and matches stock behaviour, so the plan is
to enable it by default.

Also fixed here: `uboot_cmd.py --catch` now runs `reboot -f` when the console
is a 6.x test kernel, whose /init ignores a plain `reboot`. Stock still gets
a plain `reboot`.
