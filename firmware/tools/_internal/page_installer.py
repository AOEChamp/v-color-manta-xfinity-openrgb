"""Install the exact E000 candidate on 0x71 in one bootloader session only."""
import time
from patch_storage import build, SOURCE, OUTPUT, ROOT
import bootloader as boot

ORDER = (0x4180, 0x4200, 0x6B00, 0x6E80, 0x2000)
WP = (0x444, 0x44C, 0x454)
READS = sorted({p + delta for p in ORDER for delta in (-128, 0, 128)} |
               {0, 0xE000, 0xE080, 0xE100})


def install(bus, report, save):
    original = SOURCE.read_bytes()
    candidate, manifest = build(original)
    if OUTPUT.read_bytes() != candidate:
        raise RuntimeError('Candidate file differs from reproducible build')
    report['manifest'] = manifest
    report['write_order'] = [hex(p) for p in ORDER]
    report['requests'] = []
    old_wp = [bus.read(0x71, reg, 1)[0] for reg in WP]
    report['protection_before'] = old_wp
    if old_wp != [0, 0, 0x2A]:
        raise RuntimeError('Unexpected protection values')
    written = []

    def raw(reg, value):
        if reg not in WP and not 0xF000 <= reg <= 0xF07F and not 0xF0F1 <= reg <= 0xF0F9:
            raise ValueError('Register outside installer allowlist')
        bus.select(0x71, reg)
        bus.transfer(0x71, 0, 1, 2, value)

    def request(command, address, payload=None):
        if command == 0x30:
            if address not in READS or payload is not None:
                raise ValueError('Read outside bounded verification set')
        elif command == 0x20:
            if len(written) >= len(ORDER) or address != ORDER[len(written)] or payload != candidate[address:address+128]:
                raise ValueError('Write outside exact candidate/order')
        else:
            raise ValueError('Unsupported mailbox command')
        if bus.read(0x71, 0xF0F8, 2) != b'\x00\x02':
            raise RuntimeError('Mailbox not idle; no request submitted')
        row = dict(command=hex(command), address=hex(address), length=128)
        report['requests'].append(row)
        save()
        if payload is not None:
            for i, value in enumerate(payload):
                raw(0xF000 + i, value)
            # Verify all 128 staged bytes before triggering the destructive command.
            if bus.read(0x71, 0xF000, 128) != payload or bus.read(0x71, 0xF000, 128) != payload:
                raise RuntimeError('Staged payload mismatch; no flash request sent')
        header = address.to_bytes(3, 'big') + bytes(2) + (128).to_bytes(2, 'big') + bytes([command, 0])
        for i, value in enumerate(header):
            if i == 8:
                if command == 0x20:
                    report['firmware_update_incomplete'] = True
                    written.append(address)
                # Also defer exit for an unresolved read during the update.
                report['flash_request_unresolved'] = True
                row['trigger_attempted'] = True
                save()
            raw(0xF0F1 + i, value)
        deadline = time.monotonic() + 5
        while True:
            status = bus.read(0x71, 0xF0F8, 2)
            if status == b'\x00\x02':
                row['completed'] = True
                report['flash_request_unresolved'] = False
                save()
                break
            if status[0] == 0 and status[1] & 0xF0:
                report['flash_request_unresolved'] = False
                raise RuntimeError(f'Bootloader error {status.hex()}')
            if time.monotonic() >= deadline:
                raise TimeoutError('Mailbox completion unresolved; no retry or CPU exit')
            time.sleep(0.01)
        if command == 0x30:
            first = bus.read(0x71, 0xF000, 128)
            second = bus.read(0x71, 0xF000, 128)
            row['data'] = first.hex()
            row['matching_reads'] = first == second
            save()
            if first != second:
                raise RuntimeError('Unstable firmware readback')
            return first

    before = {}
    for address in READS:
        before[address] = request(0x30, address)
        if before[address] != original[address:address+128]:
            raise RuntimeError(f'Original page mismatch at {address:#x}; no flash writes sent')
    report['original_pages'] = {hex(a): b.hex() for a, b in before.items()}
    save()
    try:
        for reg in WP:
            raw(reg, 0)
        if [bus.read(0x71, reg, 1)[0] for reg in WP] != [0, 0, 0]:
            raise RuntimeError('Protection clear verification failed')
        report['verified_written_pages'] = []
        for address in ORDER:
            request(0x20, address, candidate[address:address+128])
            if request(0x30, address) != candidate[address:address+128]:
                raise RuntimeError(f'Written page mismatch at {address:#x}; staying in bootloader')
            report['verified_written_pages'].append(hex(address))
            save()
        # Independent second pass includes neighboring pages, vector and settings.
        for address in READS:
            if request(0x30, address) != candidate[address:address+128]:
                raise RuntimeError(f'Final verification mismatch at {address:#x}')
        report['all_bounded_readbacks_match_candidate'] = True
        report['verified_read_bytes_per_pass'] = len(READS) * 128
        report['status'] = 'candidate-installed-and-verified-before-exit'
        # Keep the incomplete guard until write protections are restored, too.
        save()
    finally:
        if report.get('flash_request_unresolved'):
            report['protection_restore_deferred_pending_flash'] = True
            save()
        else:
            for reg, value in zip(WP, old_wp):
                raw(reg, value)
            report['protection_restored'] = [bus.read(0x71, reg, 1)[0] for reg in WP] == old_wp
            save()
            if not report['protection_restored']:
                raise RuntimeError('Protection restoration failed; CPU exit blocked after writes')
    if report.get('all_bounded_readbacks_match_candidate') and report.get('protection_restored'):
        report['firmware_update_incomplete'] = False
        save()
