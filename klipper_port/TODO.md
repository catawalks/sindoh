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
5. **Touch screen INPUT SHAPING page:** never tried on hardware (needs
   the accelerometer plugged in).
6. **Dryer leftovers:** STOP DRYING, PRINT_START during drying, FORCE=1
   above the 70 C sheet limit.
7. **A real Mainsail update** from SYSTEM -> UPDATE (only CHECK NOW tried).
8. **Ethernet recovery after a switch outage:** `dp200-netd.sh` restarts
   udhcpc after 30 s without an address; never exercised (pull the cable
   or power the switch off).

Either printer:
13. **Beeper:** dec_pwm block 10 (`io:pwm10`) from the 10-20 reverse
    engineering; never configured or heard. How stock drives it (period,
    duty, volume levels) is not mapped yet: the stock app
    (171114_4_open/marvell_lspsdk_3dp_gemstone-debug_stripped.elf) has
    `BeepOn`, `beepDutyTable`, `setBeepLevelfromDB`, `OpBeepThread`,
    `BeepRequestService`. Map those, then `[output_pin beeper]` and
    M300 (the dryer's end signal uses it).
16. **Homing clearance:** a few mm of Z clearance before X homing, so the
    nozzle doesn't drag across a failed print. Mind that Z homes upward.

## Printer tuning

Print quality and speed settings, found with test prints (owner at the
printer for each print). Results go into the printer's printer.cfg, the
shipped config or the slicer profiles.

9. **Work printer has no `[axis_twist_compensation]`:** if wide first
   layers are uneven left to right there, do the comparison in
   docs/dev_printer_testing.md on that printer (see also #29).
10. **Resume quality on real prints:** some straggler lines at the resume
    layer after a load (11-12). Tune `reprime_len` (30 mm) if needed.
12. **Print speed** (owner asked 11-15; goal: faster prints at the same
    quality, no mechanical changes). Today: test prints at 30 mm/s,
    `max_accel` 1500, no input shaping. X/Y are proven to 208 mm/s. In
    this order:
    a. **Max flow:** measured 11-17 (dev printer, PLA at 205 C, into the
       air): normal to 14 mm3/s; 16 and 18 came out thicker (the owner
       sees no other difference on matte gray PLA); extruder clicks at
       20. Slicer max volumetric speed 12 for now (the owner's profile
       has 8), 16 probably safe to try later. 12 is about 145 mm/s at
       0.45 x 0.2 mm. Test file `dp200_max_flow.gcode`. First fast
       Benchy started 11-17 (`dp200_benchy_fast.gcode`: 12 mm3/s, outer
       walls 60, inner 100, infill 130, travel 180, accel 2500).
       Result 11-17 (1h 16m printing, owner's photos): hull, bow, chimney,
       door arch, roof top and the bottom text good; fine hairs all over
       (stringing; retraction 4 mm at 35, 205-210 C; the PLA is dry: it
       sat on the bed through the dryer test); stern text illegible; a
       rough patch at a stern corner about 5 mm up (#18). Next: #14 and
       12c.
    b. **Input shaping:** X measured on the dev printer 11-16
       (docs/input_shaping.md "Dev printer, 2026-11-16"): Klipper
       recommends `3hump_ei` 80-83 Hz, max_accel <= 4300 (three runs,
       the last with head mount version 4, which homes X fine); the X
       peak is at 38-47 Hz. Y measured 11-16 with the bed bar: `2hump_ei`
       39.0 Hz, max_accel <= 1500; wide Y peak at 27-40 Hz. Y is the
       limiting axis. Both picks are in the dev printer's printer.cfg
       since 11-16; no print with them yet. Left:
       - Ringing test print with the saved shapers: started 11-16
         (`dp200_ringing_tower.gcode`, 1500 to 4250 in 5 mm bands);
         Y clean to 2750, X rings at sharp corners in every band.
         `dp200_x_shaper_compare.gcode` (six X shapers in 10 mm
         bands at 2500, 11-17): no band differs, so the visible X
         ripple is not the measured 38 Hz peak (docs/input_shaping.md).
         Cause: the head sits on magnets and a loose dovetail
         (owner); ripple about 4 mm = about 20 Hz. X set to the
         fastest band, `2hump_ei` 87.4 (max_accel 8094). A new
         carriage mount is a future project. Earlier plan, kept for
         reference: keep
         them, or a lighter one (X: ei ~42; Y: ei 40 or mzv 29.4,
         which allow 2500-2900), and put the result in the shipped
         config.
       `max_accel` 2500 on the dev printer since 11-17 (owner; its printer.cfg,
       the shipped dp200_printer.cfg stays 1500 for printers without shapers).
       Next: prints at the higher speeds (12c, 12d).
    c. Re-tune pressure advance at the new speeds; check part cooling.
    d. Slicer profile with the result (expected: walls and infill
       80-120 mm/s, travel 150-200), then the payload.
14. **Retraction test** (two towers; the 11-17 Benchy strung at 4 mm /
    35 mm/s with dry PLA), maybe a temperature tower, then the slicer
    profiles; recheck pressure advance (0.30, set 10-28 on damp PLA at
    slow speeds) with the dry filament (12c).
15. **Mesh front limit at Y 5** (was 30; six rows): a mesh ran clean
    on the dev printer 11-16 (30 points, reference check -0.019 mm;
    front row about 0.1 mm lower than the row behind it). Left: a first
    layer printed at the front of the bed, before the next payload
    carries the change to the work printer.
17. Optional: a 6-7 mm/s Z lift test (10 stalls lifting; stock is 5.05).
18. **Z seam on the Benchy's stern corner:** in `dp200_benchy_fast.gcode`
    (`seam_position = aligned`) the hull's outer wall starts and ends at
    the stern corner (X 77, Y 92-95) on every layer from about 3 to 10 mm;
    the rough patch at about 5 mm is there, where the stern text and its
    short moves and retractions begin. 11-18: rechecked in the G-code:
    the seam is on the low-Y stern corner (front of the bed when
    printed) only from 3 to 6.05 mm; it moves off the corner above. The
    other stern corner has no seam or retraction at that height. The
    owner sees the damage at the back left corner and no seam line;
    which corner it is still has to be matched to the bed. Owner: fix
    the cause, not hide it, so retraction (4 mm at 35 mm/s, no wipe;
    slicer profile) and pressure advance (printer.cfg) come first
    (12c, #14), then reprint and compare; moving the seam only if
    needed.
28a. **Mesh reference drift:** PRINT_START's mesh was discarded once in
    five prints on 11-15 ("reference probe moved -0.112 mm", limit 0.1).
    Cause: the pin keeps settling for about 25 touches after a deploy
    (40 touches: first one +0.04 mm, then a slow fall of 0.02 mm on a
    cool bed and 0.07 mm on a bed cooling from 60 C), and the mesh starts
    as soon as the bed reaches temperature. Options: more warm-up touches
    (`variable_warmup`, now 5; 25 adds about 3 min), a soak of a minute or
    two after the bed reaches temperature, or both. Measure which helps.
    The Z motor is not losing steps (the readings level off).
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

## Agent (no owner needed)

Input shaper sensor (the system behind the accelerometer):
19. **Make the sensor setup part of the install:**
    - A stable name for the board's port: after a replug with Klipper
      running it becomes /dev/ttyACM1 (docs/input_shaping.md has the
      recovery).
    - rc.dp200 should set group dialout / mode 660 on /dev/ttyACM0
      (today by hand after every Klipper restart).
    - `setup_numpy.sh` does not work on the NAND root (no apt); the dev
      printer got numpy by hand from the card. Decide how the payload /
      root build ships it. The stock-kernel path (work printer) is
      untested with a sensor.

Kernel (dev printer only):
20. **Bank 3 pad fix: bookkeeping only** (11-18: could not be checked
    from the PC, the build box needs its own login). The fix runs in mtd0 (image
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
      acknowledging? Compare with a stock system on the dev printer
      (the work printer is at another site, not on these networks).
      **Answered 11-17: it is our side.** Stock (with Sindoh's
      200730_2 update) on the dev printer held the same AP for 67 min
      with no drop and 0 of 3600 pings lost (docs/STATUS.md, first
      section). Our kernel on the card root dropped the same way every
      95 s (reason code 7 in that log). Next, back on our kernel:
      compare with stock's setup (Marvell driver, wext, power
      management on): try power save on, then the reason 34 low-ACK
      path in mwifiex (ACKs / TX status, firmware version).
      **11-17 night, back on our kernel: power save on fixes it.**
      Before: dropped at 73 s after boot as always. With power save
      on: no disconnect in 1 h 45 min, same AP; the PC's ping lost
      one or two in a row every 5-20 min (likely power-save latency,
      not drops). **Now the default on every printer, both kernels**
      (owner, 11-17: init.mainline, dp200-wifi-action.sh and the USB
      stick's dp200-start.sh; deployed on the dev printer, reaches the
      work printer with the next payload).
      /etc/dp200/wifi_power_save = on/off overrides.
      **11-18: power save did NOT fix it.** The dmesg log
      (/var/log/wifidrop.log, `dmesg -w` since 11-17 22:59) shows no
      drop for 2 h (22:58 to 00:59 UTC, during the comparison print and
      the PC's 1/s ping), then reason 7 drops every 95-125 s from 00:59
      to now (475 of them), power save still reported on. A 10 min ping
      from the PC on 11-18 14:00 did not stop them (10 of 600 lost,
      6 drops), so traffic is not what kept the first 2 h clean. The
      cold boot does set power save on (iw: on after the 11-17 22:57
      boot). Open: what changed at 00:59 (2 h after association: a key
      rekey, the DHCP lease, the AP's own timers?), and the UniFi
      client log for the printer at 00:59. Owner 11-18: probably the
      network (other IoT devices there drop about every 5 min);
      troubleshoot the network separately first.
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
27. Upstream submission of the 8782 fix: **tabled by the owner 11-12**.
    The patch and cover letter are ready on the build box, not sent.

Motion and firmware:
28. **Root and payload builds now take Klipper from the fork**
    (`klipper/get_fork.sh`, 2026-11-13). Syntax-checked and the checkout
    tested on the PC; the first real root or payload build is the test.
    The two printers' `/home/klipper/klipper` are older checkouts: move
    them to the pinned fork commit with the next payload.
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
End-goal install ([docs/end_goal_install_plan.md](docs/end_goal_install_plan.md);
stages 1-5 done on the dev printer):
34. **Stage 6:** installer v2 (USB stick under stock 3.2 writes mtd6, then
    mtd0).
35. **Stage 7:** the full Sindoh-stick revert cycle (YES-YES)
    and the broken-root prompt on hardware.
36. **Stage 8:** the work printer.
37. **Stage 9:** release checklist (PROJECTS #10).
