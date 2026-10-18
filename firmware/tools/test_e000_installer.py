"""Exercise installer and reset guards with a fake bus; no physical hardware."""
import json
from unittest.mock import patch
import install_e000_firmware as installer


class FakeBus:
    def __init__(self, fault=None):
        self.flash = bytearray(installer.SOURCE.read_bytes())
        self.regs = bytearray(65536)
        self.regs[0x454] = 0x2A
        self.regs[0xB500:0xB505] = bytes.fromhex('a83216e88c')
        self.regs[0x4000:0x4002] = bytes.fromhex('7730')
        self.fault = fault
        self.writes = []
        self.programmed = []
        if fault == 'preflight':
            self.flash[0x4180] ^= 1

    def read(self, target, register, count):
        assert target in (0x71, 0x73)
        return bytes(self.regs[register:register+count])

    def select(self, target, register):
        assert target == 0x71
        self.pointer = register

    def transfer(self, target, read, command, size, value):
        assert (target, read, command, size) == (0x71, 0, 1, 2)
        reg = self.pointer
        self.writes.append((reg, value))
        self.regs[reg] = value
        if reg == 0x202 and value == 0 and self.regs[0x606] == 0xE1:
            self.regs[0x606] = 0xE7
            self.regs[0xF0F8:0xF0FA] = b'\x00\x02'
        if reg != 0xF0F9 or value:
            return
        op = self.regs[0xF0F8]
        address = int.from_bytes(self.regs[0xF0F1:0xF0F4], 'big')
        length = int.from_bytes(self.regs[0xF0F6:0xF0F8], 'big')
        if op == 0x30:
            self.regs[0xF000:0xF000+length] = self.flash[address:address+length]
        elif op == 0x20:
            self.programmed.append(address)
            if self.fault == 'uncertain' and len(self.programmed) == 2:
                raise OSError('Simulated transport failure after trigger')
            if self.fault == 'error' and len(self.programmed) == 2:
                self.regs[0xF0F8:0xF0FA] = b'\x00\x10'
                return
            self.flash[address:address+length] = self.regs[0xF000:0xF000+length]
            if self.fault == 'readback' and len(self.programmed) == 2:
                self.flash[address] ^= 1
        else:
            raise AssertionError(hex(op))
        self.regs[0xF0F8:0xF0FA] = b'\x00\x02'


def run():
    cases = []
    for fault in (None, 'preflight', 'readback', 'error', 'uncertain'):
        bus, report = FakeBus(fault), {}
        try:
            with patch.object(installer.boot.time, 'sleep', lambda _: None):
                installer.boot.run(bus, report, lambda: None, cpu_only=True,
                                   verified_action=installer.install)
        except (RuntimeError, OSError) as exc:
            assert fault is not None, str(exc)
        else:
            assert fault is None
        if fault is None:
            assert bytes(bus.flash) == installer.OUTPUT.read_bytes()
            assert bus.programmed == list(installer.ORDER)
            assert report['application_resumed'] and report['control_unchanged']
            assert report['protection_restored']
            assert len(report['entry_writes']) == len(report['exit_writes']) == 3
        elif fault == 'preflight':
            assert not bus.programmed and report['application_resumed']
        else:
            assert len(bus.programmed) == 2
            assert report['firmware_update_incomplete']
            assert report['exit_deferred_incomplete_firmware']
            assert not report.get('exit_writes')
            if fault == 'uncertain':
                assert report['flash_request_unresolved']
                assert report['protection_restore_deferred_pending_flash']
        cases.append(dict(fault=fault, passed=True, writes=[hex(a) for a in bus.programmed],
                          application_resumed=report.get('application_resumed', False)))
    result = dict(hardware_access=False, cases=cases)
    (installer.ROOT / 'e000-installer-tests.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    run()
