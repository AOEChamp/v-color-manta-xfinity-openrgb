"""CPU stop/run bootloader session with guarded application exit."""
import time
from identity import snapshot

REQUEST = bytes((0, 0, 0, 0, 0, 0, 16, 0x30, 0))
EXPECTED = bytes.fromhex('001a0020d5000000dd000000df000000')


def run(bus, report, save, cpu_only=True, verified_action=None, control=True):
    if not cpu_only:
        raise ValueError('Only CPU stop/run bootloader entry is supported')
    addresses = (0x71, 0x73) if control else (0x71,)
    report['before'] = [snapshot(bus, a) for a in addresses]
    report['before_watchdog'] = bus.read(0x71, 0x600, 7).hex()
    if bus.read(0x71, 0x606, 1) != b'\x00' or bus.read(0x71, 0x202, 1)[0] & 1:
        raise RuntimeError('Expected application mode and running controller; no writes sent')
    original_stop = bus.read(0x71, 0x202, 1)[0]
    original_flags = bus.read(0x71, 0x606, 1)[0]
    entry = ((0x202, original_stop | 1), (0x606, original_flags | 0xe1), (0x202, original_stop))
    exit_sequence = ((0x202, original_stop | 1), (0x606, original_flags), (0x202, original_stop))
    report['reset_method'] = 'CPU-only 0202'

    def write(reg, value, phase):
        if phase in ('entry', 'exit'):
            sequence = entry if phase == 'entry' else exit_sequence
            attempts = report.setdefault(phase + '_writes', [])
            if len(attempts) >= len(sequence) or (reg, value) != sequence[len(attempts)]:
                raise ValueError('Outside exact vendor entry/exit sequence')
        elif phase == 'mailbox-read':
            attempts = report.setdefault('mailbox_writes', [])
            index = len(attempts)
            if index >= len(REQUEST) or (reg, value) != (0xf0f1 + index, REQUEST[index]):
                raise ValueError('Only one fixed read request allowed')
        else:
            raise ValueError('Unknown phase')
        attempts.append(dict(register=hex(reg), value=hex(value)))
        save()  # Mark attempted I/O before sending; no write retries.
        bus.select(0x71, reg)
        bus.transfer(0x71, 0, 1, 2, value)

    try:
        report['entry_attempts'] = 1
        save()
        for index, (reg, value) in enumerate(entry):
            write(reg, value, 'entry')
            if cpu_only and index == 0:
                report['held_stop_readback'] = bus.read(0x71, 0x202, 1).hex()
                report['held_stop_chip'] = bus.read(0x71, 0x4000, 2).hex()
                if int(report['held_stop_readback'], 16) != original_stop | 1 or report['held_stop_chip'] != '7730':
                    raise RuntimeError('Stop verification failed; no boot flags written')
            if cpu_only and index == 1:
                report['held_boot_flags'] = bus.read(0x71, 0x606, 1).hex()
                if int(report['held_boot_flags'], 16) != original_flags | 0xe1:
                    raise RuntimeError('Boot flag readback mismatch')
        report['status'] = 'waiting-for-bootloader'
        save()
        deadline = time.monotonic() + 5
        report['bootloader_polls'] = []
        while True:
            flags = bus.read(0x71, 0x606, 1)[0]
            mailbox = bus.read(0x71, 0xf0f8, 2)
            row = dict(flags=hex(flags), mailbox=mailbox.hex())
            if not report['bootloader_polls'] or row != report['bootloader_polls'][-1]:
                report['bootloader_polls'].append(row)
                save()
            if flags & 3 == 3 and mailbox == b'\x00\x02':
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('No bootloader-ready flags and mailbox; no read request sent')
            time.sleep(0.05)
        report['status'] = 'bootloader-ready-sending-one-read'
        save()
        for index, value in enumerate(REQUEST):
            write(0xf0f1 + index, value, 'mailbox-read')
        deadline = time.monotonic() + 3
        report['request_polls'] = []
        while True:
            state = bus.read(0x71, 0xf0f8, 2)
            if not report['request_polls'] or state.hex() != report['request_polls'][-1]:
                report['request_polls'].append(state.hex())
                save()
            if state == b'\x00\x02':
                break
            if state[1] & 0xf0:
                raise RuntimeError('Bootloader returned error status')
            if time.monotonic() >= deadline:
                raise TimeoutError('Read mailbox not consumed; no retries')
            time.sleep(0.02)
        first = bus.read(0x71, 0xf000, 16)
        second = bus.read(0x71, 0xf000, 16)
        report['mailbox_data'] = first.hex()
        report['matching_reads'] = first == second
        report['firmware_vector_matches'] = first == second == EXPECTED
        if not report['firmware_vector_matches']:
            raise RuntimeError('Mailbox returned data different from known firmware vector')
        report['status'] = 'bootloader-read-verified'
        save()
        if verified_action is not None:
            verified_action(bus, report, save)
    finally:
        if report.get('firmware_update_incomplete'):
            report['exit_deferred_incomplete_firmware'] = True
            save()
            raise RuntimeError('Firmware update incomplete; staying in bootloader without CPU exit')
        if report.get('flash_request_unresolved'):
            report['exit_deferred_pending_flash'] = True
            save()
            # Never reset a CPU while a submitted flash operation is unresolved.
            # No exit/reset is sent; retain the exception as chained context.
            raise RuntimeError('Flash request unresolved; CPU exit deferred to avoid interrupting programming')
        report['exit_attempts'] = 1
        save()
        for reg, value in exit_sequence:
            write(reg, value, 'exit')
        time.sleep(2)
        report['exit_0606'] = bus.read(0x71, 0x606, 1).hex()
        if report['exit_0606'] != '00':
            raise RuntimeError('Vendor exit did not restore application flags; inspect report')
        report['after_exit_before_red'] = snapshot(bus, 0x71)
        report['after'] = [snapshot(bus, a) for a in addresses]
        report['lighting_unchanged'] = report['before'] == report['after']
        report['lighting_reapplication_disabled_by_user'] = True
        report['control_unchanged'] = report['before'][1:] == report['after'][1:]
        report['control_present'] = control
        report['application_resumed'] = True
        save()
        if not report['control_unchanged']:
            raise RuntimeError('Control module changed after exit')


