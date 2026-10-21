"""Read-only probe of the DP200 cartridge chip.

Path: /dev/i2c-3 -> DS2465 (I2C to 1-Wire bridge with SHA-256 coprocessor,
"Smart-IC" in the stock kernel) -> 1-Wire -> the cartridge's secure
authenticator (DS28Exx family, per the stock app's function names).

Only these DS2465 operations are used:
  - register reads (status 61h, read data 62h, configuration 67h)
  - 1-Wire Reset      (command B4h)
  - 1-Wire Write Byte (command A5h) - only to send 1-Wire ROM command 33h (Read ROM)
  - 1-Wire Read Byte  (command 96h)
Never sent: Copy Scratchpad, Compute (Next) Secret, Compute MAC, Set Protection,
or any 1-Wire memory-write command. Run as root in the Debian chroot:
    /usr/bin/python3 cartridge_probe.py [--addr 0x18]
"""
import fcntl, os, sys, time

I2C_SLAVE = 0x0703
REG_CMD, REG_STATUS, REG_DATA, REG_CONFIG = 0x60, 0x61, 0x62, 0x67
ST_1WB, ST_PPD, ST_SD, ST_LL, ST_RST = 0x01, 0x02, 0x04, 0x08, 0x10

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

class Bridge:
    def __init__(self, bus, addr):
        self.fd = os.open('/dev/i2c-%d' % bus, os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, addr)

    def read_reg(self, reg, n=1):
        os.write(self.fd, bytes([reg]))          # set the read pointer
        return os.read(self.fd, n)

    def cmd(self, *b):
        os.write(self.fd, bytes([REG_CMD] + list(b)))

    def wait(self):
        for _ in range(200):
            st = self.read_reg(REG_STATUS)[0]
            if not st & ST_1WB:
                return st
            time.sleep(0.001)
        raise TimeoutError('1-Wire busy')

    def ow_reset(self):
        self.cmd(0xB4)
        return self.wait()

    def ow_write(self, byte):
        self.cmd(0xA5, byte)
        self.wait()

    def ow_read(self):
        self.cmd(0x96)
        self.wait()
        return self.read_reg(REG_DATA)[0]

def main():
    addrs = [int(sys.argv[sys.argv.index('--addr') + 1], 0)] if '--addr' in sys.argv else [0x18, 0x30]
    br = None
    for a in addrs:
        try:
            b = Bridge(3, a)
            st = b.read_reg(REG_STATUS)[0]
            cfg = b.read_reg(REG_CONFIG)[0]
            print('bridge at 0x%02x: status=0x%02x config=0x%02x' % (a, st, cfg))
            br = b
            break
        except OSError as e:
            print('no answer at 0x%02x (%s)' % (a, e.strerror))
    if not br:
        sys.exit('no DS2465 found on /dev/i2c-3')
    # Device configuration (67h, a plain register, not EEPROM): low nibble
    # APU(0) PDN(1) SPU(2) 1WS(3), high nibble = its complement.
    if '--apu' in sys.argv:
        os.write(br.fd, bytes([REG_CONFIG, 0xE1]))      # active pull-up on
        print('config now 0x%02x' % br.read_reg(REG_CONFIG)[0])
    # 1-Wire port configuration (68h-6Dh, volatile SRAM, datasheet Table 6):
    # --rwpu 0 = 500 ohm weak pull-up (default code 6 = 1000 ohm)
    if '--rwpu' in sys.argv:
        code = int(sys.argv[sys.argv.index('--rwpu') + 1])
        os.write(br.fd, bytes([0x6C, code & 0x0F]))
    # --tmsp N: standard-speed presence sample time code (0 = 58 us, default 6 = 68 us)
    if '--tmsp' in sys.argv:
        code = int(sys.argv[sys.argv.index('--tmsp') + 1])
        os.write(br.fd, bytes([0x69, 0x60 | (code & 0x0F)]))
    # --od: 1-Wire overdrive speed (config bit 1WS) for all following operations
    if '--od' in sys.argv:
        low = 0x08 | (0x01 if '--apu' in sys.argv else 0)
        os.write(br.fd, bytes([REG_CONFIG, ((~low << 4) & 0xF0) | low]))
        print('overdrive: config now 0x%02x' % br.read_reg(REG_CONFIG)[0])
    print('port config 68h-6Dh: %s' % br.read_reg(0x68, 6).hex(' '))
    st = br.ow_reset()
    print('1-Wire reset: status=0x%02x presence=%s short=%s line=%s' % (
        st, bool(st & ST_PPD), bool(st & ST_SD), 'high' if st & ST_LL else 'low'))
    if not st & ST_PPD:
        sys.exit('no 1-Wire device answered (is the cartridge seated?)')
    br.ow_write(0x33)                            # Read ROM (single device on the bus)
    rom = bytes(br.ow_read() for _ in range(8))
    ok = crc8(rom[:7]) == rom[7]
    print('ROM: %s  family=0x%02x serial=%s crc=%s' % (
        rom.hex(' '), rom[0], rom[6:0:-1].hex(), 'OK' if ok else 'BAD'))
    names = {0x17: 'DS28E15 (SHA-256, 512 bit)', 0x47: 'DS28E25 (SHA-256, 4 kbit)',
             0x48: 'DS28E22 (SHA-256, 2 kbit)', 0x37: 'DS28E01-100 (SHA-1, 1 kbit)',
             0xB3: 'DS2432 (SHA-1, 1 kbit)', 0x33: 'DS1961S/DS2432 (SHA-1)',
             0x2D: 'DS2431 (plain 1 kbit EEPROM)', 0x23: 'DS2433 (plain 4 kbit EEPROM)'}
    print('family:', names.get(rom[0], 'unknown - look up 0x%02x' % rom[0]))
    if '--dump' in sys.argv and rom[0] == 0x48 and ok:
        dump_ds28e22(br)
    br.ow_reset()                                # leave the bus idle

