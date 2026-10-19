"""Recover the package's 32-byte affine encoding from its paired SDFS images.

Offline only. Fit 1500 blocks, independently verify remaining 628, then decode
other same-format payloads. Does not execute or modify firmware or access USB.
"""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'build/decoded'
out = root / 'build/clear'
out.mkdir(exist_ok=True)
plain = (source / 'sdfs_ori.bin').read_bytes()
encoded = (source / 'sdfs.bin').read_bytes()
assert len(plain) == len(encoded) == 68096
assert len(plain) % 32 == 0
basis = {}
training = 1500
for offset in range(0, training * 32, 32):
    x = int.from_bytes(encoded[offset:offset+32], 'little') | (1 << 256)
    y = int.from_bytes(plain[offset:offset+32], 'little')
    while x:
        bit = x.bit_length() - 1
        if bit not in basis:
            basis[bit] = (x, y)
            break
        bx, by = basis[bit]
        x ^= bx
        y ^= by
    else:
        assert y == 0, 'Training pair contradicts affine transform'
assert len(basis) == 257, 'Transform is not fully determined'

def decode(data):
    assert len(data) % 32 == 0
    result = bytearray()
    for offset in range(0, len(data), 32):
        x = int.from_bytes(data[offset:offset+32], 'little') | (1 << 256)
        y = 0
        while x:
            bit = x.bit_length() - 1
            bx, by = basis[bit]
            x ^= bx
            y ^= by
        result.extend(y.to_bytes(32, 'little'))
    return bytes(result)

assert decode(encoded[training*32:]) == plain[training*32:], 'Held-out SDFS comparison failed'
assert decode(encoded) == plain, 'Full SDFS comparison failed'
report = dict(block_size=32, rank=257, training_blocks=training,
              heldout_blocks=(len(plain)//32)-training, heldout_exact_match=True,
              full_sdfs_exact_match=True, payloads=[])
for name in ('sdfs.bin', 'zephyr.bin', 'mbrec.bin', 'param.bin'):
    data = decode((source / name).read_bytes())
    (out / name).write_bytes(data)
    row = dict(name=name, size=len(data), sha256=hashlib.sha256(data).hexdigest(), header=data[:64].hex(' '))
    report['payloads'].append(row)
    print(name, len(data), row['sha256'], data[:16].hex(' '))
(out / 'decode-validation.json').write_text(json.dumps(report, indent=2))
