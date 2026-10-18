"""Install or test exact E000 v2 on physical DIMM 0x73; physical 0x71 read-only.

Reuse validated 0x71-only routines through an explicit swapped-address adapter.
No mutation is permitted to their logical control (physical 0x71).
"""
import argparse
import datetime
import json
from unittest.mock import patch
from build_e000_v2_firmware import build, SOURCE, OUTPUT, ROOT
import install_e000_firmware as installer
import probe_bootloader_mailbox as boot
import save_red_e000 as saver
from snapshot_retry import module

ORDER = (0x4180, 0x4200, 0x6B00, 0x6E00, 0x6E80, 0x2000)
READS = sorted({p + d for p in ORDER for d in (-128, 0, 128)} |
               {0, 0xE000, 0xE080, 0xE100})


class SecondDimmBus:
    def __init__(self, physical):
        self.physical = physical

    @staticmethod
    def address(logical):
        if logical not in (0x71, 0x73):
            raise ValueError('Only the two RGB addresses are allowed')
        return 0x73 if logical == 0x71 else 0x71

    def transaction(self):
        return self.physical.transaction()

    def read(self, address, register, count):
        return self.physical.read(self.address(address), register, count)

    def select(self, address, register):
        if address != 0x71:
            raise ValueError('Physical 0x71 is read-only')
        return self.physical.select(0x73, register)

    def transfer(self, address, *args):
        if address != 0x71:
            raise ValueError('Physical 0x71 is read-only')
        return self.physical.transfer(0x73, *args)

    def block(self, address, register, data):
        if address != 0x71:
            raise ValueError('Physical 0x71 is read-only')
        return self.physical.block(0x73, register, data)


def physical_report(value):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            if key in ('address', 'target', 'control') and isinstance(child, str) and child in ('0x71', '0x73'):
                result[key] = '0x73' if child == '0x71' else '0x71'
            else:
                result[key] = physical_report(child)
        return result
    if isinstance(value, list):
        return [physical_report(child) for child in value]
    return value


def install(bus, report, save):
    # Original-image preflight is required on this previously unpatched stick.
    # All six v2 pages are verified before exit, checksum/header page written last.
    with patch.multiple(installer, build=build, OUTPUT=OUTPUT, ORDER=ORDER, READS=READS):
        installer.install(bus, report, save)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--stage', choices=('install', 'save-restart'), required=True)
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = ROOT / ('second-dimm-v2-' + args.stage + '-' + stamp + '.json')
    report = dict(utc=stamp, target='0x71', control='0x73', stage=args.stage,
                  address_adapter='Logical 71 -> physical73; logical73 -> physical71; report addresses translated',
                  status='starting')

    def save():
        path.write_text(json.dumps(physical_report(report), indent=2), encoding='utf-8')

    physical = None
    try:
        save()
        physical = module.PawnBus()
        bus = SecondDimmBus(physical)
        with bus.transaction():
            if args.stage == 'install':
                boot.run(bus, report, save, cpu_only=True, verified_action=install)
            else:
                saved = report.setdefault('runtime_save', {})
                saver.run(bus, saved, save, stamp + '-physical73', v2=True)
                restarted = report.setdefault('controller_restart', {})
                boot.run(bus, restarted, save, cpu_only=True)
                report['capabilities'] = {}
                for address in (0x71, 0x73):
                    data = bus.read(address, 0xE0A1, 10)
                    report['capabilities'][hex(bus.address(address))] = data.hex()
                if report['capabilities']['0x73'] != '01000800000000000000':
                    raise RuntimeError('Unexpected restored LED count')
                if restarted['after'][0]['mode'] != '00010000' or restarted['after'][0]['colors'] != 'ff0000' * 8:
                    raise RuntimeError('Red register restore failed')
                report['status'] = 'saved-red-and-CPU-restart-verified'
                save()
    except BaseException as exc:
        report['error'] = str(exc)
        save()
        raise
    finally:
        if physical:
            physical.close()
        print(path)
        compact = {k: v for k, v in physical_report(report).items()
                   if k not in ('requests', 'original_pages', 'manifest', 'runtime_save', 'controller_restart')}
        if 'runtime_save' in report:
            compact['saved_verification'] = report['runtime_save'].get('verification')
        if 'controller_restart' in report:
            compact['after_restart'] = physical_report(report['controller_restart'].get('after'))
            compact['control_unchanged'] = report['controller_restart'].get('control_unchanged')
        print(json.dumps(compact, indent=2))


if __name__ == '__main__':
    main()
