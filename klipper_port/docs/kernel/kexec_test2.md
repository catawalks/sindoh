# Ethernet fast path test 2 (2026-10-29): kexec works, the watchdog safety net works

Loader m1-eth f3331420 (SD card), next = m1-sd (zImage d4bb52a2, dtb 12334a23 via --dtb).
Loader link up at 10.4 s, fetch, watchdog armed 60 s, kexec at 12.5 s. m1-sd: watchdog stopped at
time_init, 2 CPUs, SD read-only, Ethernet 100/Full. Still up at 90 s uptime; wdt reg 0x0000000A, timer0 ctrl 0.

```
33:[    0.000000] Linux version 6.18.59 (user@DESKTOP-L41KPL5) (arm-linux-gnueabihf-gcc (Debian 14.2.0-19) 14.2.0, GNU ld (GNU Binutils for Debian) 2.44) #8 Thu Oct 29 20:00:37 EDT 2026
137:=== DP200 eth loader: Linux (none) 6.18.59 #8 Thu Oct 29 20:00:37 EDT 2026 armv7l
170:[   10.448964] stmmaceth f9050000.ethernet eth0: Link is Up - 100Mbps/Full - flow control off
186:next-zImage-dtb.bin: 2203886 bytes, md5 d4bb52a2b42606474abfef4ec880ae37
187:next.dtb: 4598 bytes, md5 12334a23cf13d8f1dcb7cc51db8cac3e
188:[   12.495136] stmmaceth f9050000.ethernet eth0: Link is Down
189:netload: watchdog armed, 60 s
190:netload: starting[   12.546213] kexec_core: Starting new kernel
196:[    0.000000] Linux version 6.18.59 (user@DESKTOP-L41KPL5) (arm-linux-gnueabihf-gcc (Debian 14.2.0-19) 14.2.0, GNU ld (GNU Binutils for Debian) 2.44) #4 SMP Thu Oct 29 20:01:07 EDT 2026
228:[    0.000000] mv61x0-timer: stopped the watchdog the loader armed (wdt 0000000a)
347:=== DP200 milestone 1: Linux (none) 6.18.59 #4 SMP Thu Oct 29 20:01:07 EDT 2026 armv7l
361:--- CPUs online: 0-1, framebuffer: 0 simple
372: 32:          0       [    1.345539] mmcblk0: mmc0:f3c8 SU02G 1.84 GiB
374: 33:          1         [    1.355690]  mmcblk0: p1
460:[    7.498402] stmmaceth f9050000.ethernet eth0: Link is Up - 100Mbps/Full - flow control off
534:<6>[    1.345539] mmcblk0: mmc0:f3c8 SU02G 1.84 GiB
535:<6>[    1.355690]  mmcblk0: p1
542:--- mmcblk0: 3862528 sectors, read-only 1 (1 = yes)
```
