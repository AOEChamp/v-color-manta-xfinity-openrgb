"""Bounded flash-read investigation on DIMM 0x71; default is register reads only.

--probe allows only calibration read 0x90 and program-read candidate 0x13.
No reset/halt, erase, program, save, remapping or SPD operations are implemented.
"""
import argparse
import datetime
import json
import pathlib
import struct
import time
from snapshot_retry import module

TARGET = 0x71


def snapshot(bus, address):
    signature = bus.read(address, 0xB500, 5)
    chip = bus.read(address, 0x4000, 2)
    if signature != module.SIGNATURE or chip != bytes.fromhex('7730'):
        raise RuntimeError(f'Unexpected identity at {address:#x}')
    return dict(address=hex(address), signature=signature.hex(), chip=chip.hex(),
                mode=bus.read(address, 0xE020, 4).hex(),
                colors=bus.read(address, 0xE300, 24).hex())


def probe(bus, report, save):
    report['before'] = [snapshot(bus, address) for address in (0x71, 0x73)]
    before = bytes(bus.read(TARGET, reg, 1)[0] for reg in (0x410, 0x411, 0x412, 0x413))
    again = bytes(bus.read(TARGET, reg, 1)[0] for reg in (0x410, 0x411, 0x412, 0x413))
    report['flash_config_address_before'] = before.hex()
    if before != again:
        raise RuntimeError('Flash register preflight unstable; no control writes allowed')
    report['status'] = 'read-only-preflight-complete'
    save()
    return before


def read_attempt(bus, original, report, save):
    if original[0] & 0x81:
        raise RuntimeError('Flash is already busy/enabled; no control writes sent')
    report['transactions'] = []

    def write(reg, value):
        if reg not in (0x410, 0x411, 0x412, 0x413, 0x415):
            raise RuntimeError('Register outside strict allowlist')
        if reg == 0x415 and value not in (0x90, 0x13):
            raise RuntimeError('Only read commands are allowed')
        report['transactions'].append(dict(register=hex(reg), value=hex(value), attempted=True))
        save()
        bus.select(TARGET, reg)
        bus.transfer(TARGET, 0, 1, 2, value)

    def read_byte():
        deadline = time.monotonic() + 0.1
        while bus.read(TARGET, 0x410, 1)[0] & 0x80:
            if time.monotonic() >= deadline:
                raise TimeoutError('Flash read busy timeout; no command retry')
            time.sleep(0.001)
        return bus.read(TARGET, 0x414, 1)[0]

    def set_address(address):
        write(0x411, address & 255)
        write(0x412, address >> 8)
        # 0x7730 has 64 KB: Philips' helper does not write the high address byte.

    try:
        write(0x410, original[0] | 1)
        enabled = bus.read(TARGET, 0x410, 1)[0]
        report['enabled_readback'] = hex(enabled)
        if enabled != (original[0] | 1):
            raise RuntimeError('Flash enable did not read back; no read command sent')
        set_address(0x80)
        write(0x415, 0x90)
        report['calibration_marker'] = hex(read_byte())
        save()
        if report['calibration_marker'] != '0x5a':
            raise RuntimeError('Calibration marker differs from Philips format; no program-read candidate sent')
        # Bound the program-read candidate to 16 bytes. Re-select each address;
        # do not assume auto-increment behavior or attempt a full dump yet.
        data = bytearray()
        for address in range(16):
            set_address(address)
            write(0x415, 0x13)
            data.append(read_byte())
        report['candidate_vector_bytes'] = data.hex()
        sp, reset = struct.unpack_from('<II', data)
        report['candidate_initial_sp'] = hex(sp)
        report['candidate_reset_vector'] = hex(reset)
        report['plausible_cortex_m_vector'] = (0x20000000 < sp <= 0x20004000 and sp % 4 == 0
                                                  and reset & 1 == 1 and reset < 0x10000)
        report['status'] = 'bounded-read-complete-firmware-not-yet-dumped'
        save()
    finally:
        # Restore address bytes and the original control value, never a command.
        report['restore_errors'] = []
        for reg, value in ((0x411, original[1]), (0x412, original[2]), (0x410, original[0])):
            try:
                write(reg, value)
            except Exception as exc:
                report['restore_errors'].append(f'{reg:#x}: {exc}')
        report['flash_config_address_after'] = bytes(bus.read(TARGET, reg, 1)[0] for reg in (0x410, 0x411, 0x412, 0x413)).hex()
        report['after'] = [snapshot(bus, address) for address in (0x71, 0x73)]
        report['lighting_unchanged'] = report['before'] == report['after']
        save()
        if report['restore_errors']:
            raise RuntimeError('Register restoration reported an error; inspect log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc)
    output = pathlib.Path(__file__).resolve().parents[1] / 'evidence' / ('firmware-read-probe-' + stamp.strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    report = dict(utc=stamp.isoformat(), target='0x71', control='0x73', control_write_probe=args.probe,
                  erase_program_save_reset_commands=False, status='starting')

    def save():
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')

    bus = None
    try:
        save()
        bus = module.PawnBus()
        with bus.transaction():
            original = probe(bus, report, save)
            if args.probe:
                read_attempt(bus, original, report, save)
    except BaseException as exc:
        report['error'] = str(exc)
        save()
        raise
    finally:
        if bus is not None:
            bus.close()
        print(output)
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
