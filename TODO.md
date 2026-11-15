# DP200 Klipper port - open items

**Open items only.** When an item is done: delete it here and add a line to
[docs/history/CHANGELOG.md](docs/history/CHANGELOG.md), in the same commit
as the work. No test logs here. Rules and the documentation map:
[docs/README.md](docs/README.md). Current state of the printers:
[docs/STATUS.md](docs/STATUS.md). Larger projects: [PROJECTS.md](PROJECTS.md).
The list as it stood before 2026-11-12, with all results:
[docs/history/TODO_archive_2026-11-12.md](docs/history/TODO_archive_2026-11-12.md).

## Owner at a printer

Dev printer:
1. **Wi-Fi part D:** 3 power cycles, check Wi-Fi comes up from a cold boot
   (module 0028).
2. **Load jam, filament held back mid-load** (optional; the empty-inlet
   case passed 11-12).
3. **Screen app's load error pages on hardware:** the running page after
   TRY AGAIN and the plain page for homing errors (0cc6a77) are deployed
   but have not seen an error yet. Also run `test_dp200_screen.py` on the
   printer.
4. **Screen features never used on hardware:** the calibration wizards
   (Z HEIGHT paper test, PROBE OFFSET, PID TUNE, SAVE Z OFFSET), OBJECTS
   (skip one object), WiFi -> SAVED (PREFER / FORGET), custom MACROS page.
5. **UPC load in Mainsail's MCU panel under motion.** The firmware with it
   (fm 6cdaee5b, io f0407060) is on the 4 GB card root, not on the NAND
   root (fm c313d379): install it there first.
6. **Dryer leftovers:** STOP DRYING, PRINT_START during drying, FORCE=1
   above the 70 C sheet limit.
7. **A real Mainsail update** from SYSTEM -> UPDATE (only CHECK NOW tried).
8. **Ethernet recovery after a switch outage:** `dp200-netd.sh` restarts
   udhcpc after 30 s without an address; never exercised (pull the cable
   or power the switch off).

Work printer:
9. **Next stick payload** (userspace only, no kernel): the 11-12 macros
   (paused-print Z guard, jam check, EMPTY_BIN, re-prime, X/Y-only homing
   for load), PRIME_LINE at Y 0, the screen app, the UPC load firmware.
   Build (agent), then install and a real print (owner).
10. **Resume quality on real prints:** some straggler lines at the resume
    layer after a load (11-12). Tune `reprime_len` (30 mm) if needed.
11. **Wi-Fi stability on the upgraded work printer.**

Either printer, longer:
12. **Print speed** (owner asked 11-15; goal: faster prints at the same
    quality, no mechanical changes). Today: test prints at 30 mm/s,
    `max_accel` 1500, no input shaping. X/Y are proven to 208 mm/s. In
    this order:
    a. **Max flow test:** extrude at rising rates until the extruder skips
       or under-extrudes; gives the hotend's limit in mm3/s (unmeasured; a
       hotend of this type usually manages 8-12 with PLA, i.e. about
       110 mm/s at 0.45 x 0.2 mm).
    b. **Input shaping:** mounts for the FLY-ADXL345 (measure, print),
       then SHAPER_CALIBRATE (docs/input_shaping.md); raise `max_accel`
       to what it allows (3000-5000 is usual for a bed-slinger this size).
    c. Re-tune pressure advance at the new speeds; check part cooling.
    d. Slicer profile with the result (expected: walls and infill
       80-120 mm/s, travel 150-200), then the payload.
13. **Beeper:** `[output_pin beeper] pin: io:pwm10`, pick the PWM value,
    then M300; the dryer's end signal uses it.
14. **Retraction test** (two towers), then the slicer profiles; recheck
    pressure advance (0.30) with dry filament.
15. **Mesh front limit:** the front is flat to Y -2 (11-12 probe map), so
    mesh_min Y could go below 30.
16. **Homing clearance:** a few mm of Z clearance before X homing, so the
    nozzle doesn't drag across a failed print. Mind that Z homes upward.
17. Optional: a 6-7 mm/s Z lift test (10 stalls lifting; stock is 5.05).

## Agent (no owner needed)

Kernel (dev printer only):
20. **Merge the bank 3 pad fix** (motor repo `upc-bank3-pads` 7dd0f21:
    mv61x0-upc.c + the DTS) into the kernel tree and patch set.
21. **Soak the bank3 kernel** (7eae8600 in mtd0): so far one RAM boot and
    one NAND boot; C3 had 10 h.
22. **The one-CPU default rebooted by itself** ~07:20 on 11-11 (no
    watchdog line, no pstore). Cause unknown; that kernel is no longer in
    mtd0. Watch for it.
24. **Initramfs:** keep its log somewhere init.mainline's /run doesn't
    cover; close the mtd6 window when the root isn't mtd6; Ethernet MAC
    from mtd1; maybe refuse a root without init.mainline.
25. **`iw` in the root build's package list** (installed by hand on the
    dev printer). Decide Wi-Fi power save: off cut the drops but slowed
    downloads in one test (11-07).

