"""Rebuild the patched v1 container offline; never access a device.

The shipped manifest reverses the local patch to recover the exact stock input.
All recovered and rebuilt bytes are checked against the known image hashes.
"""
from pathlib import Path
import hashlib, json, runpy, struct, zlib
from container import Image

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'build'
STOCK='5c92e9dbf65713ee2435babb186aa1442d149918029208727b0e4d9e9918248b'
PATCHED='7fe19a661d17c2abd1de215c65afb5ae87d1775474c150274f0614a5c7dd90fe'
sha=lambda b:hashlib.sha256(b).hexdigest()

def main():
    shipped=(ROOT/'images/MF1710-RGB-patched-v1.fw').read_bytes()
    assert sha(shipped)==PATCHED,'Unexpected packaged firmware'
    image=Image(shipped)
    decoded=WORK/'decoded';decoded.mkdir(parents=True,exist_ok=True)
    clear=WORK/'clear';clear.mkdir(exist_ok=True)
    for name,short in [('sdfs_ori.bin',b'SDFS_ORIBIN'),('sdfs.bin',b'SDFS    BIN'),
                       ('zephyr.bin',b'ZEPHYR  BIN'),('mbrec.bin',b'MBREC   BIN'),('param.bin',b'PARAM   BIN')]:
        (decoded/name).write_bytes(image.extract_xor(image.entry(short)))
    runpy.run_path(str(ROOT/'tools/decode_pebble_payloads.py'))
    manifest=json.loads((ROOT/'validation/manifest.json').read_text())
    stock=bytearray((clear/'zephyr.bin').read_bytes())
    for change in reversed(manifest['changes']):
        start=change['offset'];end=start+change['length']
        assert stock[start:end]==bytes.fromhex(change['after'])
        stock[start:end]=bytes.fromhex(change['before'])
    assert sha(stock)==manifest['source_sha256']
    (clear/'zephyr.bin').write_bytes(stock)
    # Establish the encoder from the paired SDFS files before verifying stock.
    # Import the inverse tool only after the original encoded application exists.
    import contextlib,io
    source=(ROOT/'tools/verify_pebble_reencoding.py').read_text()
    definitions=source[:source.index('assert encode(plain[1500*32:])')]
    namespace={'__file__':str(ROOT/'tools/verify_pebble_reencoding.py')}
    exec(compile(definitions,namespace['__file__'],'exec'),namespace)
    (decoded/'zephyr.bin').write_bytes(namespace['encode'](stock))
    original=image.replace_xor(image.entry(b'ZEPHYR  BIN'),(decoded/'zephyr.bin').read_bytes())
    assert sha(original)==STOCK,'Recovered stock container differs'
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(str(ROOT/'tools/build_pebble_rgb_persistent.py'),run_name='__main__')
    candidate=WORK/'patched-v1'
    encoded=(candidate/'zephyr-rgb.encoded.bin').read_bytes()
    result=Image(original).replace_xor(image.entry(b'ZEPHYR  BIN'),encoded)
    assert result==shipped,'Rebuild differs from tested firmware'
    # Verify partition boundaries and both parameter CRCs independently.
    param=(clear/'param.bin').read_bytes()
    assert param[:4]==b'ACPT' and param[0x180:0x184]==b'FVER'
    assert zlib.crc32(param[:0x17c])==struct.unpack_from('<I',param,0x17c)[0]
    assert zlib.crc32(param[0x180:0x1fc])==struct.unpack_from('<I',param,0x1fc)[0]
    count,stride=struct.unpack_from('<HH',param,8);assert (count,stride)==(11,24)
    slots=[];end=0
    for i in range(count):
        p=16+i*stride;start,size,address=struct.unpack_from('<III',param,p+12)
        if i:assert start==end
        end=start+size
        if param[p+8]==2 and param[p+9]==4:slots.append(size)
    assert end==0x200000 and len(slots)==2
    assert all(len(encoded)<=size for size in slots)
    assert len(encoded)==839360 and len(result)==4890640
    # Same-size member replacement preserves every other FAT file and DB tail.
    allowed=set()
    entry=image.entry(b'ZEPHYR  BIN')
    for i,c in enumerate(entry['clusters']):
        n=min(image.cluster_size,len(encoded)-i*image.cluster_size)
        allowed.update(range(16+image.offset(c),16+image.offset(c)+n))
    assert all(i in allowed for i,(a,b) in enumerate(zip(original,result)) if a!=b)
    (candidate/'MF1710-RGB-patched-v1.fw').write_bytes(result)
    report={'stock_sha256':STOCK,'container_sha256':sha(result),'exact_shipped_rebuild':True,
            'application_bytes':len(encoded),'container_bytes':len(result),'application_slot_bytes':slots,
            'bootloader_and_other_members_unchanged':True,'parameter_crc_valid':True,
            'hardware_access':False}
    (candidate/'rebuild.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
