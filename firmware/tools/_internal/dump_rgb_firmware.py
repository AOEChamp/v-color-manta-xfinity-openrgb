"""Acquire two matching 64-KB images using the validated 0x13 read path on 0x71.

No erase, program, save, reset or halt operations. Requires explicit --execute.
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import struct
import time
import transport as module
from identity import snapshot

TARGET = 0x71
EXPECTED_VECTOR = bytes.fromhex('001a0020d5000000dd000000df000000')


def acquire(bus, report, save, folder, stamp):
    report['before'] = [snapshot(bus, addr) for addr in (0x71, 0x73)]
    old = bytes(bus.read(TARGET, reg, 1)[0] for reg in (0x410, 0x411, 0x412, 0x413))
    report['registers_before'] = old.hex()
    if old[0] & 0x81 or old[3] != 0:
        raise RuntimeError('Unexpected flash control/high-address state; no writes sent')

    def write(reg, value):
        if reg not in (0x410, 0x411, 0x412, 0x413, 0x415) or not 0 <= value <= 255:
            raise RuntimeError('Register/value outside strict allowlist')
        if reg == 0x415 and value != 0x13:
            raise RuntimeError('Only program READ command 13 allowed')
        bus.select(TARGET, reg)
        bus.transfer(TARGET, 0, 1, 2, value)
        report['control_writes'] += 1

    def read_range(start, length):
        write(0x411, start & 255)
        write(0x412, start >> 8)
        data = bytearray()
        for _ in range(length):
            write(0x415, 0x13)
            report['read_commands'] += 1
            deadline = time.monotonic() + 0.1
            while bus.read(TARGET, 0x410, 1)[0] & 0x80:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Read busy timeout; no command retry')
                time.sleep(0.001)
            data.extend(bus.read(TARGET, 0x414, 1))
        return bytes(data)

    try:
        report['status'] = 'enabling-read-access'
        save()
        write(0x410, old[0] | 1)
        if bus.read(TARGET, 0x410, 1)[0] != (old[0] | 1):
            raise RuntimeError('Enable readback mismatch')
        prefix = read_range(0, 16)
        report['sequential_prefix'] = prefix.hex()
        save()
        if prefix != EXPECTED_VECTOR:
            raise RuntimeError('Sequential read does not match prior individually-addressed vector; aborted')
        paths = []
        hashes = []
        for pass_number in (1, 2):
            # A sequential final-byte read may carry the address past 0xFFFF.
            # Keep each acquisition inside the verified 64-KB range.
            write(0x413, 0)
            path = folder / f'vcolor-7730-0x71-{stamp}-pass{pass_number}.bin'
            paths.append(path)
            report['status'] = f'acquiring-pass-{pass_number}'
            report['pass_number'] = pass_number
            report['bytes_in_pass'] = 0
            save()
            with path.open('xb') as output:
                for start in range(0, 65536, 128):
                    block = read_range(start, 128)
                    output.write(block)
                    report['bytes_in_pass'] = start + len(block)
                    if report['bytes_in_pass'] % 4096 == 0:
                        output.flush()
                        save()
                        print(f'Pass {pass_number}: {report["bytes_in_pass"]}/65536 bytes', flush=True)
            data = path.read_bytes()
            if len(data) != 65536 or data[:16] != EXPECTED_VECTOR:
                raise RuntimeError('Image size/vector validation failed')
            digest = hashlib.sha256(data).hexdigest()
            hashes.append(digest)
            report.setdefault('images', []).append(dict(path=str(path), bytes=len(data), sha256=digest))
            save()
        report['matching_images'] = paths[0].read_bytes() == paths[1].read_bytes()
        if not report['matching_images']:
            raise RuntimeError('Two images differ; not a verified firmware dump')
        report['status'] = 'two-identical-64kb-images-acquired'
        save()
    finally:
        report['restore_errors'] = []
        for reg, value in ((0x411, old[1]), (0x412, old[2]), (0x413, old[3]), (0x410, old[0])):
            try:
                write(reg, value)
            except Exception as exc:
                report['restore_errors'].append(f'{reg:#x}: {exc}')
        report['registers_after'] = bytes(bus.read(TARGET, reg, 1)[0] for reg in (0x410, 0x411, 0x412, 0x413)).hex()
        report['after'] = [snapshot(bus, addr) for addr in (0x71, 0x73)]
        report['lighting_unchanged'] = report['before'] == report['after']
        report['registers_restored'] = report['registers_before'] == report['registers_after']
        save()
        if report['restore_errors'] or not report['registers_restored']:
            raise RuntimeError('Register restoration check failed; inspect acquisition log')