Wi-Fi:
26. **Wi-Fi leaves the preferred network** (traced 11-14, not fixed):
    - Cause of the fallback: the access point that carries Niholedotcom
      (BSSIDs ..:45:58:f7:f9:44, 2.4 GHz) disconnects the printer about
      91 s after every association, reason code 34 (low ACK). Seen 14 times
      in the 24 min after the 11-13 boot and again live on 11-14. Its 5 GHz
      radio (-78 dBm) associates but gets no address. After enough failures
      wpa_supplicant lands on the Fios-kVGD7 router, which held 27 h.
      Power save was off. `cmd 0x23f error` (STA_CONFIGURE) shows about
      62 s after each association on both routers, so probably unrelated.
      Open: is it the AP (band steering / low-ACK kick) or our driver not
      acknowledging? Compare the work printer (stock 3.2) on the same AP.
    - 11-14: saved networks are now 2.4 GHz only (the module has no
      usable 5 GHz antenna: docs/wifi.md). The 5 GHz detours are gone and
      the printer is back on the AP 1 s after each drop, but the drops go
      on (91 s and 94 s in the test). Owner will try the UniFi settings:
      band steering, minimum RSSI, BSS transition / fast roaming, and the
      client event log.
    - Why it never goes back: `dp200_wifi.watchdog` reads cached scan
      results, which hold only the current AP after a few minutes, so it
      never sees the preferred network. A fresh scan alone makes
      wpa_supplicant switch back (seen 11-14). Don't fix this half before
      the first: it would only re-enter the 91 s loop every 10 min.
26a. **Camera streamer died** (dev printer, found 11-14): ustreamer was
    gone, first refused snapshot 11-14 00:28 UTC (about 22 h after boot),
    no trace, cause unknown. Since 11-14 rc.dp200 (`webcam-loop`) logs it
    to /var/log/dp200_webcam.log with its exit status, restarts it after
    5 s, and makes the kernel log where a fatal signal hit. Read the log
    after the next exit, find the cause; owner: the log and restart can go
    once it is fixed.
27. Upstream submission of the 8782 fix: **tabled by the owner 11-12**.
    The patch and cover letter are ready on the build box, not sent.

Motion and firmware:
28. **Root and payload builds now take Klipper from the fork**
    (`klipper/get_fork.sh`, 2026-11-13). Syntax-checked and the checkout
    tested on the PC; the first real root or payload build is the test.
    The two printers' `/home/klipper/klipper` are older checkouts: move
    them to the pinned fork commit with the next payload.
28a. **`upc-fast-step` (fork):** two untested stepping commits (fewer
    timer reads; ARM-mode step path, default off). The branch still sits
    on the old `sindoh-dp200` (tag `sindoh-dp200-before-clean`): rebase
    its two commits onto the new `sindoh-dp200`, test, then delete it.
28b. **After the fork's branch replacement (2026-11-15):**
    `sindoh-dp200` is now the clean history (8203a7d7, on upstream
    29d4ec2d), pinned in `klipper/FORK`. Left:
    - The dev printer runs tag `dp200-clean-c` (0607ba28), two commits
      behind the pin. Those two only re-wrap long lines. Rebuild fm/io
      from 8203a7d7, install with klippy from the same commit
      (docs/dev_printer_testing.md), check `software_version`.
    - klippy's C helper changed with the move to upstream 29d4ec2d and
      the NAND root has no gcc: check that the root build
      (`install/rootfs_inside.sh`) and the next stick payload carry a
      `c_helper.so` built from the pinned commit.
    - The work printer still runs the old code (the 11-07 payload).
29. **Probe: false left-right slope** (found 11-14, fixed on the dev
    printer with `[axis_twist_compensation]` in its printer.cfg, plus
    five warm-up touches before every mesh; docs/dev_printer_testing.md).
    Left:
    - After the fix the owner still saw slightly more squish on the
      right over 150 mm: the right value (0.103) may need about +0.02.
    - The center value (-0.042) is the least certain: the raw center
      reading moved 0.04 mm between runs. Redo the three-spot comparison
      once more and adjust.
    - The comparison was made at Y 30 only. Check one more row (Y 150).
    - The work printer needs its own values: do the same comparison
      there, or ship without the section and tell users how.
    - A way to do the comparison from the touch screen (wizard).
30. **Prebuilt (zig) UPC images** are untested with motion (they are the
    fallback; the printers run the gcc builds).
31. **Bed heat-up took 9 min to 60 C once** (11-12, cold start); look at
    the bed PID / max_power.
32. `map_front.py`: deploy the probe once and use `_PROBE_BASE` per point.

Screen app:
33. **Why the reply to a long LOAD request never came** (11-12; the busy
    state is fixed, the cause wasn't seen): check moonraker.log.

End-goal install ([docs/end_goal_install_plan.md](docs/end_goal_install_plan.md);
stages 1-5 done on the dev printer):
34. **Stage 6:** installer v2 (USB stick under stock 3.2 writes mtd6, then
    mtd0).
35. **Stage 7:** the full Sindoh-stick revert cycle (YES-YES)
    and the broken-root prompt on hardware.
36. **Stage 8:** the work printer.
37. **Stage 9:** release checklist (PROJECTS #10).
