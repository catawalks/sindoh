# Re-check the MCU clock frequency once the clock estimate has settled
#
# At klippy:ready, klippy/mcu.py compares each MCU's configured CLOCK_FREQ
# with the host's clock estimate and adds a runtime warning ("MCU 'io'
# configured for 396Mhz but running at 389Mhz!") when they differ by more than
# 1 %. On the DP200 the UPC cores' first clock samples arrive through the
# shared-memory bridge while it is busy with the identify/config traffic, so
# the estimate at that moment is often 1-2 % low; seconds later it settles at
# 395.9x MHz (0.02 % off). This module repeats the same check SETTLE seconds
# after ready and withdraws the warning when the settled estimate agrees.
# A real frequency problem keeps its warning.
#
# While the estimate is still off, MCU commands get scheduled against the
# wrong clock: a print started 1 s after a RESTART failed in G28 with "MCU
# shutdown: Timer too close" (2026-10-27). UPC_WAIT_CLOCK [TIMEOUT=60] waits
# until every MCU's estimate is within 0.3 %; the DP200 homing override
# calls it first.
#
#   [upc_clockcheck]
#   #settle_time: 30
#
# Copyright (C) 2026  This file may be distributed under the terms of the
# GNU GPLv3 license.
import logging

class UPCClockCheck:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.settle = config.getfloat('settle_time', 30., minval=2.)
        self.printer.register_event_handler("klippy:ready", self._ready)
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('UPC_WAIT_CLOCK', self.cmd_UPC_WAIT_CLOCK,
                               desc=self.cmd_UPC_WAIT_CLOCK_help)

    def _ready(self):
        reactor = self.printer.get_reactor()
        reactor.register_timer(self._recheck, reactor.monotonic() + self.settle)

    def _estimates(self, eventtime):
        # (mcu, configured Hz, currently estimated Hz) for every MCU
        for name, mcu in self.printer.lookup_objects(module='mcu'):
            mcu_freq = mcu.seconds_to_clock(1.)
            calc_freq = mcu.estimated_print_time(eventtime + 1.) - mcu.estimated_print_time(eventtime)
            yield mcu, mcu_freq, calc_freq * mcu_freq

    cmd_UPC_WAIT_CLOCK_help = "Wait until the MCU clock estimates have settled (after a restart)"
    def cmd_UPC_WAIT_CLOCK(self, gcmd):
        timeout = gcmd.get_float('TIMEOUT', 60., minval=0.)
        reactor = self.printer.get_reactor()
        end = reactor.monotonic() + timeout
        told = False
        while True:
            now = reactor.monotonic()
            off = max([abs(c - f) / f for m, f, c in self._estimates(now)] or [0.])
            if off <= 0.003:
                if told:
                    gcmd.respond_info("MCU clock settled")
                return
            if now > end:
                raise gcmd.error("MCU clock estimate still %.1f %% off after %.0f s"
                                 % (off * 100., timeout))
            if not told:
                gcmd.respond_info("Waiting for the MCU clock estimate to settle"
                                  " (%.1f %% off)" % (off * 100.))
                told = True
            reactor.pause(now + 1.)

    def _recheck(self, eventtime):
        pconfig = self.printer.lookup_object('configfile')
        for mcu, mcu_freq, calc_freq in self._estimates(eventtime):
            mcu_name = mcu.get_name()
            mhz = int(mcu_freq / 1000000. + 0.5)
            if abs(mcu_freq - calc_freq) > mcu_freq * 0.01:
                logging.info("upc_clockcheck: MCU '%s' still at %.3f MHz",
                             mcu_name, calc_freq / 1e6)
                continue
            prefix = "MCU '%s' configured for %dMhz but running at" % (mcu_name, mhz)
            stale = [w for w in pconfig.status_warnings
                     if w.get('type') == 'runtime_warning'
                     and w.get('message', '').startswith(prefix)]
            if not stale:
                continue
            for w in stale:
                pconfig.deprecated.pop(tuple(list(w.items())), None)
            pconfig.status_warnings = [w for w in pconfig.status_warnings
                                       if w not in stale]
            logging.info("upc_clockcheck: MCU '%s' settled at %.3f MHz;"
                         " start-up frequency warning withdrawn",
                         mcu_name, calc_freq / 1e6)
        return self.printer.get_reactor().NEVER

def load_config(config):
    return UPCClockCheck(config)
