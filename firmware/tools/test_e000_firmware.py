"""Execute candidate ARM code with simulated flash; never opens a hardware driver."""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'pylibs'))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2
from build_e000_firmware import build, SOURCE, ROOT


class Machine:
    def __init__(self, image):
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.cpu.mem_map(0, 0x20000)
        self.cpu.mem_write(0, image + b'\xff' * 65536)
        self.cpu.mem_map(0x20000000, 0x10000)
        self.cpu.mem_map(0x40000000, 0x2000)
        self.commands = []
        self.latch = []
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self.mmio)
        self.cpu.hook_add(UC_HOOK_CODE, self.code)

    def code(self, cpu, address, size, user):
        if address == 0x750:  # Boot header reader, modeled peripheral read.
            destination = cpu.reg_read(UC_ARM_REG_R0)
            source = cpu.reg_read(UC_ARM_REG_R1)
            length = cpu.reg_read(UC_ARM_REG_R2)
            cpu.mem_write(destination, bytes(cpu.mem_read(source, length)))
            cpu.reg_write(UC_ARM_REG_PC, cpu.reg_read(UC_ARM_REG_LR))

    def mmio(self, cpu, access, address, size, value, user):
        if address != 0x40000415:
            return
        selected = int.from_bytes(cpu.mem_read(0x40000411, 3), 'little')
        assert 0xE000 <= selected < 0xE180, hex(selected)
        page = selected & ~127
        self.commands.append((value, selected))
        if value == 0x20:
            cpu.mem_write(page, b'\xff' * 128)
        elif value == 0x80:
            self.latch = []
        elif value in (0x12, 0x02):
            self.latch.append(cpu.mem_read(0x40000414, 1)[0])
            if value == 0x02:
                assert len(self.latch) == 128
                cpu.mem_write(page, bytes(self.latch))
        else:
            assert value == 0x70, hex(value)

    def call(self, address):
        self.cpu.reg_write(UC_ARM_REG_SP, 0x20003F00)
        self.cpu.reg_write(UC_ARM_REG_LR, 0x1701)
        self.cpu.emu_start(address | 1, 0x1700, count=1000000)
        assert self.cpu.reg_read(UC_ARM_REG_PC) == 0x1700, hex(address)
        return self.cpu.reg_read(UC_ARM_REG_R0)

    def request(self, command):
        self.cpu.mem_write(0x200030A0, bytes([command]))
        self.call(0x4138)
        assert self.cpu.mem_read(0x200030A0, 1) == b'\x00'

    def boot_checks(self):
        assert self.call(0x5E4) == 1
        assert self.call(0x69C) == 1


def run():
    original = SOURCE.read_bytes()
    candidate, manifest = build(original)
    Machine(original).boot_checks()
    m = Machine(candidate)
    m.boot_checks()
    assert m.call(0x6E90) == 0  # Zero-filled uninitialized settings are rejected.
    mode = bytes.fromhex('00010000') + bytes(12)
    colors = bytes((i * 17 + 3) & 255 for i in range(96))
    secondary = bytes((i * 7 + 5) & 255 for i in range(96))
    m.cpu.mem_write(0x20003020, mode)
    m.cpu.mem_write(0x20003300, colors)
    m.cpu.mem_write(0x20003500, secondary)
    m.cpu.mem_write(0x20000178, b'\x01')
    m.request(0xAA)  # Actual dispatcher, serializer, writer and wait routine.
    assert [a for command, a in m.commands if command == 0x20] == [0xE000, 0xE080, 0xE100]
    assert len(m.commands) == 3 * 131
    saved = bytes(m.cpu.mem_read(0xE000, 384))
    assert saved[382] == 0x5A and saved[383] == sum(saved[:383]) & 255
    assert m.call(0x6E90) == 1
    m.boot_checks()  # Saving must never invalidate the firmware checksum.
    flash = bytes(m.cpu.mem_read(0, 65536))
    assert flash[:0xE000] == candidate[:0xE000]
    assert flash[0xE180:] == candidate[0xE180:]

    # Fresh SRAM + saved flash: execute the actual configuration startup path.
    cold = Machine(flash)
    cold.cpu.mem_write(0x200030B0, b'\x00\x08')  # Existing one-channel/eight-LED topology.
    cold.call(0x420C)
    assert bytes(cold.cpu.mem_read(0x20003020, 16)) == mode
    assert bytes(cold.cpu.mem_read(0x20003300, 96)) == colors
    assert bytes(cold.cpu.mem_read(0x20003500, 96)) == secondary
    assert not cold.commands

    for offset in (0, 128, 300, 382, 383):
        damaged = Machine(flash)
        damaged.cpu.mem_write(0xE000 + offset, bytes([saved[offset] ^ 1]))
        assert damaged.call(0x6E90) == 0
    for command in (0x02, 0x55):
        erased = Machine(flash)
        erased.cpu.mem_write(0x200030B0, b'\x00\x08')
        erased.request(command)
        assert erased.commands == [(0x20, a) for a in (0xE000, 0xE080, 0xE100)]
        assert erased.call(0x6E90) == 0
        erased.boot_checks()
    broken = bytearray(candidate)
    broken[0x2010] ^= 1
    invalid = Machine(bytes(broken))
    assert invalid.call(0x5E4) == 1 and invalid.call(0x69C) == 0
    broken = bytearray(candidate)
    broken[0x2004] ^= 1
    assert Machine(bytes(broken)).call(0x5E4) == 0
    try:
        build(bytes(broken))
    except ValueError:
        pass
    else:
        raise AssertionError('Builder accepted a modified input')
    report = dict(hardware_access=False, candidate_sha256=manifest['candidate_sha256'],
                  passed=['original and candidate boot checks', 'AA dispatcher and actual app writer',
                          'three relocated pages only', 'settings marker/checksum',
                          'firmware checksum after save', 'fresh SRAM startup restore',
                          'corrupt settings rejection', '02 and 55 erase paths',
                          'bad firmware and header rejection', 'wrong input refusal'],
                  limitation='Flash effects and CPU-visible mapping are simulated. Hardware protection, timing, interrupts, power loss and live persistence remain unverified.')
    (ROOT / 'e000-candidate-tests.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    run()
