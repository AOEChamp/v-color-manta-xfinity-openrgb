"""Loopback OpenRGB SDK v3 bridge for compatible V-Color ENE DDR5 controllers.
SPDX-License-Identifier: GPL-2.0-or-later
"""
import argparse
import logging
import socketserver
import struct
import json
import sys
from config import VERSION, load_config, find_openrgb
from client_settings import configure_client, settings_path
from ene_aura6 import PawnBus, discover
from modes import MODES, SPEED_NORMAL, SPEED_SLOWEST, SPEED_FASTEST, validate_mode

U32 = lambda v: struct.pack('<I', v)
U16 = lambda v: struct.pack('<H', v)

def string(value):
    data = value.encode('utf-8') + b'\0'
    return U16(len(data)) + data

def mode_description(index, speed=None):
    spec = MODES[index]
    if speed is None:
        speed = SPEED_NORMAL if spec.animated else 0
    # value, flags, speed min/max, brightness min/max, color min/max,
    # speed, brightness, direction, color mode; zero mode-specific colors.
    fields = (spec.value, (32 if spec.colors else 0) | 256 | (1 if spec.animated else 0),
              SPEED_SLOWEST if spec.animated else 0, SPEED_FASTEST, 0, 0, 0, 0,
              speed, 0, 0, 1 if spec.colors else 0)
    return string(spec.name) + struct.pack('<12I', *fields) + U16(0)

def description(device):
    with device.lock:
        data = U32(1)  # DEVICE_TYPE_DRAM
        for s in (f'V-Color Manta XFinity DDR5 [{device.address:02X}]', 'V-Color',
                  'Native ENE Aura 6; TMXFL1660830WWK', 'A8 32 16 E8 8C',
                  f'ENE-{device.address:02X}', f'PIIX4 port {getattr(device.bus, "port", 0)}, address 0x{device.address:02X}'):
            data += string(s)
        data += U16(len(MODES)) + U32(device.mode)
        data += b''.join(mode_description(i, device.speeds[i]) for i in range(len(MODES)))
        data += U16(1) + string('DIMM') + struct.pack('<4I', 1, 8, 8, 8) + U16(0)
        data += U16(8)
        for i in range(8): data += string(f'LED {i+1}') + U32(i)
        data += U16(8) + b''.join(bytes([r, g, b, 0]) for r, g, b in device.colors)
        return U32(len(data) + 4) + data

def exact(sock, count):
    result = bytearray()
    while len(result) < count:
        part = sock.recv(count - len(result))
        if not part: raise EOFError()
        result.extend(part)
    return bytes(result)

def update(device, packet, data):
    # Fully validate before touching hardware, including declared sizes.
    if packet in (1050, 1051, 1101, 1102):
        if len(data) < 4 or struct.unpack_from('<I', data)[0] != len(data):
            raise ValueError('Invalid packet size')
    with device.lock:
        if packet in (1050, 1051):
            offset = 4
            if packet == 1051:
                if len(data) < 10 or struct.unpack_from('<I', data, 4)[0] != 0:
                    raise ValueError('Invalid zone')
                offset = 8
            if len(data) != offset + 2 + 32 or struct.unpack_from('<H', data, offset)[0] != 8:
                raise ValueError('Exactly eight colors required')
            device.apply([tuple(data[i:i+3]) for i in range(offset+2, len(data), 4)])
        elif packet == 1052:
            if len(data) != 8: raise ValueError('Invalid single LED packet')
            index = struct.unpack_from('<I', data)[0]
            if index >= 8: raise ValueError('Invalid LED index')
            colors = list(device.colors)
            colors[index] = tuple(data[4:7])
            device.apply(colors)
        elif packet == 1100:
            if data: raise ValueError('Unexpected custom-mode payload')
            device.apply(mode=0)
        elif packet in (1101, 1102):
            if len(data) < 10: raise ValueError('Truncated mode')
            mode = struct.unpack_from('<I', data, 4)[0]
            if mode >= len(MODES): raise ValueError('Invalid mode')
            n = struct.unpack_from('<H', data, 8)[0]
            if n < 1 or len(data) != 10+n+50 or data[10+n-1] != 0:
                raise ValueError('Invalid mode descriptor')
            if struct.unpack_from('<H', data, 10+n+48)[0] != 0:
                raise ValueError('Mode-specific colors unsupported')
            speed = struct.unpack_from('<I', data, 10+n+32)[0]
            validate_mode(mode, speed)
            if packet == 1102:
                device.save(mode=mode, speed=speed)
                logging.info('Save requested for V-Color DIMM at 0x%02X', device.address)
            else:
                device.apply(mode=mode, speed=speed)

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(None)
        try:
            while True:
                magic, dev, packet, size = struct.unpack('<4sIII', exact(self.request, 16))
                if magic != b'ORGB' or size > 4096: raise ValueError('Invalid SDK header')
                data = exact(self.request, size)
                reply = None
                if packet == 40:
                    if len(data) != 4 or struct.unpack('<I', data)[0] < 3:
                        raise ValueError('SDK protocol 3 or newer required')
                    reply = U32(3)
                elif packet == 0:
                    if data: raise ValueError('Unexpected count payload')
                    reply = U32(len(self.server.devices))
                elif packet == 50:
                    continue  # Client name has no hardware effect.
                elif packet == 150:
                    reply = U32(6) + U16(0)  # Profiles are managed by the OpenRGB UI.
                elif packet == 1:
                    if dev >= len(self.server.devices): raise ValueError('Invalid device')
                    if data and data != U32(3): raise ValueError('Invalid descriptor protocol')
                    reply = description(self.server.devices[dev])
                elif packet in (1050, 1051, 1052, 1100, 1101, 1102):
                    if dev >= len(self.server.devices): raise ValueError('Invalid device')
                    update(self.server.devices[dev], packet, data)
                # Unknown commands are intentionally ignored: no resizes/raw I/O.
                if reply is not None:
                    self.request.sendall(struct.pack('<4sIII', b'ORGB', dev, packet, len(reply)) + reply)
        except (EOFError, ConnectionError, TimeoutError): pass
        except (ValueError, OSError, struct.error) as exc:
            logging.error('Connection closed: %s', exc)

