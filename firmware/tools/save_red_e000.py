"""Apply red and issue one patched-firmware AA save, then read E000 settings.

No reset, bootloader entry, firmware flashing, or direct flash programming.
"""
import argparse
import datetime
import json
from pathlib import Path
import time
from snapshot_retry import module
from probe_firmware_read import snapshot
from read_ram_config_regions import acquire
from build_e000_firmware import build, SOURCE, OUTPUT

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'images'


def run(bus, report, save, stamp, v2=False):
    if v2:
        from build_e000_v2_firmware import build as builder, OUTPUT as output
    else:
        builder, output = build, OUTPUT
    candidate, _ = builder(SOURCE.read_bytes())
    report['firmware_version'] = 'E000 v2' if v2 else 'E000 v1'
    if output.read_bytes() != candidate:
        raise RuntimeError('Candidate does not match reproducible build')
    report['initial'] = [snapshot(bus, a) for a in (0x71, 0x73)]
    if bus.read(0x71, 0x606, 1) != b'\x00' or bus.read(0x71, 0x202, 1)[0] & 1:
        raise RuntimeError('Target is not running application mode')
    preflight = report.setdefault('firmware_preflight', {})
    addresses = (0x2000, 0x4180, 0x4200, 0x6b00, 0x6e00, 0x6e80) if v2 else (0x2000, 0x4180, 0x4200, 0x6b00, 0x6e80)
    acquire(bus, preflight, FOLDER, stamp + '-preflight', tuple((a, 128) for a in addresses))
    save()
    for row in preflight['regions']:
        address = int(row['start'], 16)
        if bytes.fromhex(row['data']) != candidate[address:address + row['bytes']]:
            raise RuntimeError('Installed firmware differs from candidate; no save sent')
    if bus.read(0x71, 0xe0a0, 1) != b'\x00':
        raise RuntimeError('Application command mailbox is not idle')
    module.Dimm(bus, 0x71).apply([(255, 0, 0)] * 8, 1)
    report['red_before_save'] = snapshot(bus, 0x71)
    if report['red_before_save']['mode'] != '00010000' or report['red_before_save']['colors'] != 'ff0000' * 8:
        raise RuntimeError('Red readback mismatch; no save sent')
    report['save_attempts'] = 1
    report['status'] = 'issuing-one-AA-save'
    save()
    bus.select(0x71, 0xe0a0)
    bus.transfer(0x71, 0, 1, 2, 0xaa)
    deadline = time.monotonic() + 3
    report['mailbox_polls'] = []
    while True:
        time.sleep(0.05)
        value = bus.read(0x71, 0xe0a0, 1).hex()
        report['mailbox_polls'].append(value)
        save()
        if value == '00':
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('Save did not finish; no retry, reset or flash read sent')
    result = report.setdefault('saved_block_read', {})
    acquire(bus, result, FOLDER, stamp + '-saved', ((0xe000, 384),))
    data = bytes.fromhex(result['regions'][0]['data'])
    report['verification'] = dict(marker=hex(data[382]), stored_checksum=hex(data[383]),
        calculated_checksum=hex(sum(data[:383]) & 255),
        valid=data[382] == 0x5a and data[383] == (sum(data[:383]) & 255),
        saved_mode=data[:4].hex(), saved_colors_rbg=data[128:152].hex(),
        saved_static_red=data[:4] == bytes.fromhex('00010000') and data[128:152] == bytes.fromhex('ff0000' * 8))
    report['final'] = [snapshot(bus, a) for a in (0x71, 0x73)]
    report['control_unchanged'] = report['initial'][1] == report['final'][1]
    report['status'] = 'save-and-read-complete'
    save()
    if not report['control_unchanged'] or not report['verification']['valid'] or not report['verification']['saved_static_red']:
        raise RuntimeError('Save verification failed; no retry or additional writes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--v2', action='store_true')
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = FOLDER / ('e000-runtime-save-' + stamp + '.json')
    report = dict(utc=stamp, target='0x71', control='0x73', save_attempts=0,
                  reset=False, firmware_writes=False, power_cycle_persistence_tested=False)
    def save():
        path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    bus = None
    try:
        save()
        bus = module.PawnBus()
        with bus.transaction():
            run(bus, report, save, stamp, v2=args.v2)
    except BaseException as exc:
        report['error'] = str(exc)
        save()
        raise
    finally:
        if bus:
            bus.close()
        print(path)
        print(json.dumps({k: v for k, v in report.items() if k not in ('firmware_preflight', 'saved_block_read')}, indent=2))


if __name__ == '__main__':
    main()
