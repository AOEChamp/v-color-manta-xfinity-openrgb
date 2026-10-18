"""Offline v3 candidate: Random Flicker uses each LED's stored color."""
import hashlib
import json
import struct
from firmware_image import build as build_v2, SOURCE, ROOT

OUTPUT = ROOT / 'vcolor-7730-e000-v3-stored-flicker.bin'
START, END = 0x34A8, 0x34D8
EXPECTED = bytes.fromhex('019803f085fa0090684600786a00aa18a1698854684640786a00aa18a16989184870684680786a00aa18a16989188870')


def build(original):
    parent, parent_manifest = build_v2(original)
    # Replace only color generation/output. Random choices, tick/hue counters,
    # LED iteration, output pointer, effect selection and speed remain intact.
    code = struct.pack('<17H', 0x6960, 0x2103, 0x4369, 0x1840, 0x69A3,
                       0x185B, 0x2103, 0x466A, 0x7992, 0x7806, 0x4356,
                       0x0A36, 0x701E, 0x3001, 0x3301, 0x3901, 0xD1F7)
    code += bytes.fromhex('00bf') * ((END - START - len(code)) // 2)
    if len(code) != END - START or parent[START:END] != EXPECTED:
        raise ValueError('Unexpected v2 Random Flicker implementation')
    image = bytearray(parent)
    image[START:END] = code
    end = 0x1800 + int.from_bytes(image[0x200B:0x200E], 'little')
    checksum = (-(sum(image[0x1800:end]) - sum(image[0x2000:0x2010]))) & 0xFFFFFFFF
    struct.pack_into('<I', image, 0x2004, checksum)
    header = sum(image[0x2000:0x2008]) + sum(image[0x200B:0x200E])
    struct.pack_into('<H', image, 0x200E, header)
    assert image[:0x1800] == original[:0x1800] and image[end:] == original[end:]
    manifest = dict(version='E000 v3 stored-color Random Flicker', hardware_access=False,
        parent_sha256=parent_manifest['candidate_sha256'], candidate_sha256=hashlib.sha256(image).hexdigest(),
        application_checksum=hex(checksum), header_checksum=hex(header),
        changed_pages_from_v2=[hex(a) for a in range(0, 65536, 128) if image[a:a+128] != parent[a:a+128]],
        patch=dict(address=hex(START), before=EXPECTED.hex(), after=code.hex()),
        behavior='Mode13: output[i,c] = stored[i,c] * intensity[i] >> 8; intensity remains 16 or128',
        settings_format_unchanged=True, status='Reproducible offline build; hardware validation is documented separately')
    return bytes(image), manifest


if __name__ == '__main__':
    image, manifest = build(SOURCE.read_bytes())
    OUTPUT.write_bytes(image)
    OUTPUT.with_suffix('.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))
