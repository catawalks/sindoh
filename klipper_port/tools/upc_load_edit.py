#!/usr/bin/env python3
# UPC load in Klipper's stats (2026-11-09): count the timer work that the
# UPC port runs inside irq_wait() and give it back to run_tasks()'s stats,
# so mcu_awake / mcu_task_avg (Mainsail's MCU load) include step timing.
# usage: python3 upc_load_edit.py KLIPPER_TREE
import sys
t = sys.argv[1]

def edit(path, old, new):
    s = open(path).read()
    assert s.count(old) == 1, (path, old[:40])
    open(path, 'w').write(s.replace(old, new))

edit(t + '/src/upc/main.c',
"""void
irq_poll(void)
{
    if (timer_pending()) {
        timer_clear_pending();
        uint32_t next = timer_dispatch_many_polling();
        timer_set(next);
    }""",
"""// Ticks spent dispatching timers since sched.c last reset it. Timers run
// from irq_poll(), also while run_tasks() "sleeps" in irq_wait(), which its
// stats leave out; sched.c adds this back so mcu_awake shows the real load.
uint32_t upc_sleep_busy;

void
irq_poll(void)
{
    if (timer_pending()) {
        timer_clear_pending();
        uint32_t t0 = timer_read_time();
        uint32_t next = timer_dispatch_many_polling();
        timer_set(next);
        upc_sleep_busy += timer_read_time() - t0;
    }""")

edit(t + '/src/sched.c',
"""            start -= timer_read_time();
            irq_disable();""",
"""            start -= timer_read_time();
#if CONFIG_MACH_UPC
            extern uint32_t upc_sleep_busy;
            upc_sleep_busy = 0;
#endif
            irq_disable();""")

edit(t + '/src/sched.c',
"""            irq_enable();
            start += timer_read_time();""",
"""            irq_enable();
            start += timer_read_time();
#if CONFIG_MACH_UPC
            // count the timer work done while "asleep" (UPC: no interrupts)
            start -= upc_sleep_busy;
#endif""")
print('UPC-LOAD-EDIT OK')
