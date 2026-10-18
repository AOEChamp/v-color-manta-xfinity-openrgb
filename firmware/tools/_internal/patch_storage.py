"""Build an exact-image persistence relocation candidate. No hardware access."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2] / 'images'
SOURCE = ROOT / 'vcolor-7730-0x71-20261017T135335444329Z-pass1.bin'
SHA256 = 'beaa0db9a2cee7c0ad0af668fd3860b3a1b4d327f7150941d39d0f3db40c278a'
OUTPUT = ROOT / 'vcolor-7730-e000-candidate.bin'


def build(original):
    if len(original) != 65536 or hashlib.sha256(original).hexdigest() != SHA256:
        raise ValueError('Only the verified original DIMM image is supported')
    image = bytearray(original)
    changes = []

    def patch(address, expected, replacement, reason):
        if image[address:address + len(expected)] != expected:
            raise ValueError(f'Unexpected bytes at {address:#x}')
        assert len(expected) == len(replacement)
        image[address:address + len(expected)] = replacement
        changes.append(dict(address=hex(address), before=expected.hex(),
                            after=replacement.hex(), reason=reason))

    # MOVS r0,#28; LSLS r0,r0,#11 = E000 (was 3F << 11 = 1F800).
    for address, reason in [(0x4184, 'command 02 first erase page'),
                            (0x41CE, 'command 55 first erase page'),
                            (0x6B42, 'AA save first page')]:
        patch(address, bytes.fromhex('3f20c002'), bytes.fromhex('1c20c002'), reason)
    for address, before, after, reason in [
        (0x4208, 0x1F880, 0xE080, 'erase second page; third derived by +80'),
        (0x6B7C, 0x1F880, 0xE080, 'save second page; third derived by +80'),
        (0x6ED4, 0x1F600, 0xE000, 'validator and restore source'),
    ]:
        patch(address, struct.pack('<I', before), struct.pack('<I', after), reason)

    length = int.from_bytes(image[0x200B:0x200E], 'little')
    end = 0x1800 + length
    assert end == 0xB748 and not any(image[0xE000:0xE180])
    checksum = (-(sum(image[0x1800:end]) - sum(image[0x2000:0x2010]))) & 0xFFFFFFFF
    patch(0x2004, original[0x2004:0x2008], checksum.to_bytes(4, 'little'),
          'application additive checksum complement')
    # Header sum excludes offsets 8..10 and its own 14..15 checksum bytes.
    header_sum = sum(image[0x2000:0x2008]) + sum(image[0x200B:0x200E])
    patch(0x200E, original[0x200E:0x2010], header_sum.to_bytes(2, 'little'),
          'header checksum after application checksum update')
    assert image[:0x1800] == original[:0x1800]
    assert image[end:] == original[end:]
    pages = [a for a in range(0, len(image), 128)
             if image[a:a+128] != original[a:a+128]]
    report = dict(hardware_access=False, source_sha256=SHA256,
                  candidate_sha256=hashlib.sha256(image).hexdigest(),
                  settings_range='0xE000..0xE17F', application_checksum_end=hex(end - 1),
                  application_checksum=hex(checksum), header_checksum=hex(header_sum),
                  changed_pages=[hex(a) for a in pages], patches=changes,
                  unchanged_metadata_literals=['0x43AC', '0x43B0', '0x44B8', '0x44BC'],
                  status='Offline candidate; not installed or hardware validated')
    return bytes(image), report
