"""Build E000 v2: restore the serialized LED count as a big-endian word."""
import hashlib
import json
import struct
from patch_storage import build as build_v1, SOURCE, ROOT

OUTPUT = ROOT / 'vcolor-7730-e000-v2.bin'
RESTORE = 0x6E4E
EXPECTED = bytes.fromhex('002007e007490a5c0146a131044b5a54411c88b20228f5db7047')
# Load saved channel/LED counts at SRAM 20002CDC; restore A1=channels,
# A2=0 (high count byte), A3=LED count (low byte), then return.
REPLACEMENT = bytes.fromhex('0849064ba03308785870002098704878d870704700bf00bf00bf')


def build(original):
    parent, parent_manifest = build_v1(original)
    if parent[RESTORE:RESTORE + len(EXPECTED)] != EXPECTED:
        raise ValueError('Unexpected v1 restore routine')
    if len(EXPECTED) != len(REPLACEMENT):
        raise ValueError('Patch changes routine length')
    image = bytearray(parent)
    image[RESTORE:RESTORE + len(REPLACEMENT)] = REPLACEMENT
    end = 0x1800 + int.from_bytes(image[0x200B:0x200E], 'little')
    checksum = (-(sum(image[0x1800:end]) - sum(image[0x2000:0x2010]))) & 0xFFFFFFFF
    struct.pack_into('<I', image, 0x2004, checksum)
    header = sum(image[0x2000:0x2008]) + sum(image[0x200B:0x200E])
    struct.pack_into('<H', image, 0x200E, header)
    assert image[:0x1800] == original[:0x1800]
    assert image[end:] == original[end:]
    pages = lambda other: [hex(a) for a in range(0, len(image), 128)
                          if image[a:a+128] != other[a:a+128]]
    manifest = dict(version='E000 v2', hardware_access=False,
        source_sha256=parent_manifest['source_sha256'], parent_sha256=parent_manifest['candidate_sha256'],
        candidate_sha256=hashlib.sha256(image).hexdigest(),
        application_checksum=hex(checksum), header_checksum=hex(header),
        application_checksum_end=hex(end-1), settings_range='0xE000..0xE17F',
        changed_pages_from_v1=pages(parent), changed_pages_from_original=pages(original),
        restore_patch=dict(address=hex(RESTORE), before=EXPECTED.hex(), after=REPLACEMENT.hex()),
        settings_format_unchanged=True, existing_v1_saved_block_compatible=True,
        status='Offline build; not installed or hardware validated')
    return bytes(image), manifest


