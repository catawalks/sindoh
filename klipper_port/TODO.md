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
   (Z HEIGHT paper test, PROBE OFFSET, PID TUNE, SAVE Z OFFSET), WiFi ->
   SAVED (PREFER / FORGET). The custom MACROS page opens and lists the
   macros (owner, 11-16); adding an own macro and running one from it
   is not tried.
6. **Dryer leftovers:** STOP DRYING, PRINT_START during drying, FORCE=1
   above the 70 C sheet limit.
7. **A real Mainsail update** from SYSTEM -> UPDATE (only CHECK NOW tried).
8. **Ethernet recovery after a switch outage:** `dp200-netd.sh` restarts
   udhcpc after 30 s without an address; never exercised (pull the cable
   or power the switch off).

Work printer:
9. **Work printer has no `[axis_twist_compensation]`:** if wide first
   layers are uneven left to right there, do the comparison in
   docs/dev_printer_testing.md on that printer (see also #29).
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
    b. **Input shaping:** X measured on the dev printer 11-16
       (docs/input_shaping.md "Dev printer, 2026-11-16"): Klipper
       recommends `3hump_ei` 80.8 Hz, max_accel <= 4300; the X peak is
       at 44-47 Hz. Nothing saved yet. Left:
       - Choose the X shaper with a ringing test print (3hump_ei 80.8
         against mzv ~50), then put `[input_shaper]` in printer.cfg.
       - Y: the bed mount is ready to print
         (`install/input_shaping/mounts/adxl_bed_bar.stl`: a bar that
         replaces one front grip of the build plate, same two screws).
         Owner prints it, reports the fit, then SHAPER_CALIBRATE AXIS=Y.
       - Mount version 4 (clears the Bowden tube at X home, posts at
         the left end) is ready to print; version 3 blocks X homing.
         Repeat the X run once with it.
       - rc.dp200 should set group dialout / mode 660 on /dev/ttyACM0
         (today by hand after every Klipper restart).
       - `setup_numpy.sh` does not work on the NAND root (no apt); the
         dev printer got numpy by hand from the card. Decide how the
         payload / root build ships it. The stock-kernel path (work
         printer) is untested with a sensor.
       - The touch screen's INPUT SHAPING page is untested.
       Then raise `max_accel` (1500 now) toward what the shapers allow.
    c. Re-tune pressure advance at the new speeds; check part cooling.
    d. Slicer profile with the result (expected: walls and infill
       80-120 mm/s, travel 150-200), then the payload.
13. **Beeper:** `[output_pin beeper] pin: io:pwm10`, pick the PWM value,
    then M300; the dryer's end signal uses it.
14. **Retraction test** (two towers), then the slicer profiles; recheck
    pressure advance (0.30) with dry filament.
15. **Mesh front limit at Y 5** (was 30; six rows): a mesh ran clean
    on the dev printer 11-16 (30 points, reference check -0.019 mm;
    front row about 0.1 mm lower than the row behind it). Left: a first
    layer printed at the front of the bed, before the next payload
    carries the change to the work printer.
16. **Homing clearance:** a few mm of Z clearance before X homing, so the
    nozzle doesn't drag across a failed print. Mind that Z homes upward.
17. Optional: a 6-7 mm/s Z lift test (10 stalls lifting; stock is 5.05).

## Agent (no owner needed)

Kernel (dev printer only):
20. **Bank 3 pad fix: bookkeeping only.** The fix runs in mtd0 (image
    7eae8600, soaked: see the changelog, 11-16). Left: on the build box,
    merge motor repo branch `upc-bank3-pads` (7dd0f21: mv61x0-upc.c + the
    DTS) into the kernel tree and patch set, so the next kernel build
    has it without that branch. Not checked on 11-16 whether this was
    already done there.
24. **Initramfs** (checked 11-16; needs a new kernel image, so do it
    with the next kernel build, before end-goal stage 6):
    - Its own log is still lost: it is copied to /newroot/run, which
      init.mainline's tmpfs covers (no such file on the dev printer).
      Write it where it survives, e.g. append to /var/log/dp200-init.log.
    - Close the mtd6 write window when the root isn't mtd6 (does not
      matter on the dev printer today: its root is mtd6).
    - Optional: refuse a root without init.mainline.

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
    5 s, and makes the kernel log where a fatal signal hit. Checked
    11-16 15:18 UTC: no exit since the loop was deployed (running since
    11-14 06:12 UTC, 57 h, same boot; the earlier death came about 22 h
    after boot). The three exits in the log are the 11-14 deploy tests.
    Check again after a longer run or a reboot; if it dies, read the
    log, find the cause. Owner: the log and restart can go once fixed.
27. Upstream submission of the 8782 fix: **tabled by the owner 11-12**.
    The patch and cover letter are ready on the build box, not sent.

Motion and firmware:
28. **Root and payload builds now take Klipper from the fork**
    (`klipper/get_fork.sh`, 2026-11-13). Syntax-checked and the checkout
    tested on the PC; the first real root or payload build is the test.
    The two printers' `/home/klipper/klipper` are older checkouts: move
    them to the pinned fork commit with the next payload.
28a. **Mesh reference drift:** PRINT_START's mesh was discarded once in
    five prints on 11-15 ("reference probe moved -0.112 mm", limit 0.1).
    Cause: the pin keeps settling for about 25 touches after a deploy
    (40 touches: first one +0.04 mm, then a slow fall of 0.02 mm on a
    cool bed and 0.07 mm on a bed cooling from 60 C), and the mesh starts
    as soon as the bed reaches temperature. Options: more warm-up touches
    (`variable_warmup`, now 5; 25 adds about 3 min), a soak of a minute or
    two after the bed reaches temperature, or both. Measure which helps.
    The Z motor is not losing steps (the readings level off).
28b. **Root build with the new fork:** klippy's C helper changed with
    the move to upstream 29d4ec2d and the NAND root has no gcc. The stick
    payload carries the right `c_helper.so` (built on the card). Still to
    check: `install/rootfs_inside.sh` (a root built from scratch) builds
    it too.
28c. **`UPC_STEP_ARM`** (fork, default off): the ARM-mode step path
    passed homing, the drift test and a print on 11-15 (FM image 14068 B
    of 16384). Turn it on in `config/dp200_fm.config` only if the speed
    work (#12) shows the step firmware is the limit.
28d. **The stick payload (11-15) has the firmware of 8203a7d7**, without
    the three stepping commits merged later that day (ee0c7f8e). They go
    into the next payload.
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

End-goal install ([docs/end_goal_install_plan.md](docs/end_goal_install_plan.md);
stages 1-5 done on the dev printer):
34. **Stage 6:** installer v2 (USB stick under stock 3.2 writes mtd6, then
    mtd0).
35. **Stage 7:** the full Sindoh-stick revert cycle (YES-YES)
    and the broken-root prompt on hardware.
36. **Stage 8:** the work printer.
37. **Stage 9:** release checklist (PROJECTS #10).
