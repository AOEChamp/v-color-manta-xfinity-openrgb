"""Execute v2 startup/save code offline, including the actual saved red block."""
import hashlib
import json
from patch_storage import build as build_v1, SOURCE, ROOT
from firmware_image import build, OUTPUT
from arm_emulator import Machine


def cold_start(image, block, topology=16):
    flash = bytearray(image)
    flash[0xE000:0xE180] = block
    m = Machine(bytes(flash))
    m.boot_checks()
    m.cpu.mem_write(0x200030B0, topology.to_bytes(2, 'big'))
    m.call(0x420C)
    assert not m.commands
    return m


def run():
    original = SOURCE.read_bytes()
    candidate, manifest = build(original)
    assert OUTPUT.read_bytes() == candidate
    parent, _ = build_v1(original)
    report = json.loads((ROOT / 'e000-runtime-save-20261018T064216372384Z.json').read_text())
    captured = bytes.fromhex(report['saved_block_read']['regions'][0]['data'])
    assert len(captured) == 384 and captured[382] == 0x5A
    assert captured[383] == sum(captured[:383]) & 255
    old = cold_start(parent, captured)
    assert bytes(old.cpu.mem_read(0x200030A1, 3)) == bytes.fromhex('010800')
    new = cold_start(candidate, captured)
    assert bytes(new.cpu.mem_read(0x200030A1, 3)) == bytes.fromhex('010008')
    assert new.cpu.mem_read(0x20002A90, 1) == b'\x08'
    assert new.cpu.mem_read(0x20000178, 1) == b'\x01'
    assert bytes(new.cpu.mem_read(0x20003020, 16)) == captured[:16]
    assert bytes(new.cpu.mem_read(0x20003300, 96)) == captured[128:224]
    assert bytes(new.cpu.mem_read(0x20003500, 96)) == captured[224:320]
    new.request(0xAA)
    saved = bytes(new.cpu.mem_read(0xE000, 384))
    assert saved[382] == 0x5A and saved[383] == sum(saved[:383]) & 255
    assert saved[:16] == captured[:16] and saved[128:320] == captured[128:320]
    assert saved[368:370] == b'\x01\x08'
    assert [a for cmd, a in new.commands if cmd == 0x20] == [0xE000, 0xE080, 0xE100]
    new.boot_checks()
    repeat = cold_start(candidate, saved)
    assert bytes(repeat.cpu.mem_read(0x200030A1, 3)) == bytes.fromhex('010008')
    assert repeat.cpu.mem_read(0x20002A90, 1) == b'\x08'
    for n in (1, 8, 16):
        block = bytearray(captured)
        block[369] = n
        block[383] = sum(block[:383]) & 255
        m = cold_start(candidate, block, topology=n*2)
        assert bytes(m.cpu.mem_read(0x200030A1, 3)) == bytes([1, 0, n])
        assert m.cpu.mem_read(0x20002A90, 1) == bytes([n])
    for command in (0x02, 0x55):
        m = cold_start(candidate, captured)
        m.request(command)
        assert m.commands == [(0x20, a) for a in (0xE000, 0xE080, 0xE100)]
        assert m.call(0x6E90) == 0
        m.boot_checks()
    corrupt = bytearray(captured)
    corrupt[383] ^= 1
    rejected = cold_start(candidate, corrupt)
    assert rejected.call(0x6E90) == 0
    assert bytes(rejected.cpu.mem_read(0x200030A1, 3)) == bytes.fromhex('010008')
    assert bytes(rejected.cpu.mem_read(0x20003020, 4)) == bytes.fromhex('00050000')
    for offset, header_ok in ((0x6E58, True), (0x2004, False)):
        bad = bytearray(candidate)
        bad[offset] ^= 1
        m = Machine(bytes(bad))
        assert m.call(0x5E4) == int(header_ok)
        if header_ok:
            assert m.call(0x69C) == 0
    try:
        build(parent)
    except ValueError:
        pass
    else:
        raise AssertionError('Builder accepted a non-original image')
    result = dict(hardware_access=False, candidate_sha256=hashlib.sha256(candidate).hexdigest(),
        passed=['v1 count-layout bug reproduced with captured hardware save',
                'v2 restores actual saved red and count 0008', 'engine channel count 1 and LED count 8',
                'AA save and fresh startup roundtrip', 'counts 1,8,16',
                '02/55 erase paths', 'invalid settings fallback',
                'actual ARM firmware/header checksum validators and corruption rejection',
                'wrong build input rejected'],
        limitation='CPU and flash effects simulated; visible output and power-loss behavior untested')
    (ROOT / 'e000-v2-tests.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


