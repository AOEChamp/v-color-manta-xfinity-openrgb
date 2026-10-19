"""Execute ARM code with simulated flash; never opens a hardware driver."""
import struct
import sys
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2


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
