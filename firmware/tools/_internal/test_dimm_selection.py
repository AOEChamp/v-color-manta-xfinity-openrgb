"""Offline discovery/selection and selected-address flashing regression tests."""
from unittest.mock import patch
import discovery
import flash
import test_installer as fixtures
import page_installer as stock
import bootloader as boot


class Physical:
    def __init__(self, target, fault=None):
        self.target = target
        self.inner = fixtures.FakeBus(fault)
        self.writes = []
    def read(self, address, reg, count):
        return self.inner.read(0x71, reg, count)
    def select(self, address, reg):
        assert address == self.target
        self.inner.select(0x71, reg)
    def transfer(self, address, *args):
        assert address == self.target
        self.writes.append(address)
        return self.inner.transfer(0x71, *args)


def run():
    with patch.object(discovery, 'display'):
        rows = [dict(address=0x70, compatible_identity=False), dict(address=0x72, compatible_identity=True)]
        assert discovery.choose(rows, lambda _: '2') == 0x72
        for value in ('', '0', '3', 'bad', '1'):
            try:
                discovery.choose(rows, lambda _: value)
            except (ValueError, RuntimeError):
                pass
            else:
                raise AssertionError('Invalid selection accepted')
    for target in discovery.ADDRESSES:
        for control in (None, next(a for a in discovery.ADDRESSES if a != target)):
            for fault in (None, 'preflight', 'readback', 'error', 'uncertain'):
                physical = Physical(target, fault)
                bus = flash.TargetBus(physical, target, control)
                report = {}
                for method, args in ((bus.select, (0x73, 0x202)), (bus.transfer, (0x73, 0, 1, 2, 0))):
                    try:
                        method(*args)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('Control mutation permitted')
                try:
                    with patch.object(boot.time, 'sleep', lambda _: None):
                        boot.run(bus, report, lambda: None, cpu_only=True,
                                 verified_action=stock.install, control=control is not None)
                except (RuntimeError, OSError):
                    assert fault is not None
                else:
                    assert fault is None
                    assert report['application_resumed']
                    assert report['control_present'] == (control is not None)
                if fault in ('readback', 'error', 'uncertain'):
                    assert report['exit_deferred_incomplete_firmware']
                assert all(a == target for a in physical.writes)
                assert bus.report({'target':'0x71'})['target'] == hex(target)
    class DiscoveryBus:
        def read(self, address, reg, count):
            if address == 0x70:
                raise OSError('absent')
            if reg == 0xB500:
                return discovery.module.SIGNATURE if address == 0x72 else bytes(5)
            return bytes.fromhex('7730')
    rows = discovery.discover(DiscoveryBus())
    assert [r['address'] for r in rows] == [0x71, 0x72, 0x73]
    assert [r['address'] for r in rows if r['compatible_identity']] == [0x72]
    print('Discovery/selection and 40 target/control/fault cases passed; no hardware access.')
