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
12. **Input shaping:** mounts for the FLY-ADXL345 (measure, print), then
    SHAPER_CALIBRATE, then the payload (docs/input_shaping.md).
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
    timer reads; ARM-mode step path, default off). Test, rebase onto
    `sindoh-dp200` without the merge commit, then delete the branch.
28b. **Clean fork branch `dp200-clean`: built 2026-11-13, printer tests
    open** (owner at the dev printer: homing, drift test, a real print).
    Test B first, then C:
    - B (`dp200-clean-b`, f01effd8: same code on upstream 29d4ec2d):
      `fm-clean-b.bin` a4481759, `io-clean-b.bin` a249f6c7.
    - C (`dp200-clean-c`, 0607ba28: no board `#if` in shared files):
      `fm-clean-c.bin` cea02737, `io-clean-c.bin` 8ecc88f4.
    Images on 10.10.0.68:8098. No printer-config change needed. klippy on
    the printer must come from the same tag as the firmware (protocol
    dictionary). After both pass: `dp200-clean` replaces `sindoh-dp200`
    (owner's OK for the force-push or rename), bump `klipper/FORK`, and
    copy the fork's re-wrapped `upc_hw.h` to `common/` (fork_check).
29. **Probe settling after homing:** the first ~5 touches after G28 read
    0.015-0.02 mm high. Check BED_MESH_CALIBRATE right after homing.
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
