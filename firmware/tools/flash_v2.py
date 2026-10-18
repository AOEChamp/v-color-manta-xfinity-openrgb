"""Discover RGB DIMMs and install exact final firmware on the user's selection."""
import argparse
import datetime
import json
import second_dimm_e000_v2 as stock
import probe_bootloader_mailbox as boot
from build_e000_v2_firmware import ROOT
from snapshot_retry import module
from list_dimms import discover, choose, ADDRESSES
from probe_firmware_read import snapshot


class TargetBus:
    """Map existing installer target; reject mutations of every other address."""
    def __init__(self, physical, target, control=None):
        if target not in ADDRESSES or (control is not None and (control not in ADDRESSES or control == target)):
            raise ValueError('Invalid target/control mapping')
        self.physical, self.target, self.control = physical, target, control

    def address(self, logical):
        if logical == 0x71:
            return self.target
        if logical == 0x73 and self.control is not None:
            return self.control
        raise ValueError('Unmapped logical address')

    def read(self, address, register, count):
        return self.physical.read(self.address(address), register, count)

    def select(self, address, register):
        if address != 0x71:
            raise ValueError('Only the selected target may be written')
        return self.physical.select(self.target, register)

    def transfer(self, address, *args):
        if address != 0x71:
            raise ValueError('Only the selected target may be written')
        return self.physical.transfer(self.target, *args)

    def report(self, value):
        if isinstance(value, dict):
            return {k: (hex(self.address(int(v, 16))) if k in ('address', 'target', 'control') and v in ('0x71', '0x73')
                        else self.report(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [self.report(v) for v in value]
        return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.parse_args()
    physical = module.PawnBus()
    report = {}
    path = ROOT / ('v2-install-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    bus = None
    def save():
        path.write_text(json.dumps(bus.report(report) if bus else report, indent=2), encoding='utf-8')
    try:
        with physical.transaction():
            rows = discover(physical)
        target = choose(rows)  # Prompt without holding the shared SMBus mutex.
        others = [r['address'] for r in rows if r['compatible_identity'] and r['address'] != target]
        bus = TargetBus(physical, target, others[0] if others else None)
        report.update(target='0x71', source='stock', discovered=rows, status='starting')
        if others:
            report['control'] = '0x73'
        save()
        with physical.transaction():
            # Rediscover after the prompt, before any bootloader/reset operation.
            if discover(physical) != rows:
                raise RuntimeError('Controller identities changed after selection; no flash attempted')
            before = [snapshot(physical, a) for a in others]
            boot.run(bus, report, save, cpu_only=True, verified_action=stock.install, control=bool(others))
            report['all_other_modules_unchanged'] = before == [snapshot(physical, a) for a in others]
            save()
            if not report['all_other_modules_unchanged']:
                raise RuntimeError('Another module changed; inspect report')
    except BaseException as exc:
        report['error'] = str(exc)
        save()
        raise
    finally:
        physical.close()
        print(path)


if __name__ == '__main__':
    main()
