"""Build the final persistence and stored-color Random Flicker firmware."""
import hashlib
import struct
from patch_storage import build as build_v1, SOURCE, ROOT

OUTPUT = ROOT / 'vcolor-7730-e000.bin'
RESTORE = 0x6E4E
EXPECTED = bytes.fromhex('002007e007490a5c0146a131044b5a54411c88b20228f5db7047')
# Load saved channel/LED counts at SRAM 20002CDC; restore A1=channels,
# A2=0 (high count byte), A3=LED count (low byte), then return.
REPLACEMENT = bytes.fromhex('0849064ba03308785870002098704878d870704700bf00bf00bf')
FLICKER_START, FLICKER_END = 0x34A8, 0x34D8
FLICKER_EXPECTED = bytes.fromhex('019803f085fa0090684600786a00aa18a1698854684640786a00aa18a16989184870684680786a00aa18a16989188870')


def build(original):
    parent, parent_manifest = build_v1(original)
    if parent[RESTORE:RESTORE + len(EXPECTED)] != EXPECTED:
        raise ValueError('Unexpected v1 restore routine')
    if len(EXPECTED) != len(REPLACEMENT):
        raise ValueError('Patch changes routine length')
    image = bytearray(parent)
    image[RESTORE:RESTORE + len(REPLACEMENT)] = REPLACEMENT
    # Retain random intensity/timing; scale each LED's stored R,B,G color.
    flicker = struct.pack('<17H', 0x6960, 0x2103, 0x4369, 0x1840, 0x69A3,
                          0x185B, 0x2103, 0x466A, 0x7992, 0x7806, 0x4356,
                          0x0A36, 0x701E, 0x3001, 0x3301, 0x3901, 0xD1F7)
    flicker += bytes.fromhex('00bf') * ((FLICKER_END - FLICKER_START - len(flicker)) // 2)
    if parent[FLICKER_START:FLICKER_END] != FLICKER_EXPECTED or len(flicker) != FLICKER_END - FLICKER_START:
        raise ValueError('Unexpected Random Flicker implementation')
    image[FLICKER_START:FLICKER_END] = flicker
    end = 0x1800 + int.from_bytes(image[0x200B:0x200E], 'little')
    checksum = (-(sum(image[0x1800:end]) - sum(image[0x2000:0x2010]))) & 0xFFFFFFFF
    struct.pack_into('<I', image, 0x2004, checksum)
    header = sum(image[0x2000:0x2008]) + sum(image[0x200B:0x200E])
    struct.pack_into('<H', image, 0x200E, header)
    assert image[:0x1800] == original[:0x1800]
    assert image[end:] == original[end:]
    pages = lambda other: [hex(a) for a in range(0, len(image), 128)
                          if image[a:a+128] != other[a:a+128]]
    manifest = dict(version='E000 final', hardware_access=False,
        source_sha256=parent_manifest['source_sha256'], parent_sha256=parent_manifest['candidate_sha256'],
        candidate_sha256=hashlib.sha256(image).hexdigest(),
        application_checksum=hex(checksum), header_checksum=hex(header),
        application_checksum_end=hex(end-1), settings_range='0xE000..0xE17F',
        changed_pages_from_original=pages(original),
        restore_patch=dict(address=hex(RESTORE), before=EXPECTED.hex(), after=REPLACEMENT.hex()),
        flicker_patch=dict(address=hex(FLICKER_START), before=FLICKER_EXPECTED.hex(), after=flicker.hex()),
        behavior='Mode13: output[i,c] = stored[i,c] * intensity[i] >> 8; intensity remains 16 or128',
        settings_format_unchanged=True,
        status='Reproducible offline build; hardware validation is documented separately')
    return bytes(image), manifest
