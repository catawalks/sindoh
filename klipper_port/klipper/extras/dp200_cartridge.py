# Read-only support for the Sindoh DP200 filament cartridge chip
#
# Path: /dev/i2c-3 -> DS2465 I2C-to-1-Wire bridge (address 0x18) -> DS28E22
# secure authenticator in the cartridge, which talks at overdrive speed only.
# Memory layout and units were decoded from the stock firmware; see
# docs/cartridge_chip.md of the DP200 port. Nothing is ever written to the
# chip: only 1-Wire Read ROM / Read Memory / Read Status are sent.
#
#   [dp200_cartridge]
#   #i2c_device: /dev/i2c-3
#   #i2c_address: 24            # 0x18
#
# G-code: CARTRIDGE_READ (re-read the chip; not while printing)
# Status: printer["dp200_cartridge"] -> present, rom_id, product, material,
#   total_m, used_m, remaining_m, remaining_percent, fuses_used, error
#
# Copyright (C) 2026  This file may be distributed under the terms of the
# GNU GPLv3 license.
import fcntl, logging, os, struct, threading, time

I2C_SLAVE = 0x0703
REG_CMD, REG_STATUS, REG_DATA, REG_CONFIG = 0x60, 0x61, 0x62, 0x67
ST_1WB, ST_PPD = 0x01, 0x02
CFG_OVERDRIVE_APU = 0x69          # low nibble 1WS|APU = 0x9, high nibble = complement
OW_RESET, OW_WRITE_BYTE, OW_READ_BYTE = 0xB4, 0xA5, 0x96   # DS2465 function commands
READ_ROM, SKIP_ROM = 0x33, 0xCC                              # 1-Wire ROM commands
READ_MEMORY, READ_STATUS = 0xF0, 0xAA                        # DS28E22 (read-only subset)
FAMILY_DS28E22 = 0x48
MM_PER_EPULSE = 500. / 458.83     # stock: ePulse x 500 extruder steps / (458.83 steps/mm)

def crc8(data):
    crc = 0
    for b in data:
        for _ in range(8):
            mix = (crc ^ b) & 1
            crc >>= 1
            if mix:
                crc ^= 0x8C
            b >>= 1
    return crc

def crc16(data, crc=0):
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc

class CartridgeError(Exception):
    pass

class DS2465Link:
    def __init__(self, device, address):
        self.fd = os.open(device, os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, address)
    def close(self):
        os.close(self.fd)
    def _reg(self, reg):
        os.write(self.fd, bytes([reg]))
        return os.read(self.fd, 1)[0]
    def _wait(self):
        for _ in range(200):
            st = self._reg(REG_STATUS)
            if not st & ST_1WB:
                return st
            time.sleep(0.0005)
        raise CartridgeError("1-Wire bus stuck busy")
    def setup(self):
        os.write(self.fd, bytes([REG_CONFIG, CFG_OVERDRIVE_APU]))
    def reset(self):
        os.write(self.fd, bytes([REG_CMD, OW_RESET]))
        return bool(self._wait() & ST_PPD)
    def write(self, b):
        os.write(self.fd, bytes([REG_CMD, OW_WRITE_BYTE, b]))
        self._wait()
    def read(self, n=1):
        out = bytearray()
        for _ in range(n):
            os.write(self.fd, bytes([REG_CMD, OW_READ_BYTE]))
            self._wait()
            out.append(self._reg(REG_DATA))
        return bytes(out)

def read_cartridge(device, address):
    """Read ROM, the data pages and the fuse pages. Returns a dict."""
    link = DS2465Link(device, address)
    try:
        link.setup()
        if not link.reset():
            return {'present': False}
        link.write(READ_ROM)
        rom = link.read(8)
        if crc8(rom[:7]) != rom[7]:
            raise CartridgeError("ROM CRC error")
        if rom[0] != FAMILY_DS28E22:
            raise CartridgeError("unknown chip family 0x%02x" % rom[0])
        def command(cmd, param):
            assert cmd in (READ_MEMORY, READ_STATUS)       # read-only by design
            if not link.reset():
                raise CartridgeError("cartridge removed")
            link.write(SKIP_ROM)
            link.write(cmd)
            link.write(param)
            if crc16(link.read(2), crc16(bytes([cmd, param]))) != 0xB001:
                raise CartridgeError("command CRC error")
        def page(n):
            command(READ_MEMORY, n)
            data = link.read(32)
            if crc16(link.read(2), crc16(data)) != 0xB001:
                raise CartridgeError("page %d CRC error" % n)
            return data
        p0, p2, p3, p6, p7 = page(0), page(2), page(3), page(6), page(7)
    finally:
        link.reset()
        link.close()
    total_m = struct.unpack_from('<I', p0, 28)[0]
    used_mm = struct.unpack_from('<I', p2, 4)[0] * MM_PER_EPULSE
    remaining_m = max(0., total_m - used_mm / 1000.)
    product = p0[:12].decode('ascii', 'replace').rstrip('\0')
    # 1 = PLA, 2 = ABS (stock app), 6 = Flex (black flex cartridge, 2026-10-22)
    code = struct.unpack_from('<I', p0, 16)[0]
    material = {1: 'PLA', 2: 'ABS', 6: 'FLEX'}.get(code, 'code %d' % code)
    fuses = sum(8 - bin(b).count('1') for b in p6 + p7)   # cleared EPROM bits
    return {
        'present': True,
        'rom_id': rom.hex(),
        'product': product,
        'material': material,
        'total_m': total_m,
        'used_m': round(used_mm / 1000., 2),
        'remaining_m': round(remaining_m, 2),
        'remaining_percent': round(100. * remaining_m / total_m, 1) if total_m else 0.,
        'fuses_used': fuses,
        'params': list(struct.unpack_from('<6I', p3, 0)),
    }

class DP200Cartridge:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.device = config.get('i2c_device', '/dev/i2c-3')
        self.address = config.getint('i2c_address', 0x18)
        self.status = {'present': False, 'error': None}
        self.busy = False
        self.printer.register_event_handler("klippy:ready", self._start_read)
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('CARTRIDGE_READ', self.cmd_CARTRIDGE_READ,
                               desc="Read the filament cartridge chip (read-only)")
    def _start_read(self):
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._worker, daemon=True).start()
        return True
    def _worker(self):
        # I2C/1-Wire I/O happens off the reactor thread
        try:
            result = read_cartridge(self.device, self.address)
            result['error'] = None
        except (OSError, CartridgeError) as e:
            result = {'present': False, 'error': str(e)}
        self.reactor.register_async_callback(lambda et: self._done(result))
    def _done(self, result):
        self.busy = False
        self.status = result
        if result.get('present'):
            msg = ("Cartridge %s (%s): %.1f of %d m left (%.0f%%)"
                   % (result['product'], result['material'], result['remaining_m'],
                      result['total_m'], result['remaining_percent']))
        else:
            msg = "No cartridge chip" + (" (%s)" % result['error'] if result.get('error') else "")
        logging.info("dp200_cartridge: %s", msg)
        self.printer.lookup_object('gcode').respond_info(msg)
    def cmd_CARTRIDGE_READ(self, gcmd):
        ps = self.printer.lookup_object('print_stats', None)
        if ps is not None and ps.get_status(self.reactor.monotonic())['state'] == 'printing':
            raise gcmd.error("CARTRIDGE_READ is not allowed while printing")
        if not self._start_read():
            gcmd.respond_info("Cartridge read already in progress")
    def get_status(self, eventtime):
        return dict(self.status, busy=self.busy)

def load_config(config):
    return DP200Cartridge(config)
