"""Build patched v1: persistence, count restoration and stored-color Random Flicker."""
import hashlib
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "images"
SOURCE = ROOT / "vcolor-7730-stock.bin"
SOURCE_SHA256 = "beaa0db9a2cee7c0ad0af668fd3860b3a1b4d327f7150941d39d0f3db40c278a"

OUTPUT = ROOT / 'vcolor-7730-patched-v1.bin'
RESTORE = 0x6E4E
EXPECTED = bytes.fromhex('002007e007490a5c0146a131044b5a54411c88b20228f5db7047')
# Load saved channel/LED counts at SRAM 20002CDC; restore A1=channels,
# A2=0 (high count byte), A3=LED count (low byte), then return.
REPLACEMENT = bytes.fromhex('0849064ba03308785870002098704878d870704700bf00bf00bf')
FLICKER_START, FLICKER_END = 0x34A8, 0x34D8
FLICKER_EXPECTED = bytes.fromhex('019803f085fa0090684600786a00aa18a1698854684640786a00aa18a16989184870684680786a00aa18a16989188870')


def build(original):
    if len(original) != 65536 or hashlib.sha256(original).hexdigest() != SOURCE_SHA256:
        raise ValueError('Only the verified original DIMM image is supported')
    image = bytearray(original)
    storage_patches = []
    def patch(address, expected, replacement, reason):
        if image[address:address+len(expected)] != expected or len(expected) != len(replacement):
            raise ValueError(f'Unexpected bytes at {address:#x}')
        image[address:address+len(expected)] = replacement
        storage_patches.append(dict(address=hex(address),before=expected.hex(),after=replacement.hex(),reason=reason))
    for address,reason in [(0x4184,'command 02 first erase page'),
                           (0x41CE,'command 55 first erase page'),
                           (0x6B42,'AA save first page')]:
        patch(address,bytes.fromhex('3f20c002'),bytes.fromhex('1c20c002'),reason)
    for address,before,after,reason in [
        (0x4208,0x1F880,0xE080,'erase second page; third derived by +80'),
        (0x6B7C,0x1F880,0xE080,'save second page; third derived by +80'),
        (0x6ED4,0x1F600,0xE000,'validator and restore source')]:
        patch(address,struct.pack('<I',before),struct.pack('<I',after),reason)
    if image[RESTORE:RESTORE+len(EXPECTED)] != EXPECTED or len(EXPECTED) != len(REPLACEMENT):
        raise ValueError('Unexpected stock restore routine')
    image[RESTORE:RESTORE + len(REPLACEMENT)] = REPLACEMENT
    # Retain random intensity/timing; scale each LED's stored R,B,G color.
    flicker = struct.pack('<17H', 0x6960, 0x2103, 0x4369, 0x1840, 0x69A3,
                          0x185B, 0x2103, 0x466A, 0x7992, 0x7806, 0x4356,
                          0x0A36, 0x701E, 0x3001, 0x3301, 0x3901, 0xD1F7)
    flicker += bytes.fromhex('00bf') * ((FLICKER_END - FLICKER_START - len(flicker)) // 2)
    if original[FLICKER_START:FLICKER_END] != FLICKER_EXPECTED or len(flicker) != FLICKER_END - FLICKER_START:
        raise ValueError('Unexpected Random Flicker implementation')
    image[FLICKER_START:FLICKER_END] = flicker
    end = 0x1800 + int.from_bytes(image[0x200B:0x200E], 'little')
    assert end == 0xB748 and not any(image[0xE000:0xE180])
    checksum = (-(sum(image[0x1800:end]) - sum(image[0x2000:0x2010]))) & 0xFFFFFFFF
    struct.pack_into('<I', image, 0x2004, checksum)
    header = sum(image[0x2000:0x2008]) + sum(image[0x200B:0x200E])
    struct.pack_into('<H', image, 0x200E, header)
    assert image[:0x1800] == original[:0x1800]
    assert image[end:] == original[end:]
    pages = lambda other: [hex(a) for a in range(0, len(image), 128)
                          if image[a:a+128] != other[a:a+128]]
    manifest = dict(version='patched v1', hardware_access=False,
        source_sha256=SOURCE_SHA256, storage_patches=storage_patches,
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
