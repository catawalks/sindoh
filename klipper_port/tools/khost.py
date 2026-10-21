"""Read-only hardware test of the UPC Klipper firmware over 'upctool bridge -f tcp:9100 -i tcp:9101'.
Uses klippy's msgproto. Configures ONLY inputs (analog_in, endstops): nothing moves or heats.
usage: khost.py KLIPPER_TREE PRINTER_IP"""
import socket, struct, sys, time
kl, ip = sys.argv[1], sys.argv[2]
sys.path.insert(0, kl + '/klippy')
import msgproto

class Mcu:
    def __init__(self, name, port):
        self.name = name
        self.s = socket.create_connection((ip, port), timeout=5)
        self.s.settimeout(0.05)
        self.p = msgproto.MessageParser()
        self.seq = 0
        self.mcu_next = None
        self.buf = bytearray()

    def send(self, text):
        cmd = self.p.create_command(text)
        blk = [msgproto.MESSAGE_MIN + len(cmd), (self.seq & 0x0f) | msgproto.MESSAGE_DEST] + cmd
        blk += msgproto.crc16_ccitt(blk) + [msgproto.MESSAGE_SYNC]
        self.seq = (self.seq + 1) & 0x0f
        self.s.sendall(bytes(blk))
        # No retransmit/flow control here (klippy has both): pace commands so
        # unacknowledged data never exceeds the MCU's 192-byte RECEIVE_WINDOW.
        time.sleep(0.03)

    def recv(self, wait=0.1):
        end = time.time() + wait
        msgs = []
        while time.time() < end:
            try:
                d = self.s.recv(4096)
                if d:
                    self.buf += d
            except socket.timeout:
                pass
            while self.buf:
                n = self.p.check_packet(bytes(self.buf))
                if n == 0:
                    break
                if n < 0:
                    del self.buf[:-n]
                    continue
                blk = bytes(self.buf[:n]); del self.buf[:n]
                # Every frame header carries the sequence the MCU expects next
                self.mcu_next = blk[msgproto.MESSAGE_POS_SEQ] & msgproto.MESSAGE_SEQ_MASK
                pos = msgproto.MESSAGE_HEADER_SIZE
                while pos < len(blk) - msgproto.MESSAGE_TRAILER_SIZE:
                    mid, _ = self.p.msgid_parser.parse(blk, pos)
                    mt = self.p.messages_by_id.get(mid, self.p.unknown)
                    params, pos = mt.parse(blk, pos)
                    params['#name'] = mt.name
                    params['#time'] = time.time()
                    msgs.append(params)
        return msgs

    def transact(self, text, want, wait=2.0):
        got = []
        for attempt in range(4):
            self.send(text)
            end = time.time() + wait / 4
            while time.time() < end:
                for m in self.recv(0.05):
                    if m['#name'] == want:
                        return m
                    got.append(m)
            # No answer: resynchronize to the sequence the MCU expects (as klippy does)
            if self.mcu_next is not None:
                self.seq = self.mcu_next
        raise SystemExit('%s: no %s for %r (got %r)' % (self.name, want, text, got[-3:]))

    def identify(self):
        data = b''
        while True:
            r = self.transact('identify offset=%d count=40' % len(data), 'identify_response')
            if not r['data']:
                break
            data += bytes(r['data'])
        self.p.process_identify(data)
        c = self.p.get_constants()
        print('%s: identify OK (%d byte dict) MCU=%s version=%s CLOCK_FREQ=%s'
              % (self.name, len(data), c['MCU'], self.p.get_version_info()[0], c['CLOCK_FREQ']))

    def clock(self):
        t0 = time.time()
        r = self.transact('get_clock', 'clock')
        t1 = time.time()
        return r['clock'], (t0 + t1) / 2, t1 - t0

fm = Mcu('FM', 9100)
io = Mcu('IO', 9101)
fm.identify(); io.identify()
for m in (fm, io):
    r = m.transact('get_config', 'config')
    print('%s: is_config=%d is_shutdown=%d move_count=%d' % (m.name, r['is_config'], r['is_shutdown'], r['move_count']))

# Clock: rate against this PC, and FM/IO offset (both cores share Timer1)
samples = {fm: [], io: []}
for i in range(8):     # 7 s span: must stay below one 32-bit wrap (10.8 s at 396 MHz)
    for m in (fm, io):
        samples[m].append(m.clock())
    time.sleep(1.0)
for m in (fm, io):
    (c0, t0, _), (c1, t1, _) = samples[m][0], samples[m][-1]
    rate = ((c1 - c0) & 0xffffffff) / (t1 - t0)
    rtt = sorted(x[2] for x in samples[m])
    print('%s: clock rate %.0f Hz over %.1f s, rtt min %.1f ms median %.1f ms'
          % (m.name, rate, t1 - t0, rtt[0] * 1e3, rtt[len(rtt) // 2] * 1e3))

# Inputs on the FM core: endstops (config only inputs, then query)
fm.send('allocate_oids count=4')
for oid, pin in enumerate(('xena42', 'xena43', 'xena44', 'xena46')):
    fm.send('config_endstop oid=%d pin=%s pull_up=0' % (oid, pin))
fm.send('finalize_config crc=0')
for oid, pin in enumerate(('xena42', 'xena43', 'xena44', 'xena46')):
    r = fm.transact('endstop_query_state oid=%d' % oid, 'endstop_state')
    print('FM: %s pin_value=%d' % (pin, r['pin_value']))

# Thermistors on the IO core: 8 samples like a Klipper heater
io.send('allocate_oids count=2')
io.send('config_analog_in oid=0 pin=adc0')
io.send('config_analog_in oid=1 pin=adc1')
io.send('finalize_config crc=0')
now = io.clock()[0]
for oid in (0, 1):
    io.send('query_analog_in oid=%d clock=%d sample_ticks=%d sample_count=8 rest_ticks=%d'
            ' bytes_per_report=2 min_value=0 max_value=8184 range_check_count=0'
            % (oid, (now + 396000000 // 2 + oid * 1000) & 0xffffffff, 396000, 396000000 * 3 // 10))
vals = {0: [], 1: []}
end = time.time() + 4
while time.time() < end:
    for m in io.recv(0.1):
        if m['#name'] == 'analog_in_state':
            vals[m['oid']].append(int.from_bytes(bytes(m['values'][:2]), 'little'))
for oid, name in ((0, 'nozzle adc0'), (1, 'bed adc1')):
    v = vals[oid]
    print('IO: %s: %d reports, sum8 %s -> raw avg %.1f' % (name, len(v), v[:4], (sum(v) / len(v) / 8) if v else -1))
for m in (fm, io):
    r = m.transact('get_config', 'config')
    print('%s: final is_shutdown=%d' % (m.name, r['is_shutdown']))
