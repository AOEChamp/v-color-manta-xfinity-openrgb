"""Offline inspection of an acquired DIMM image; never accesses hardware."""
import argparse
import hashlib
from pathlib import Path
import re
import struct
import sys

import capstone

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('image', type=Path)
args = parser.parse_args()
with args.image.open('rb') as stream:
    data = stream.read()
decoder = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
decoder.detail = True
rows = [f'Input: {args.image.name}', f'Bytes: {len(data)}',
        f'SHA256: {hashlib.sha256(data).hexdigest()}']
for match in re.finditer(rb'[ -~]{8,}', data):
    if b'6K' in match.group() or b'WINUSB' in match.group():
        rows.append(f'Label {match.start():04x}: {match.group().decode("ascii")}')
for name, start, end in [
    ('mailbox dispatcher', 0x4138, 0x41fe),
    ('configuration startup', 0x420c, 0x43b4),
    ('save serializer', 0x6ab0, 0x6c10),
    ('restore settings', 0x6df0, 0x6e90),
    ('saved settings validator', 0x6e90, 0x6edc),
    ('flash erase helper', 0x35e0, 0x3690),
]:
    rows.append(f'\n{name}: {start:#x}..{end:#x}')
    for ins in decoder.disasm(data[start:end], start):
        note = ''
        if ins.mnemonic == 'ldr' and len(ins.operands) > 1:
            op = ins.operands[1]
            if op.type == capstone.arm.ARM_OP_MEM and op.mem.base == capstone.arm.ARM_REG_PC:
                literal = ((ins.address + 4) & ~3) + op.mem.disp
                if literal + 4 <= len(data):
                    note = f' ; [{literal:#x}]={struct.unpack_from("<I", data, literal)[0]:#010x}'
        rows.append(f'{ins.address:04x} {ins.mnemonic} {ins.op_str}{note}')
output = args.image.parent / 'firmware-focused.asm'
output.write_text('\n'.join(rows), encoding='utf-8')
print(output)