class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False
    request_queue_size = 4
    def __init__(self, port, devices):
        self.devices = devices
        super().__init__(('127.0.0.1', port), Handler)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--config', help='JSON configuration file (default: bridge-config.json beside the launcher)')
    parser.add_argument('--openrgb-dir', help='Override the configured OpenRGB folder')
    parser.add_argument('--port', type=int, help='Override the configured loopback SDK port')
    parser.add_argument('--print-config', action='store_true', help='Validate configuration, locate OpenRGB, print JSON and exit without hardware access')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--configure-client', choices=('install', 'remove'), help='Save or remove this localhost SDK connection without hardware access; close OpenRGB first')
    parser.add_argument('--settings-file', help='Override the OpenRGB settings file for --configure-client')
    parser.add_argument('--color', help='Set all DIMMs to RRGGBB and exit')
    parser.add_argument('--list', action='store_true', help='Identify DIMMs without changing colors')
    args = parser.parse_args()
    if args.port is not None:
        if not 1024 <= args.port <= 65535: parser.error('--port must be from 1024 to 65535')
    if args.configure_client:
        port = args.port if args.port is not None else load_config(args.config)['port']
        print(json.dumps(configure_client(settings_path(args.settings_file), port, args.configure_client == 'remove')))
        return
    settings = load_config(args.config)
    if args.port is not None:
        settings['port'] = args.port
    settings['openrgb_dir'] = find_openrgb(args.openrgb_dir or settings['openrgb_dir'])
    if args.print_config:
        print(json.dumps(settings))
        return
    if args.color and (len(args.color) != 6 or any(c not in '0123456789abcdefABCDEF' for c in args.color)):
        parser.error('--color requires six hexadecimal digits')
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    logging.info('V-Color bridge %s; AMD PIIX4 port %d; SDK port %d', VERSION, settings['smbus_port'], settings['port'])
    bus = PawnBus(settings['openrgb_dir'], settings['smbus_port'])
    try:
        devices = discover(bus)
        for d in devices: logging.info('Matched V-Color DIMM at 0x%02X, 8 LEDs; save available (patched E000 assumed)', d.address)
        if args.color:
            color = tuple(bytes.fromhex(args.color))
            for d in devices: d.apply([color]*8, mode=1)
        elif not args.list:
            with Server(settings['port'], devices) as server:
                logging.info('Ready: connect OpenRGB SDK Client to 127.0.0.1:%d', settings['port'])
                server.serve_forever(poll_interval=0.25)
    finally: bus.close()

if __name__ == '__main__':
    try: main()
    except KeyboardInterrupt: pass
    except (OSError, ValueError, RuntimeError) as exc:
        logging.error('%s', exc)
        sys.exit(1)
