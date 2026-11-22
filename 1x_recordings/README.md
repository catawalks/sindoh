# 3DWOX 1X: recordings of the stock firmware

Raw logs behind [docs/1x_stock_routines.md](../docs/1x_stock_routines.md),
taken read-only on the owner's stock 1X (PLA, open filament).

| File | What |
|---|---|
| `movewatch_unload_load_cleanbin_2026-11-22.log` | Every motor move, input change and fan/lamp/solenoid change during a stock unload, load and "clean bin" (sindoh-klipper `host/movewatch.c`). `M start end axis dir steps mm`, `I time input level`, `P time block ctrl high/low`; times are seconds of uptime. |
| `console_unload_load_cleanbin_2026-11-22.log` | The stock console text of the same run, with PC times. |
| `movewatch_home_and_bed_leveling_2026-11-22.log` | A stock "home all" from mid-travel (uptime 135 to 162 s, twice) and the whole bed leveling routine (from 227 s): nozzle wipe, the scrub on the bed, three touches at each of three points, the pause while the owner turned the wheels (391 to 433 s), and the second round. |
| `regwatch_first_run_2026-11-22.log` | An earlier run of the same three routines, sampled once a second (`host/regwatch.c`): totals per second, too coarse for the X moves. |
| `console_first_run_2026-11-22.log` | Its console text. |

Direction pin levels in `M` lines: X 1 = left (toward home), Y 1 =
bed forward (away from home), Z 1 = bed down, E and C 0 = feed.
