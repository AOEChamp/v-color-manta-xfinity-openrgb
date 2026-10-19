"""Build the patched v1 application payload offline; never flash a device.

Uses a tiny explicit MIPS32 encoder; all instructions are disassembled and
emulated by the separate test. No hardware access or device-library loading.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import runpy
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'build/clear/zephyr.bin'
OUT = ROOT / 'build/patched-v1'
BASE = 0xbf000000
CAVE = 0xb1330
LIMIT = 0xb18d0
SOURCE_HASH = 'd1d3188234476d240aa877bf064e8a44a347d4206d4f1a1aa52b6da61f29bad8'

# The firmware wire-format identifier is 0x03; release name is patched v1.
# SET_REPORT Output 03, exactly 64 bytes. Modes: static/cycle/pulse/off = 0..3.
WIRE_MAGIC = 0x42475203
MAILBOX = 0xbfc2575c
KEY_ADDRESS=BASE+LIMIT-16
KEY=b'OPENRGB_V1\0'
RECORD_MAGIC=0x33504752

def mips16_call(target,exchange=False):
    # MIPS16 JAL/JALX interleaves target[25:21] and [20:16].
    index=(target>>2)&0x3ffffff
    return struct.pack('<HH',0x1800|(0x400 if exchange else 0)|
                       ((index>>16)&0x1f)<<5|((index>>21)&0x1f),index&0xffff)

class Assembler:
    def __init__(self, address):
        self.address = address
        self.words = []
        self.labels = {}
        self.fixups = []
        self.calls = {}
        self.delegates = {}
    @property
    def pc(self): return self.address + 4 * len(self.words)
    def emit(self, word): self.words.append(word & 0xffffffff)
    def label(self, name): self.labels[name] = self.pc
    def op(self, opcode, rt, rs, imm):
        self.emit((opcode << 26) | (rs << 21) | (rt << 16) | (imm & 0xffff))
    def const(self, rt, value):
        self.op(15, rt, 0, value >> 16)
        self.op(13, rt, rt, value)
    def branch(self, opcode, rs, rt, label):
        self.fixups.append((len(self.words), label))
        self.op(opcode, rt, rs, 0)
        self.emit(0)
    def shift(self, rt, rd, amount):
        self.emit((rt << 16) | (rd << 11) | (amount << 6))
    def or_(self, rd, rs, rt):
        self.emit((rs << 21) | (rt << 16) | (rd << 11) | 0x25)
    def call16(self, target, name):
        self.calls[self.pc] = dict(target=target, name=name)
        self.emit((0x1d << 26) | ((target >> 2) & 0x3ffffff))
        self.emit(0)
    def call32(self, target, name):
        self.calls[self.pc] = dict(target=target, name=name)
        self.emit((3 << 26) | ((target >> 2) & 0x3ffffff))
        self.emit(0)
    def delegate16(self, target):
        self.const(25, target | 1)
        self.delegates[self.pc] = target | 1
        self.emit((25 << 21) | 8)  # JR t9 exchanges ISA using target bit 0.
        self.emit(0)
    def return_(self):
        self.emit((31 << 21) | 8)
        self.emit(0)
    def finish(self):
        for index, label in self.fixups:
            delta = (self.labels[label] - (self.address + index*4 + 4)) // 4
            assert -32768 <= delta < 32768
            self.words[index] |= delta & 0xffff
        return struct.pack('<%dI' % len(self.words), *self.words)

def build_code():
    a = Assembler(BASE + CAVE)
    parser = a.pc
    # Validate SET_REPORT output ID, setup length, actual length, wire magic,
    # version and opcode BEFORE touching anything but caller-saved registers.
    a.op(0x25, 8, 4, 2)       # lhu t0,2(a0): wValue
    a.op(9, 9, 0, 0x203)
    a.branch(5, 8, 9, 'fallback')
    a.op(0x25, 8, 4, 6)       # setup wLength
    a.op(9, 9, 0, 64)
    a.branch(5, 8, 9, 'fallback')
    a.op(0x23, 8, 5, 0)       # actual data length
    a.branch(5, 8, 9, 'fallback')
    a.op(0x23, 8, 6, 0)       # data pointer (firmware EP0 buffer is aligned)
    a.op(0x23, 10, 8, 0)
    a.const(9, WIRE_MAGIC)
    a.branch(5, 10, 9, 'fallback')
    a.op(0x25, 10, 8, 4)
    a.op(9,9,0,0x203)        # v3 opcode 2: query, nonce in bytes 6..8
    a.op(9,12,0,5)
    a.branch(4,10,9,'query_guard')
    a.op(9, 9, 0, 0x101)
    a.op(9, 12, 0, 1)        # v1 remains static, ignoring reserved mode byte
    a.branch(4, 10, 9, 'pack')
    a.op(9, 9, 0, 0x102)     # v2/opcode 1 adds mode at offset 9
    a.op(9, 13, 0, 0)
    a.branch(4, 10, 9, 'read_mode')
    a.op(9, 9, 0, 0x103)     # v3 adds explicit save flag at offset 10
    a.branch(5, 10, 9, 'fallback')
    a.op(0x24, 13, 8, 10)
    a.op(0xb, 9, 13, 2)
    a.branch(4, 9, 0, 'fallback')
    a.shift(13, 13, 7)
    a.label('read_mode')
    a.op(0x24, 12, 8, 9)
    a.op(0xb, 9, 12, 4)      # sltiu: mode must be 0..3
    a.branch(4, 9, 0, 'fallback')
    a.op(9, 12, 12, 1)
    a.or_(12, 12, 13)
    a.label('pack')
    # Single aligned mailbox store: USB/ISR path makes NO firmware calls.
    a.op(0x24, 10, 8, 8)
    a.shift(10, 10, 16)
    a.op(0x24, 11, 8, 7)
    a.shift(11, 11, 8)
    a.or_(10, 10, 11)
    a.op(0x24, 11, 8, 6)
    a.or_(10, 10, 11)
    a.shift(12, 12, 24)
    a.or_(10, 10, 12)        # top byte mode+1; RGB low 24 bits
    a.op(15, 8, 0, MAILBOX >> 16)
    a.op(0x2b, 10, 8, MAILBOX & 0xffff)
    a.op(9, 2, 0, 0)
    a.return_()
    a.label('fallback')
    a.delegate16(0xbf03a4cc)  # original status/headset handling, unchanged args
    a.label('query_guard')
    # Queries must never replace an unapplied mode/color/save command.
    a.op(15,9,0,MAILBOX>>16)
    a.op(0x23,9,9,MAILBOX&0xffff)
    a.branch(5,9,0,'fallback')
    a.branch(4,0,0,'pack')
    worker = a.pc
    # Existing application timer callback, not a hardware ISR. Atomically take
    # the pending color, then perform PWM with interrupts restored.
    a.op(9, 29, 29, -32)
    a.op(0x2b, 31, 29, 28)
    a.op(0x2b, 4, 29, 24)
    a.op(0x2b, 0, 29, 20)
    a.call32(0xbfc23474, 'irq_lock')
    a.op(0x2b, 2, 29, 16)
    a.op(15, 8, 0, MAILBOX >> 16)
    a.op(0x23, 10, 8, MAILBOX & 0xffff)
    a.emit((10 << 16) | (11 << 11) | (24 << 6) | 2)
    a.op(0xc, 11, 11, 0x7f)
    a.op(9, 11, 11, -1)
    a.op(0xb, 9, 11, 5)
    a.branch(4, 9, 0, 'unlock')
    a.op(0x2b, 10, 29, 20)
    a.op(0x2b, 0, 8, MAILBOX & 0xffff)
    a.label('unlock')
    a.op(0x23, 4, 29, 16)
    a.call32(0xbfc23488, 'irq_unlock')
    a.op(0x23, 10, 29, 20)
    a.branch(4, 10, 0, 'animate')
    a.emit((10<<16)|(12<<11)|(24<<6)|2)
    a.op(9,9,0,5)
    a.branch(5,12,9,'not_query')
    a.or_(4,10,0)
    a.call32(0,'read_reply')
    a.branch(4,0,0,'animate')
    a.label('not_query')
    a.branch(1, 10, 0, 'save_requested') # bltz: save bit is bit 31
    a.branch(4, 0, 0, 'save_done')
    a.label('save_requested')
    a.or_(4,10,0)
    a.call32(0,'persist_save')
    a.op(0x23,10,29,20)
    a.label('save_done')
    # Only cycle needs native initialization; direct color updates must not
    # emit the initializer's black frame before every requested color.
    a.emit((10 << 16) | (12 << 11) | (24 << 6) | 2)
    a.op(0xc,12,12,0x7f)
    a.op(9, 9, 0, 2)
    a.branch(5, 12, 9, 'initialized')
    a.call16(0xbf04ed04, 'rgb_init')
    a.op(0x23, 10, 29, 20)
    a.label('initialized')
    a.emit((10 << 16) | (12 << 11) | (24 << 6) | 2)
    a.op(0xc,12,12,0x7f)
    a.op(9, 12, 12, -1)       # wire mode 0 static, 1 cycle, 2 pulse, 3 off
    a.op(15, 8, 0, 0xbfc2)
    a.op(0x28, 0, 8, 0x5355)
    a.op(9, 9, 0, 1)
    a.branch(4, 12, 9, 'set_mode') # Cycle uses native firmware animation
    a.op(9, 9, 0, 3)
    a.branch(5, 12, 9, 'color')
    a.op(9, 10, 0, 0)         # off emits black
    a.label('color')
    a.op(0x28, 10, 8, 0x6785)  # LED serial order G,R,B
    a.emit((10 << 16) | (11 << 11) | (8 << 6) | 2)  # srl t3,t2,8
    a.op(0x28, 11, 8, 0x6784)
    a.emit((10 << 16) | (11 << 11) | (16 << 6) | 2)
    a.op(0x28, 11, 8, 0x6786)
    # Scratch target is R,G,B in 2677c..7e; native effects don't execute in
    # host pulse mode. Reset on every command before switching ownership.
    a.op(0x28, 10, 8, 0x677c)
    a.emit((10 << 16) | (11 << 11) | (8 << 6) | 2)
    a.op(0x28, 11, 8, 0x677d)
    a.emit((10 << 16) | (11 << 11) | (16 << 6) | 2)
    a.op(0x28, 11, 8, 0x677e)
    a.op(0x28, 0, 8, 0x6780)  # deterministic fresh breathing phase
    a.op(9, 9, 0, 255)
    a.op(9, 11, 0, 2)
    a.branch(5, 12, 11, 'set_mode')
    a.op(9, 9, 0, 254)
    a.label('set_mode')
    a.op(0x28, 9, 8, 0x5356)
    a.op(9, 11, 0, 254)
    a.branch(4, 9, 11, 'animate')
    a.call16(0xbf04ec44, 'pwm')
    a.label('animate')
    a.op(15, 8, 0, 0xbfc2)
    a.op(0x24, 9, 8, 0x5356)
    a.op(9, 11, 0, 254)
    a.branch(5, 9, 11, 'native_timer')
    # 64 timer ticks per triangle-wave breathing cycle; endpoint-exact 0..255.
    a.op(0x24, 9, 8, 0x6780)
    a.op(9, 10, 9, 4)
    a.op(0x28, 10, 8, 0x6780)
    a.op(0xc, 11, 9, 128)
    a.branch(4, 11, 0, 'brightness')
    a.op(9, 10, 0, 255)
    a.emit((10 << 21) | (9 << 16) | (9 << 11) | 0x23) # subu t1,t2,t1
    a.label('brightness')
    a.shift(9, 9, 1)
    # Normalize phase 0..127 to gain 0..255 (gain=2*x+(x>>6)).
    a.emit((9 << 16) | (10 << 11) | (7 << 6) | 2)
    a.or_(9, 9, 10)
    for target,output in ((0x677c,0x6785),(0x677d,0x6784),(0x677e,0x6786)):
        a.op(0x24, 10, 8, target)
        a.emit((10 << 21) | (9 << 16) | 0x19) # multu
        a.emit((11 << 11) | 0x12)             # mflo t3
        # Exact division by 255: ((x+1)+(x>>8))>>8 for x<=65025.
        a.op(9, 11, 11, 1)
        a.emit((11 << 16) | (10 << 11) | (8 << 6) | 2)
        a.emit((11 << 21) | (10 << 16) | (11 << 11) | 0x21)
        a.emit((11 << 16) | (11 << 11) | (8 << 6) | 2)
        a.op(0x28, 11, 8, output)
    a.call16(0xbf04ec44, 'pwm')
    a.label('native_timer')
    a.op(0x23, 4, 29, 24)
    a.call16(0xbf04a4b8, 'native_timer')
    a.op(0x23, 31, 29, 28)
    a.op(9, 29, 29, 32)
    a.return_()
    # Explicit save: one native binary property, using the normal settings API.
    # Compare the complete existing record first; unchanged saves do no writes.
    a.label('persist_save')
    a.op(9,29,29,-64)
    a.op(0x2b,31,29,60)
    a.const(8,0x7fffffff)
    a.emit((4<<21)|(8<<16)|(8<<11)|0x24) # and t0,a0,t0 (strip save flag)
    a.op(0x2b,8,29,20)
    a.emit((8<<21)|(9<<11)|0x27) # nor t1,t0,zero
    a.op(0x2b,9,29,24)
    a.const(8,RECORD_MAGIC)
    a.op(0x2b,8,29,16)
    for offset in (32,36,40):a.op(0x2b,0,29,offset)
    a.const(4,KEY_ADDRESS)
    a.op(9,5,29,32)
    a.op(9,6,0,12)
    a.call16(0xbf048b60,'property_get')
    a.branch(1,2,0,'write_record')
    for offset in (0,4,8):
        a.op(0x23,8,29,16+offset)
        a.op(0x23,9,29,32+offset)
        a.branch(5,8,9,'write_record')
    a.branch(4,0,0,'save_return')
    a.label('write_record')
    a.const(4,KEY_ADDRESS)
    a.op(9,5,29,16)
    a.op(9,6,0,12)
    a.call16(0xbf048b6c,'property_set')
    a.branch(1,2,0,'save_return')
    a.const(4,KEY_ADDRESS)
    a.call16(0xbf048bf0,'property_flush')
    a.label('save_return')
    a.op(0x23,31,29,60)
    a.op(9,29,29,64)
    a.return_()
    # Boot-only wrapper at the existing main-startup RGB init call. Missing or
    # invalid records leave stock defaults alone and never write flash.
    a.label('restore')
    a.op(9,29,29,-48)
    a.op(0x2b,31,29,44)
    a.call16(0xbf04ed04,'rgb_init')
    for offset in (16,20,24):a.op(0x2b,0,29,offset)
    a.const(4,KEY_ADDRESS)
    a.op(9,5,29,16)
    a.op(9,6,0,12)
    a.call16(0xbf048b60,'property_get')
    a.branch(1,2,0,'restore_return')
    a.op(0x23,8,29,16)
    a.const(9,RECORD_MAGIC)
    a.branch(5,8,9,'restore_return')
    a.op(0x23,10,29,20)
    a.op(0x23,9,29,24)
    a.emit((10<<21)|(8<<11)|0x27)
    a.branch(5,8,9,'restore_return')
    a.emit((10<<16)|(8<<11)|(24<<6)|2)
    a.op(9,8,8,-1)
    a.op(0xb,9,8,4)
    a.branch(4,9,0,'restore_return')
    a.call32(0xbfc23474,'irq_lock')
    a.op(0x2b,2,29,28)
    a.op(15,8,0,MAILBOX>>16)
    a.op(0x23,9,8,MAILBOX&0xffff)
    a.branch(5,9,0,'restore_unlock') # an already queued host command wins
    a.op(0x23,10,29,20)
    a.op(0x2b,10,8,MAILBOX&0xffff)
    a.label('restore_unlock')
    a.op(0x23,4,29,28)
    a.call32(0xbfc23488,'irq_unlock')
    a.label('restore_return')
    a.op(0x23,31,29,44)
    a.op(9,29,29,48)
    a.return_()
    a.label('read_reply')
    a.op(9,29,29,-96)
    a.op(0x2b,31,29,92)
    a.op(0x2b,4,29,84)
    # Full initialized input report, copied synchronously by native endpoint API.
    for offset in range(16,80,4):a.op(0x2b,0,29,offset)
    a.const(8,WIRE_MAGIC)
    a.op(0x2b,8,29,16)
    a.const(8,0x000f8203)    # version 3, reply opcode 82, capabilities 0f
    a.op(0x2b,8,29,20)
    a.op(15,8,0,0xbfc2)
    for source,dest in ((0x5356,23),(0x6785,24),(0x6784,25),(0x6786,26),
                        (0x677c,28),(0x677d,29),(0x677e,30)):
        a.op(0x24,9,8,source)
        a.op(0x28,9,29,dest)
    a.op(0x23,8,29,84)
    a.op(0xc,9,8,0xffff)
    a.op(0x29,9,29,44)     # nonce low 16 bits; no command marker echoed
    a.emit((8<<16)|(8<<11)|(16<<6)|2)
    a.op(0x28,8,29,46)
    a.const(4,KEY_ADDRESS)
    a.op(9,5,29,32)       # saved record at response offset 16
    a.op(9,6,0,12)
    a.call16(0xbf048b60,'property_get')
    a.op(9,4,29,16)
    a.op(9,5,0,64)
    a.call16(0xbf03a444,'report_send')
    a.op(0x23,31,29,92)
    a.op(9,29,29,96)
    a.return_()
    for address,call in a.calls.items():
        if call['name'] in ('persist_save','read_reply'):
            call['target']=a.labels[call['name']]
            a.words[(address-a.address)//4]=(3<<26)|((call['target']>>2)&0x3ffffff)
    code = a.finish()
    assert BASE+CAVE+len(code)<=KEY_ADDRESS,len(code)
    return a, parser, worker, code

def main():
    original = SOURCE.read_bytes()
    assert hashlib.sha256(original).hexdigest() == SOURCE_HASH
    a, parser, worker, code = build_code()
    data = bytearray(original)
    changes = []
    def replace(offset, content, purpose):
        before = bytes(data[offset:offset+len(content)])
        data[offset:offset+len(content)] = content
        changes.append(dict(offset=offset, length=len(content), before=before.hex(),
                            after=content.hex(), purpose=purpose))
    # All aligned pointers into the reclaimed HID log text must be retired.
    refs = [p for p in range(0, len(data)-3, 4)
            if BASE+CAVE <= struct.unpack_from('<I', data, p)[0] < BASE+LIMIT]
    # This expanded region consists solely of diagnostic format/function names.
    assert original[CAVE:LIMIT].startswith(b'send messag in isr')
    assert all(x==0 or x in (10,13) or 32<=x<127 for x in original[CAVE:LIMIT])
    starts={CAVE}|{i+1 for i in range(CAVE,LIMIT-1) if original[i]==0 and original[i+1]!=0}
    assert all(struct.unpack_from('<I',original,p)[0]-BASE in starts for p in refs)
    for value in {struct.unpack_from('<I',original,p)[0] for p in refs}:
        needle=struct.pack('<I',value)
        assert all(p%4==0 for p in range(len(original)-3) if original[p:p+4]==needle)
    assert set([0x3a53c,0x3a540,0x3a544,0x3a548,0x3a550,0x3a57c,
                    0x3a580,0x3a5e0,0x3a5e4,0x3a5e8,0x3a614,0x3a618])<=set(refs)
    for ref in refs:
        replace(ref, struct.pack('<I', BASE+0x24), 'retired diagnostic text -> empty string')
    replace(CAVE, code + bytes(KEY_ADDRESS-(BASE+CAVE+len(code)))+KEY+bytes(16-len(KEY)), 'MIPS32 RGB/persistence code and property key')
    assert original[0x18da4:0x18da8]==mips16_call(0xbf04ed04)
    assert original[0x4ec5e:0x4ec62]==mips16_call(0xbfc23474,True)
    replace(0x18da4,mips16_call(a.labels['restore'],True),'main boot RGB init -> restore wrapper (MIPS32)')
    assert struct.unpack_from('<I', original, 0xb18dc)[0] == 0xbf03a4cd
    replace(0xb18dc, struct.pack('<I', parser), 'HID SET_REPORT callback (MIPS32)')
    assert struct.unpack_from('<I', original, 0x4a94c)[0] == 0xbf04a4b9
    replace(0x4a94c, struct.pack('<I', worker), 'application timer callback -> mailbox worker (MIPS32)')
    assert original[0x3a504:0x3a506] == bytes.fromhex('12b3')
    replace(0x3a504, bytes.fromhex('0403'), 'original status word -> spare stack local sp+16, freeing mailbox')
    OUT.mkdir(parents=True,exist_ok=True)
    output = OUT / 'zephyr-rgb.clear.bin'
    output.write_bytes(data)
    # Known inverse transform; separately verified against every original payload.
    with contextlib.redirect_stdout(io.StringIO()):
        encoder = runpy.run_path(str(ROOT / 'tools/verify_pebble_reencoding.py'))['encode']
    encoded = encoder(bytes(data))
    (OUT / 'zephyr-rgb.encoded.bin').write_bytes(encoded)
    manifest = dict(version="patched v1", source_sha256=SOURCE_HASH, clear_sha256=hashlib.sha256(data).hexdigest(),
        encoded_sha256=hashlib.sha256(encoded).hexdigest(), size=len(data),
        parser=parser, worker=worker, code_size=len(code), code_end=a.pc,
        calls=a.calls, delegates=a.delegates, changes=changes,
        protocol=dict(report_id=3, transfer='HID SET_REPORT Output, EP0', length=64,
                      prefix='03 52 47 42 03 01', rgb_offsets=[6,7,8],mode_offset=9,save_flag_offset=10,
                      modes={'static':0,'cycle':1,'pulse':2,'off':3},
                      query_opcode=2,reply_opcode=0x82,query_transport='control output request; interrupt input response'),
        mailbox=MAILBOX,restore=a.labels['restore'],save=a.labels['persist_save'],query=a.labels['read_reply'],property_key=KEY[:-1].decode(),
        stack_frames=dict(worker=32,save_helper=64,boot_restore=48,query_helper=96),
        transport='atomic latest-mode/color/save mailbox; consumed by existing application timer',
        status='Patched v1 payload; offline instruction, layout and boot checks are run separately')
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({k:manifest[k] for k in ('status','code_size','size','clear_sha256')}, indent=2))

if __name__ == '__main__': main()
