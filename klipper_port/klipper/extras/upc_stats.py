# DP200 / UPC port diagnostics: report the step-engine counters of the FM
# MCU (pulses issued, pulses requested while the engine was still busy,
# direction changes that had to wait for a running pulse).
#
# Install: copy to ~/klipper/klippy/extras/, add [upc_stats] to printer.cfg.
# G-code: UPC_STEP_STATS
#
# Copyright (C) 2026  This file may be distributed under the terms of the
# GNU GPLv3 license.

ENGINES = (('X', 0), ('Y', 1), ('Z', 2), ('E', 3))

class UpcStats:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.mcu = self.printer.lookup_object('mcu')     # FM core
        self.query = None
        self.mcu.register_config_callback(self._build_config)
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('UPC_STEP_STATS', self.cmd_UPC_STEP_STATS,
                               desc=self.cmd_UPC_STEP_STATS_help)
    def _build_config(self):
        self.query = self.mcu.lookup_query_command(
            "upc_step_stats engine=%c",
            "upc_step_stats_result engine=%c pulses=%u busy_hits=%u"
            " dir_waits=%u")
    cmd_UPC_STEP_STATS_help = "Report UPC step-engine pulse / busy-hit counters"
    def cmd_UPC_STEP_STATS(self, gcmd):
        if self.query is None:
            raise gcmd.error("upc_stats: FM MCU not configured")
        lines = []
        for name, n in ENGINES:
            r = self.query.send([n])
            lines.append("%s (engine %d): pulses=%d busy_hits=%d dir_waits=%d"
                         % (name, n, r['pulses'], r['busy_hits'],
                            r['dir_waits']))
        gcmd.respond_info("\n".join(lines))

def load_config(config):
    return UpcStats(config)
