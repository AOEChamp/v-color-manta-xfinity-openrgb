"""Offline inverse-encoding feasibility check; creates no flashable image."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'build/decoded'
clear = root / 'build/clear'
plain = (source / 'sdfs_ori.bin').read_bytes()
encoded = (source / 'sdfs.bin').read_bytes()
basis = {}
for offset in range(0, 1500 * 32, 32):
    x = int.from_bytes(plain[offset:offset+32], 'little') | (1 << 256)
    y = int.from_bytes(encoded[offset:offset+32], 'little')
    while x:
        bit = x.bit_length() - 1
        if bit not in basis:
            basis[bit] = x, y
            break
        bx, by = basis[bit]
        x ^= bx
        y ^= by
    else:
        assert y == 0
assert len(basis) == 257

def encode(data):
    assert len(data) % 32 == 0
    result = bytearray()
    for offset in range(0, len(data), 32):
        x = int.from_bytes(data[offset:offset+32], 'little') | (1 << 256)
        y = 0
        while x:
            bx, by = basis[x.bit_length() - 1]
            x ^= bx
            y ^= by
        result.extend(y.to_bytes(32, 'little'))
    return bytes(result)

assert encode(plain[1500*32:]) == encoded[1500*32:]
rows = []
for name in ('sdfs.bin', 'zephyr.bin', 'mbrec.bin', 'param.bin'):
    original = (source / name).read_bytes()
    rebuilt = encode((clear / name).read_bytes())
    assert rebuilt == original, name
    rows.append(dict(name=name, size=len(rebuilt), exact_match=True,
                     sha256=hashlib.sha256(rebuilt).hexdigest()))
report = dict(inverse_rank=257, heldout_blocks=628, heldout_exact_match=True,
              payloads=rows, modified_image_created=False,
              limitation='Does not validate package rebuilding, checksums, boot authentication, update transport or recovery.')
(clear / 'reencoding-validation.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
