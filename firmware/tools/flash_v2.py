"""Install exact v2 from the supported stock image; explicit physical target required."""
import argparse
import datetime
import json
from unittest.mock import patch
import second_dimm_e000_v2 as stock
import probe_bootloader_mailbox as boot
from build_e000_v2_firmware import ROOT
from snapshot_retry import module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=('0x71', '0x73'), required=True)
    parser.add_argument('--execute', action='store_true', required=True)
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = ROOT / ('v2-install-' + stamp + '.json')
    swapped = args.target == '0x73'
    report = dict(target='0x71', control='0x73', source='stock',
                  status='starting', physical_target=args.target)

    def save():
        data = stock.physical_report(report) if swapped else report
        path.write_text(json.dumps(data, indent=2), encoding='utf-8')

    physical = None
    try:
        save()
        physical = module.PawnBus()
        bus = stock.SecondDimmBus(physical) if swapped else physical
        action = stock.install
        with bus.transaction():
            boot.run(bus, report, save, cpu_only=True, verified_action=action)
    except BaseException as exc:
        report['error'] = str(exc)
        save()
        raise
    finally:
        if physical:
            physical.close()
        print(path)


if __name__ == '__main__':
    main()