# 1-Wire CRC16 (x^16 + x^15 + x^2 + 1, reflected); the device sends ~crc LSB first,
# so crc16(data + response) == 0xB001 when both match (as in Maxim's MaximInterface).
def crc16(data, crc=0):
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc

# DS28E15/22/25 memory function commands (MaximInterface DS28E15_22_25.hpp).
# READ-ONLY subset - write/secret/MAC commands are deliberately absent.
READ_MEMORY, READ_STATUS = 0xF0, 0xAA
SKIP_ROM = 0xCC

def ds_command(br, cmd, param):
    """Reset, Skip ROM, send command + parameter, check the echoed CRC16."""
    assert cmd in (READ_MEMORY, READ_STATUS)
    if not br.ow_reset() & ST_PPD:
        raise IOError('no presence')
    br.ow_write(SKIP_ROM)
    br.ow_write(cmd)
    br.ow_write(param)
    resp = bytes([br.ow_read(), br.ow_read()])
    if crc16(resp, crc16(bytes([cmd, param]))) != 0xB001:
        raise IOError('command CRC mismatch (cmd %02x param %02x): %s' % (cmd, param, resp.hex()))

def ds_read(br, n):
    data = bytes(br.ow_read() for _ in range(n))
    resp = bytes([br.ow_read(), br.ow_read()])
    if crc16(resp, crc16(data)) != 0xB001:
        raise IOError('data CRC mismatch')
    return data

def dump_ds28e22(br):
    ds_command(br, READ_STATUS, 0xE0)
    pers = ds_read(br, 4)
    print('personality: PB1=%02x PB2=%02x manufacturer ID=%02x%02x' % (pers[0], pers[1], pers[3], pers[2]))
    ds_command(br, READ_STATUS, 0x00)
    prot = ds_read(br, 16)                      # DS28E22: 8 bytes used, 16 read for the CRC
    for blk in range(4):
        s = prot[blk * 2]
        flags = [n for m, n in ((0x80, 'READ-PROT'), (0x40, 'WRITE-PROT'), (0x20, 'EPROM'), (0x10, 'AUTH'))
                 if s & m]
        print('block %d (pages %d-%d): status %02x %s' % (blk, blk * 2, blk * 2 + 1, s,
                                                         ' '.join(flags) or 'open'))
    for page in range(8):
        ds_command(br, READ_MEMORY, page)
        data = ds_read(br, 32)
        txt = ''.join(chr(c) if 32 <= c < 127 else '.' for c in data)
        print('page %d: %s  |%s|' % (page, data.hex(' '), txt))

main()
