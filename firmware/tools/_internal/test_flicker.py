"""Compare original/patched Random Flicker using actual ARM code, offline only."""
import json
import struct
from firmware_image import build, SOURCE, ROOT, OUTPUT
from arm_emulator import Machine
from test_firmware import cold_start
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_SP

RECORD, SOURCE_BUFFER, DESTINATION = 0x20002A90, 0x20003300, 0x20002000


def machine(image, colors, seed):
    m = Machine(image)
    m.cpu.mem_write(RECORD, bytes([len(colors)//3, 13]))
    m.cpu.mem_write(RECORD + 0x14, struct.pack('<II', SOURCE_BUFFER, DESTINATION))
    m.cpu.mem_write(SOURCE_BUFFER, colors)
    m.cpu.mem_write(DESTINATION-4, b'\xa5'*104)
    rng = struct.unpack_from('<I', image, 0x1960)[0]
    m.cpu.mem_write(rng, struct.pack('<I', seed))
    levels = []
    def hook(cpu, address, size, user):
        if address == 0x34A8:
            levels.append(cpu.mem_read(cpu.reg_read(UC_ARM_REG_SP) + 6, 1)[0])
    m.cpu.hook_add(UC_HOOK_CODE, hook)
    return m, levels, rng


def frame(m, dispatch=False):
    m.cpu.reg_write(UC_ARM_REG_R0, 0 if dispatch else RECORD)
    m.call(0x6BDC if dispatch else 0x345C)


def run():
    original = SOURCE.read_bytes()
    parent = original
    candidate, manifest = build(original)
    assert OUTPUT.read_bytes() == candidate
    Machine(candidate).boot_checks()
    patterns = [bytes.fromhex('ff0000'*8), bytes.fromhex('00ff00'*8),
                bytes.fromhex('0000ff'*8), bytes(24), bytes([255])*24,
                bytes((i*37+11)&255 for i in range(24))]
    observed = set()
    frames = 0
    for colors in patterns:
        a, old_levels, rng = machine(parent, colors, 0x12345678)
        b, new_levels, _ = machine(candidate, colors, 0x12345678)
        for _ in range(64):
            old_levels.clear(); new_levels.clear()
            frame(a); frame(b)
            assert old_levels == new_levels and len(new_levels) == 8
            observed.update(new_levels)
            expected = bytes((colors[i]*new_levels[i//3])>>8 for i in range(24))
            assert bytes(b.cpu.mem_read(DESTINATION, 24)) == expected
            assert bytes(b.cpu.mem_read(SOURCE_BUFFER, 24)) == colors
            assert bytes(b.cpu.mem_read(RECORD, 28)) == bytes(a.cpu.mem_read(RECORD, 28))
            assert bytes(b.cpu.mem_read(rng, 4)) == bytes(a.cpu.mem_read(rng, 4))
            assert bytes(b.cpu.mem_read(DESTINATION-4, 4)) == b'\xa5'*4
            assert bytes(b.cpu.mem_read(DESTINATION+24, 4)) == b'\xa5'*4
            assert not a.commands and not b.commands
            frames += 1
    assert observed == {16, 128}
    # Original output ignores the source color entirely for identical RNG state.
    a, _, _ = machine(parent, patterns[0], 123)
    b, _, _ = machine(parent, patterns[2], 123)
    frame(a); frame(b)
    assert a.cpu.mem_read(DESTINATION, 24) == b.cpu.mem_read(DESTINATION, 24)
    # Actual mode13 dispatcher reaches the patched renderer as well.
    m, levels, _ = machine(candidate, patterns[0], 123)
    frame(m, dispatch=True)
    assert len(levels) == 8
    # Settings save and startup still preserve mode13 and per-LED color data.
    block = bytearray((ROOT.parent/'tests/fixtures/saved-static-red.bin').read_bytes())
    block[1] = 13
    block[128:152] = patterns[-1]
    block[383] = sum(block[:383]) & 255
    m = cold_start(candidate, block)
    assert bytes(m.cpu.mem_read(0x200030A1, 3)) == bytes.fromhex('010008')
    assert m.cpu.mem_read(0x20003021, 1) == b'\x0d'
    assert bytes(m.cpu.mem_read(SOURCE_BUFFER, 24)) == patterns[-1]
    m.request(0xAA)
    m.boot_checks()
    saved = bytes(m.cpu.mem_read(0xE000,384))
    assert saved[1] == 13 and saved[128:152] == patterns[-1]
    assert saved[382] == 0x5A and saved[383] == sum(saved[:383]) & 255
    m = cold_start(candidate, saved)
    assert m.cpu.mem_read(0x20003021,1) == b'\x0d'
    assert bytes(m.cpu.mem_read(SOURCE_BUFFER,24)) == patterns[-1]
    result = dict(hardware_access=False, candidate_sha256=manifest['candidate_sha256'],
        frames_compared=frames, brightness_levels=sorted(observed),
        passed=['original ignores stored colors', 'per-LED stored RBG scaling',
                'red/green/blue/black/white/mixed frames', 'identical random choices and counters',
                'source buffer and neighboring bytes unchanged', 'actual mode13 dispatch',
                'LED-count fix retained', 'save/startup mode13 and colors', 'firmware/header checksums'],
        limitation='No hardware flash or visible-output test; changes existing mode13 behavior')
    (ROOT.parent/'reports/patched-v1-flicker-tests.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    run()
