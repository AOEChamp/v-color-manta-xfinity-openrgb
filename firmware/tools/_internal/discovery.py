"""Discovery and interactive selection shared by the flashing command."""
import json
import subprocess
import transport as module

ADDRESSES = tuple(range(0x70, 0x74))

def discover(bus):
    rows = []
    for address in ADDRESSES:
        try:
            signature = bus.read(address, 0xB500, 5)
            chip = bus.read(address, 0x4000, 2)
        except OSError:
            continue  # No responding RGB controller at this candidate address.
        supported = signature == module.SIGNATURE and chip == bytes.fromhex('7730')
        rows.append(dict(address=address, chip=chip.hex(), signature=signature.hex(),
                         hardware_name='ENE 6K7732 (firmware-identified)' if supported else 'Unrecognized RGB controller',
                         compatible_identity=supported))
    return rows


def windows_dimms():
    command = 'Get-CimInstance Win32_PhysicalMemory | Select-Object DeviceLocator,Manufacturer,PartNumber | ConvertTo-Json -Compress'
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                            capture_output=True, text=True, check=True)
    data = json.loads(result.stdout) if result.stdout.strip() else []
    return [data] if isinstance(data, dict) else data


def display(rows):
    print('RGB controllers (PIIX4 port 0):')
    for index, row in enumerate(rows, 1):
        state = 'identity matches; stock preflight still required' if row['compatible_identity'] else 'not supported'
        print(f"{index}. {row['address']:#04x}  {row['hardware_name']}  chip={row['chip']}  signature={row['signature']}  [{state}]")
    if not rows:
        print('No responding RGB controllers found in 0x70..0x73.')
    try:
        dimms = windows_dimms()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'Windows DIMM inventory unavailable: {exc}')
    else:
        print('\nInstalled DIMM hardware names reported by Windows:')
        for row in dimms:
            print('  ' + ' | '.join(str(row.get(k) or '').strip() for k in ('DeviceLocator', 'Manufacturer', 'PartNumber')))
        print('Windows slot/part names cannot reliably be mapped to RGB SMBus addresses; no mapping is assumed.')


def choose(rows, input_fn=input):
    display(rows)
    if not any(r['compatible_identity'] for r in rows):
        raise RuntimeError('No compatible RGB controller identity found')
    answer = input_fn('Select controller number to flash (Enter to cancel): ').strip()
    if not answer:
        raise RuntimeError('Cancelled; no firmware writes sent')
    if not answer.isdecimal() or not 1 <= int(answer) <= len(rows):
        raise ValueError('Invalid controller selection')
    row = rows[int(answer) - 1]
    if not row['compatible_identity']:
        raise ValueError('Selected controller is not supported')
    return row['address']
