"""Read only flash addresses referenced by the recovered save/restore code.

Never sends erase, program, save, halt, reset or SPD commands.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import time
from snapshot_retry import module
from probe_firmware_read import snapshot


def acquire(bus, report, folder, stamp, regions=None):
    if regions is None:
        regions = ((0x10000, 16), (0x1f600, 0x180), (0x1f800, 0x180))
    if any(not (0 <= start <= 0x20000 and 0 < size <= 512) for start, size in regions):
        raise ValueError('Read outside bounded investigation ranges')
    target = 0x71
    report['before'] = [snapshot(bus, a) for a in (0x71, 0x73)]
    old = bytes(bus.read(target, r, 1)[0] for r in (0x410, 0x411, 0x412, 0x413))
    report['registers_before'] = old.hex()
    if old[0] & 0x81:
        raise RuntimeError('Controller busy/enabled; aborted')

    def write(reg, value):
        if reg not in (0x410, 0x411, 0x412, 0x413, 0x415) or not 0 <= value <= 255:
            raise ValueError('Outside strict register/value allowlist')
        if reg == 0x415 and value != 0x13:
            raise ValueError('Only READ command 13 allowed')
        bus.select(target, reg)
        bus.transfer(target, 0, 1, 2, value)

    def read(start, length):
        write(0x411, start & 255)
        write(0x412, (start >> 8) & 255)
        write(0x413, (start >> 16) & 255)
        data = bytearray()
        for _ in range(length):
            write(0x415, 0x13)
            deadline = time.monotonic() + 0.1
            while bus.read(target, 0x410, 1)[0] & 0x80:
                if time.monotonic() > deadline:
                    raise TimeoutError('Read timeout; no retry')
            data.extend(bus.read(target, 0x414, 1))
        return bytes(data)

    try:
        write(0x410, old[0] | 1)
        if bus.read(target, 0x410, 1)[0] != old[0] | 1:
            raise RuntimeError('Enable mismatch')
        report['regions'] = []
        for start, size in regions:
            first, second = read(start, size), read(start, size)
            if first != second:
                raise RuntimeError(f'Unstable read at {start:#x}')
            path = folder / f'config-{stamp}-{start:05x}.bin'
            path.write_bytes(first)
            report['regions'].append(dict(start=hex(start), bytes=size, matching_reads=True,
                                          sha256=hashlib.sha256(first).hexdigest(),
                                          path=str(path), data=first.hex()))
    finally:
        report['restore_errors'] = []
        for r, v in ((0x411, old[1]), (0x412, old[2]), (0x413, old[3]), (0x410, old[0])):
            try:
                write(r, v)
            except Exception as exc:
                report['restore_errors'].append(str(exc))
        report['registers_after'] = bytes(bus.read(target, r, 1)[0] for r in (0x410, 0x411, 0x412, 0x413)).hex()
        report['registers_restored'] = report['registers_before'] == report['registers_after']
        report['after'] = [snapshot(bus, a) for a in (0x71, 0x73)]
        report['lighting_unchanged'] = report['before'] == report['after']
        if report['restore_errors'] or not report['registers_restored']:
            raise RuntimeError('Register restoration failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--boundary', action='store_true', help='Sample across 64 KB and 128 KB address boundaries')
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = Path(__file__).resolve().parents[1] / 'evidence' / 'ram-firmware'
    report = dict(hardware_read=True, target='0x71', read_command='0x13',
                  erase_program_save_reset_commands=False, boundary_probe=args.boundary)
    bus = None
    try:
        bus = module.PawnBus()
        with bus.transaction():
            regions = ((0, 16), (0xff80, 256), (0x10000, 128), (0x10100, 128),
                       (0x1ff80, 256), (0x20000, 16)) if args.boundary else None
            acquire(bus, report, folder, stamp, regions)
    except BaseException as exc:
        report['error'] = str(exc)
        raise
    finally:
        if bus:
            bus.close()
        path = folder / f'config-read-{stamp}.json'
        path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(path)
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
