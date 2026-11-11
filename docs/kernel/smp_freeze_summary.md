# Two-CPU hard freeze: where it stands (2026-11-09)

This summary is for resuming after the weekly usage reset (2026-11-13 19:00 UTC). The kernel session's detailed log is in [nandboot_hang_analysis.md](nandboot_hang_analysis.md). Its hand-over note is `smp_freeze_resume_plan.md` in the shared side-session notes folder. The day-by-day record is in TODO.md (hangs 9 to 25).

## Current state of the dev printer

- **mtd0:** the default `m1-nandboot.uimg` **0bcb101e**, with `maxcpus=1` and no hang watchdog. Its modules are 6f1002ef (the same `.ko` files as every recent build).
  - It was RAM-booted first, then written from a one-CPU boot with the owner's OK.
  - It boots from mtd0 onto the NAND root, with Ethernet, Wi-Fi and Klipper up.
- **The old two-CPU default** dc3b5f20 is kept in `D:\DP200\kernel\out\keep-dc3b5f20\`.
- **The 4GB-SD:**
  - storage only: the marker is renamed to `/.dp200-root.off`, so the root is NAND;
  - its gap may hold an incomplete nandpcs write, which is harmless because sd_raw_boot checks the CRC;
  - its card root has the nandps3 modules; the old card set is in `/var/backups/mods-card-06f000a0.tar`.
- **The serial console is dead until a power cycle.** On 11-09 its shell exited after a second Ctrl-D. Moonraker refuses to reboot ("Cannot reboot from within a lxc container"). The printer itself runs fine.
- **Why it matters:** the owner reports a high single-core load. The vendor 3.2 kernel runs both cores, so ours has to as well. Fixing the two-CPU freeze is a high priority once usage resets.

## What the freeze is

- **What happens:** a silent hard stall of the whole SoC, on two CPUs only.
  - The console, ping, both CPUs' timer interrupts and the UART all stop at once.
  - A tick check on CPU1 (timer 3) printed nothing, and pstore got nothing.
  - The PC samples stop on both CPUs within about 50 µs of each other.
- **What it looks like:** a bus or interconnect stall, not a lost interrupt.
- **Where the CPUs were:** at the freeze, one CPU is usually in page-fault, fault-around or mm code. Often the other was in storage I/O completion: the NAND read ISR entry on the NAND root (4 of 7 runs), or `sdhci_request_done` on the card root. With all the trace and sampler code, that's suggestive but not proof.

## Results (two CPUs unless noted)

| Setup | Kernel | Result |
|---|---|---|
| NAND root | plain dc3b5f20 (mtd0) | froze at about 22-30 min, several times |
| NAND root | **plain nandwdt** (card gap) | **froze at about 20 min** (11-09) |
| NAND root | debug builds nanddbg … nandfa (mostly mtd0) | froze in 60 s to 14 min (hangs 9-15) |
| NAND root | nandirq (debug, card gap) | froze at 490 s |
| NAND root | nandpcs (debug) | **3 h 56 min clean from the card gap; froze at 143 s from mtd0**. The only build with a clean gap soak and a failed mtd0 run; one pair, unexplained |
| NAND root, **1 CPU** | nandup (debug, mtd0) | 2 h clean |
| NAND root, **1 CPU** | nandupw (plain + watchdog, mtd0) | **10 h clean** (151 passes) |
| card root | plain/near-plain, no ramoops driver: nandwdt, nandres, nandpad, nandpad2, nandps2, nandps4, nandrs, nanddrv, nanddrv2 + older plain kernels | all clean, about 16 h in total |
| card root | nandsz (nandres + 10 KB incompressible padding) | froze at **49 min**; one data point, possibly a fluke, rerun queued |
| card root | ramoops platform driver present: nandram, nandrnc, nandrso, nandrwb, nandrmv, nandps0, nandps3 ×2 | all froze in 20 s to 7 min |
| card root | full debug stack nandfa (Wi-Fi on / off) | froze at 106 s / 329 s |

**Boot source (card gap vs mtd0):** no general effect. Freezes happened from both on both roots. nandpcs is the single exception.

**Ruled out:**
- the camera and Wi-Fi;
- the PTE cache clean (nandpte; MMFR3 00102211 says the table walk is coherent);
- the DDR drain write (nandmb);
- the CPU aux-register setup (patch 0001 already ports the vendor's PJ4B setup, so nandvs was a rerun);
- fault-around (nandfa);
- the NAND root as the *only* cause: the card root freezes with the accelerators;
- the image size or kernel layout (nandpad, nandpad2, nandsz);
- the reserved-memory holes (nandres);
- the ramoops mapping type and address (nandrso, nandrwb, nandrmv);
- the pstore fs registration (nandps2);
- the Reed-Solomon library (nandrs);
- a generic postcore platform driver (nanddrv);
- a "ramoops"-named driver probing the reserved-memory device (nanddrv2).

**Accelerator found, mechanism unknown:** registering ramoops' own platform driver.
- nandps3 froze in 2 of 2 runs with **no device and nothing bound**: its DT has no `compatible`.
- nandps4 has the same code but `ramoops_init` returns early, and it ran 55 min clean.

## Reproducers

- **Fast (minutes, card root):** nandps3 `237dde132fe6eb03a6f65db62b3bd46d` (modules 7565bc8f).
- **Real-world (about 20 min, NAND root):** nandwdt `cf897cd804ba26e9857d242ec6ea8808` (modules d7bd2ee2), RAM-booted from the card gap.
- **Workaround:** `maxcpus=1` (default now).

## Candidate 3 result (11-11)

All barriers as `dsb sy` (plus the 6011 window and clrex): nanddsb passed
the 2 h NAND-root soak on two CPUs, the first ever. A 10 h soak follows.

## Next, after the reset

1. **Rerun nandpcs from the card gap on the NAND root, 2 h.** Does its long clean run repeat? If it does, compare its mtd0 boot path.
2. **Rerun nandsz on the card root, 2 h.** Was 49 min a fluke?
3. **The kernel session's fix work against both reproducers.** Compare what the vendor 3.2 kernel does differently with two CPUs.
4. **Use long soaks (2 h+) for the base-rate freezes.** 45-minute soaks only catch the fast ones.

## How tests are run (the method that worked)

- **Install a test image:**
  1. Put it in the card gap with `tools/sd_raw_install.sh`.
  2. RAM-boot it with `tools/sd_raw_boot.sh`. That's the owner's rule: boot every kernel before writing it to NAND.
  3. Install its modules tar.
  4. For mtd0 runs, write it with `tools/mtd0_kernel_update.sh` (served as `deploy/usb/t/kupdate.sh`), **only from a stable kernel**. A write from a fast-freezing kernel froze mid-script once.
- **Soak:** `deploy/usb/t/soak45.sh` / `soak2h.sh` / `soak10h.sh`.
  - Each starts the SD hang logger and the read soak (`irq_soak.sh`: drop_caches plus a full tar of / every 2 min).
  - Kernel lines: `SOAKxx started`, `IRQSOAK TAR n done`, `IRQSOAK DONE n passes`.
- **Watchers on the PC (scratchpad):**
  - **`probe.py`** holds COM3 and sends Enter every 2 s, logging a missed prompt. It stops sending at the first miss or any U-Boot or panic text. Use the `now` mode for a board that's already up.
  - **`tping.py`** pings once a second, with timestamps.
- **Grading:** device output only, never the echoed command. Missed probes plus a ping loss in the same second is a freeze. Lone ping losses are the network.
- **Serial-console safety:**
  - never `exit`, because it reboots the board;
  - never pass an empty variable to head, tail or cat, because they then read the console;
  - to free a stuck console, send ONE Ctrl-D.
- **Usage:** check weekly usage before each run, and pause at 90% (owner).
