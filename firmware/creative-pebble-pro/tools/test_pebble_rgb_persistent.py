"""Execute patched v1 MIPS32 instructions offline with Unicorn.

Native MIPS16 callees and ISA-return boundaries are stubbed, explicitly. This
tests the injected machine code, not a whole-device or boot emulation.
"""
import hashlib
import json
from pathlib import Path
import random
import struct
import sys
import contextlib
import io
import runpy

ROOT = Path(__file__).resolve().parents[1]
import pypcode
import unicorn
from unicorn.mips_const import *
from build_pebble_rgb_persistent import build_code, MAILBOX, OUT, SOURCE, CAVE, RECORD_MAGIC, KEY_ADDRESS, KEY, mips16_call

class Machine:
    def __init__(self):
        self.asm, self.parser, self.worker, self.code = build_code()
        self.u = unicorn.Uc(unicorn.UC_ARCH_MIPS,
                            unicorn.UC_MODE_MIPS32 | unicorn.UC_MODE_LITTLE_ENDIAN)
        # CPU KSEG1 accesses map to these physical addresses.
        self.u.mem_map(0x1f0b1000, 0x1000)
        self.u.mem_write(self.parser & 0x1fffffff, self.code)
        self.u.mem_write(KEY_ADDRESS&0x1fffffff,KEY)
        self.u.mem_map(0x1fc25000, 0x3000)
        self.u.mem_map(0x10000, 0x20000)
        self.u.hook_add(unicorn.UC_HOOK_CODE, self.step)
        self.u.hook_add(unicorn.UC_HOOK_MEM_WRITE, self.write)
        self.inject_on_unlock=None
        self.properties={};self.set_count=0;self.flush_count=0;self.property_error=False
        self.replies=[]
        self.saved_regs = [UC_MIPS_REG_S0, UC_MIPS_REG_S1, UC_MIPS_REG_S2,
                           UC_MIPS_REG_S3, UC_MIPS_REG_S4, UC_MIPS_REG_S5,
                           UC_MIPS_REG_S6, UC_MIPS_REG_S7, UC_MIPS_REG_GP,
                           UC_MIPS_REG_FP]
    def write(self, u, access, address, size, value, user):
        self.writes.append((address, size))
    def clobber(self, pc):
        for reg in (UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3,
                    UC_MIPS_REG_T0,UC_MIPS_REG_T1,UC_MIPS_REG_T2,UC_MIPS_REG_T3,
                    UC_MIPS_REG_T4,UC_MIPS_REG_T5,UC_MIPS_REG_T6,UC_MIPS_REG_T7,
                    UC_MIPS_REG_T8,UC_MIPS_REG_T9,UC_MIPS_REG_V1):
            self.u.reg_write(reg, 0xdeadbeef)
        self.u.reg_write(UC_MIPS_REG_RA, pc+8)
        self.u.reg_write(UC_MIPS_REG_PC, pc+8)
    def step(self, u, pc, size, user):
        if pc in self.asm.calls:
            call = self.asm.calls[pc]
            if call['name'] in ('persist_save','read_reply'):return # real injected helpers
            if call['name'] == 'irq_lock':
                assert not self.locked
                self.locked=True
                result=0x12345678
            elif call['name'] == 'irq_unlock':
                assert self.locked and u.reg_read(UC_MIPS_REG_A0)==0x12345678
                self.locked=False
                if self.inject_on_unlock is not None:
                    u.mem_write(MAILBOX & 0x1fffffff,struct.pack('<I',self.inject_on_unlock))
                    self.inject_on_unlock=None
                result=0
            elif call['name'] == 'pwm':
                assert not self.locked
                self.pwm.append(bytes(u.mem_read(0x1fc26784, 3)))
                result = 0
            elif call['name'] == 'rgb_init':
                assert not self.locked
                u.mem_write(0x1fc26774,bytes(20))
                self.init_count+=1
                result=0
            elif call['name']=='report_send':
                assert not self.locked and u.reg_read(UC_MIPS_REG_A1)==64
                self.replies.append(bytes(u.mem_read(u.reg_read(UC_MIPS_REG_A0),64)))
                result=0
            elif call['name'] in ('property_get','property_set','property_flush'):
                assert not self.locked
                key=u.reg_read(UC_MIPS_REG_A0)
                assert key==KEY_ADDRESS
                name=bytes(u.mem_read(key&0x1fffffff,11)).split(b'\0')[0]
                assert name==b'OPENRGB_V1'
                data=u.reg_read(UC_MIPS_REG_A1);length=u.reg_read(UC_MIPS_REG_A2)
                if call['name']=='property_get':
                    assert length==12
                    value=self.properties.get(name)
                    if value is None or self.property_error:result=0xfffffffe
                    else:
                        u.mem_write(data,value[:length]);result=0 # uncached native get returns 0 on success
                elif call['name']=='property_set':
                    assert length==12
                    self.set_count+=1
                    if self.property_error:result=0xfffffffb
                    else:self.properties[name]=bytes(u.mem_read(data,length));result=0
                else:
                    self.flush_count+=1;result=0
            else:
                assert not self.locked and u.reg_read(UC_MIPS_REG_A0)==0x10200
                self.native_timer_count+=1
                result=0
            self.clobber(pc)
            u.reg_write(UC_MIPS_REG_V0, result)
        elif pc in self.asm.delegates:
            self.delegate = self.asm.delegates[pc]
            self.end_args = [u.reg_read(r) for r in (UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2)]
            self.done = True
            u.emu_stop()
        elif struct.unpack('<I',u.mem_read(pc & 0x1fffffff,4))[0] == 0x03e00008:
            if u.reg_read(UC_MIPS_REG_RA) == 0x40001:
                self.done = True
                u.emu_stop()
    def run(self, entry, args):
        self.writes=[]; self.pwm=[]; self.delegate=None
        self.done=False;self.locked=False;self.native_timer_count=0;self.init_count=0
        for i,reg in enumerate(self.saved_regs): self.u.reg_write(reg,0x12340000+i)
        self.u.reg_write(UC_MIPS_REG_SP,0x28000)
        self.u.reg_write(UC_MIPS_REG_RA,0x40001) # preserve a MIPS16 return address
        for r,v in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2),args): self.u.reg_write(r,v)
        self.u.emu_start(entry,0,count=700)
        assert self.done, 'instruction limit reached'
        assert self.u.reg_read(UC_MIPS_REG_SP)==0x28000
        assert not self.locked
        for i,reg in enumerate(self.saved_regs): assert self.u.reg_read(reg)==0x12340000+i
        assert all(0x27f80<=address and address+size<=0x28000 or
            address in (0x1fc2575c,0x1fc25355,0x1fc25356,0x1fc2677c,0x1fc2677d,
                        0x1fc2677e,0x1fc26780,0x1fc26784,0x1fc26785,0x1fc26786)
            for address,size in self.writes)
        return self.u.reg_read(UC_MIPS_REG_V0)
    def rx(self, packet, value=0x203, length=64, actual=64):
        setup=struct.pack('<BBHHH',0x21,9,value,0,length)
        self.u.mem_write(0x10000,setup)
        self.u.mem_write(0x10010,struct.pack('<I',actual))
        self.u.mem_write(0x10020,struct.pack('<I',0x10100))
        self.u.mem_write(0x10100,bytes(packet))
        return self.run(self.parser,[0x10000,0x10010,0x10020])
    def apply(self):
        return self.run(self.worker,[0x10200,0,0])

def main():
    m=Machine()
    ctx=pypcode.Context('MIPS:LE:32:default')
    ins=ctx.disassemble(m.code,base_address=m.parser).instructions
    assert sum(i.length for i in ins)==len(m.code) and all(i.length==4 for i in ins)
    listing='\n'.join('%08x %-7s %s'%(i.addr.offset,i.mnem,i.body) for i in ins)
    (OUT/'injected-code.disasm.txt').write_text(listing)
    # Original MIPS16 status handler gets a real 4-byte local at sp+16.
    hook=pypcode.Context('MIPS:LE:32:16e').disassemble(bytes.fromhex('0403'),
            base_address=0xbf03a504,max_instructions=1).instructions[0]
    assert hook.mnem=='addiu' and hook.body=='v1, sp, 0x10'
    original=SOURCE.read_bytes()
    # Check SAVE semantics: RA/S1/S0 occupy upper 12 bytes, never sp+16.
    saved=pypcode.Context('MIPS:LE:32:16e').translate(original[0x3a4cc:0x3a4d0],
              base_address=0xbf03a4cc,max_instructions=1)
    (OUT/'original-status-save.pcode.txt').write_text(str(saved))
    assert str(saved).count('tsp = tsp - 0x4')==3
    assert 'sp = sp - unique' in str(saved) and 'zext(0x20)' in str(saved)
    rng=random.Random(1710)
    colors=[(0,0,0),(255,0,0),(0,255,0),(0,0,255),(255,255,255),(17,34,51)]
    colors += [tuple(rng.randrange(256) for _ in range(3)) for _ in range(256)]
    packet=bytearray(64);packet[:6]=bytes.fromhex('035247420101')
    for rgb in colors:
        packet[6:9]=bytes(rgb)
        m.u.mem_write(0x1fc25000,bytes(0x3000))
        assert m.rx(packet)==0 and m.delegate is None
        assert not m.pwm  # RX never touches PWM or RGB state.
        assert m.native_timer_count==0 and m.writes==[(MAILBOX & 0x1fffffff,4)]
        expected=0x1000000|rgb[0]|rgb[1]<<8|rgb[2]<<16
        assert struct.unpack('<I',m.u.mem_read(MAILBOX & 0x1fffffff,4))[0]==expected
        # Host buffer can change before app processes its copied message.
        m.u.mem_write(0x10100,bytes(64))
        assert m.apply()==0
        assert m.delegate is None and m.pwm==[bytes((rgb[1],rgb[0],rgb[2]))]
        assert m.native_timer_count==1
        assert bytes(m.u.mem_read(MAILBOX & 0x1fffffff,4))==bytes(4)
        assert bytes(m.u.mem_read(0x1fc25355,2))==bytes((0,255))
        assert all(0x27fe0 <= a < 0x28000 or a in
                   (0x1fc26784,0x1fc26785,0x1fc26786,0x1fc25355,0x1fc25356,0x1fc2575c,
                    0x1fc2677c,0x1fc2677d,0x1fc2677e,0x1fc26780)
                   for a,n in m.writes)
        assert m.apply()==0 and not m.pwm and m.native_timer_count==1
    # Every non-RGB SET_REPORT remains delegated with original arguments.
    rejected=0
    for offset in range(6):
        for v in range(256):
            if v==packet[offset]: continue
            if offset==4 and v in (2,3):continue # supported versions, flags default zero
            bad=bytearray(packet);bad[offset]=v
            m.rx(bad)
            assert m.delegate==0xbf03a4cd and not m.writes
            assert m.end_args==[0x10000,0x10010,0x10020]
            rejected+=1
    for kwargs in [dict(value=0x205),dict(value=0x303),dict(length=9),dict(length=63),
                   dict(length=65),dict(actual=0),dict(actual=8),dict(actual=63),dict(actual=65)]:
        m.rx(packet,**kwargs)
        assert m.delegate==0xbf03a4cd and not m.writes
        rejected+=1
    # Native status values cannot impersonate the pending-color marker.
    for _ in range(256):
        m.u.mem_write(MAILBOX & 0x1fffffff,struct.pack('<I',rng.randrange(1<<24)))
        m.apply()
        assert not m.pwm and m.native_timer_count==1
    # Rapid reports coalesce to the most recent complete color.
    packet[6:9]=bytes((1,2,3));m.rx(packet)
    packet[6:9]=bytes((4,5,6));m.rx(packet)
    m.apply();assert m.pwm==[bytes((5,4,6))]
    # An interrupt arriving immediately after unlock remains pending for next tick.
    packet[6:9]=bytes((7,8,9));m.rx(packet)
    m.inject_on_unlock=0x010c0b0a
    m.apply();assert m.pwm==[bytes((8,7,9))]
    assert struct.unpack('<I',m.u.mem_read(MAILBOX & 0x1fffffff,4))[0]==0x010c0b0a
    m.apply();assert m.pwm==[bytes((11,10,12))]
    # Format 0x02: every mode with varied RGB, and complete exact-color pulse
    # cycles. Native cycle callee is stubbed; mode routing/init are checked.
    mode_cases=0;pulse_ticks=0
    for rgb in colors:
        for mode in range(4):
            p=bytearray(64);p[:6]=bytes.fromhex('035247420201')
            p[6:9]=bytes(rgb);p[9]=mode
            m.rx(p)
            assert not m.pwm and not m.init_count
            assert struct.unpack('<I',m.u.mem_read(MAILBOX&0x1fffffff,4))[0]==((mode+1)<<24|rgb[0]|rgb[1]<<8|rgb[2]<<16)
            m.apply();mode_cases+=1
            assert all(0x27fe0<=address<0x28000 or address in
                (0x1fc2575c,0x1fc25355,0x1fc25356,0x1fc2677c,0x1fc2677d,
                 0x1fc2677e,0x1fc26780,0x1fc26784,0x1fc26785,0x1fc26786)
                for address,size in m.writes)
            assert m.native_timer_count==1 and m.init_count==(mode==1)
            assert m.u.mem_read(0x1fc25356,1)==bytes(({0:255,1:1,2:254,3:255}[mode],))
            assert m.u.mem_read(0x1fc25355,1)==bytes(1)
            if mode==0:assert m.pwm==[bytes((rgb[1],rgb[0],rgb[2]))]
            if mode in (1,3):assert m.pwm==[bytes(3)]
            if mode==2:
                for tick in range(65):
                    if tick:m.apply()
                    phase=(tick*4)&255
                    x=phase if phase<128 else 255-phase
                    gain=2*x+((2*x)>>7)
                    expected=bytes(c*gain//255 for c in (rgb[1],rgb[0],rgb[2]))
                    assert m.pwm==[expected],(rgb,tick,m.pwm,expected)
                    assert m.native_timer_count==1
                    pulse_ticks+=1
                assert m.u.mem_read(0x1fc2677c,3)==bytes(rgb)
    # Bad modes neither alter mailbox nor dispatch effects.
    for mode in range(4,256):
        p[9]=mode;m.rx(p)
        assert m.delegate==0xbf03a4cd and not m.writes
        rejected+=1
    # Format 0x01 ignores its reserved mode byte.
    packet[9]=255;m.rx(packet);m.apply()
    assert m.pwm==[bytes((8,7,9))] and m.u.mem_read(0x1fc25356,1)==b'\xff'
    # New mode/color coalesces atomically; a next command arriving after unlock
    # must wait for the next timer tick without changing the current target.
    p[9]=2;m.rx(p)
    m.inject_on_unlock=0x04030201
    m.apply();assert m.u.mem_read(0x1fc25356,1)==b'\xfe'
    m.apply();assert m.pwm==[bytes(3)] and m.u.mem_read(0x1fc25356,1)==b'\xff'
    # Local mode ownership stops the host breathing engine.
    m.u.mem_write(0x1fc25356,b'\x02');m.apply()
    assert not m.pwm and m.native_timer_count==1
    # Only declared ranges may differ, and image length/header remain unchanged.
    assert m.set_count==m.flush_count==0 # all previous volatile/invalid traffic
    persist_cases=0
    for mode in range(4):
        for rgb in colors[:6]:
            saved=Machine()
            p=bytearray(64);p[:6]=bytes.fromhex('035247420301')
            p[6:9]=bytes(rgb);p[9]=mode;p[10]=1
            saved.rx(p)
            assert saved.set_count==saved.flush_count==0 # ISR never saves
            saved.apply()
            assert saved.set_count==saved.flush_count==1
            word=((mode+1)<<24)|rgb[0]|rgb[1]<<8|rgb[2]<<16
            record=struct.pack('<III',RECORD_MAGIC,word,word^0xffffffff)
            assert saved.properties=={b'OPENRGB_V1':record}
            # Same save is a no-op; a volatile update leaves saved default alone.
            saved.rx(p);saved.apply()
            assert saved.set_count==saved.flush_count==1
            p[10]=0;p[6:9]=b'\x09\x08\x07';saved.rx(p);saved.apply()
            assert saved.properties[b'OPENRGB_V1']==record
            cold=Machine();cold.properties=dict(saved.properties)
            cold.run(cold.asm.labels['restore'],[1,0,0])
            assert cold.init_count==1 and cold.set_count==cold.flush_count==0
            assert struct.unpack('<I',cold.u.mem_read(MAILBOX&0x1fffffff,4))[0]==word
            cold.apply()
            assert cold.u.mem_read(0x1fc25356,1)==bytes(({0:255,1:1,2:254,3:255}[mode],))
            # Query is asynchronous: no effect or flash operation in RX.
            q=bytes.fromhex('035247420302123456')+bytes(55)
            cold.rx(q);assert not cold.replies and not cold.pwm
            cold.apply();reply=cold.replies[-1]
            assert len(reply)==64 and reply[:7]==bytes.fromhex('0352474203820f')
            assert reply[16:28]==record and reply[28:31]==bytes.fromhex('123456')
            assert reply[7]=={0:255,1:1,2:254,3:255}[mode]
            assert cold.set_count==cold.flush_count==0
            assert cold.native_timer_count==1
            persist_cases+=1
    # Missing, truncated, corrupted, invalid-mode and error records do not restore.
    bad_records=[None,b'',record[:5],bytes(12)]
    for index in range(12):
        bad=bytearray(record);bad[index]^=1;bad_records.append(bytes(bad))
    for tag in (0,5,0x81,255):
        word=tag<<24|0x112233
        bad_records.append(struct.pack('<III',RECORD_MAGIC,word,word^0xffffffff))
    for bad in bad_records:
        cold=Machine()
        if bad is not None:cold.properties[b'OPENRGB_V1']=bad
        cold.run(cold.asm.labels['restore'],[1,0,0])
        assert cold.u.mem_read(MAILBOX&0x1fffffff,4)==bytes(4)
        assert cold.set_count==cold.flush_count==0
    # Pending host command wins over boot restore.
    cold=Machine();cold.properties[b'OPENRGB_V1']=record
    cold.u.mem_write(MAILBOX&0x1fffffff,struct.pack('<I',0x01010203))
    cold.run(cold.asm.labels['restore'],[1,0,0])
    assert struct.unpack('<I',cold.u.mem_read(MAILBOX&0x1fffffff,4))[0]==0x01010203
    # Failed setter is not flushed; pending live application still updates.
    failed=Machine();failed.property_error=True
    p[10]=1;failed.rx(p);failed.apply()
    assert failed.set_count==1 and failed.flush_count==0 and failed.native_timer_count==1
    # A query cannot displace a pending explicit save command.
    pending=Machine();p[10]=1;pending.rx(p)
    before=bytes(pending.u.mem_read(MAILBOX&0x1fffffff,4))
    pending.rx(q)
    assert pending.delegate==0xbf03a4cd and not pending.writes
    assert pending.u.mem_read(MAILBOX&0x1fffffff,4)==before
    pending.apply();assert pending.set_count==pending.flush_count==1
    for flags in range(2,256):
        p[10]=flags;failed.rx(p)
        assert failed.delegate==0xbf03a4cd and not failed.writes
    # Verify the boot JALX target independently with SLEIGH.
    boot_call=mips16_call(m.asm.labels['restore'],True)
    decoded=pypcode.Context('MIPS:LE:32:16e').disassemble(boot_call,
        base_address=0xbf018da4,max_instructions=1).instructions[0]
    assert decoded.mnem=='jalx' and int(decoded.body,16)==m.asm.labels['restore']
    assert (OUT/'zephyr-rgb.clear.bin').read_bytes()[0x18da4:0x18da8]==boot_call
    from pebble_rgb import make_report
    assert make_report(b'\xff\x00\x00')==bytes.fromhex('035247420301ff00000000')+bytes(53)
    for mode,name in enumerate(('static','cycle','pulse','off')):
        report=make_report(b'\x12\x34\x56',name)
        assert len(report)==64 and report[:11]==bytes.fromhex('035247420301123456')+bytes([mode,0])
        report=make_report(b'\x12\x34\x56',name,True)
        assert len(report)==64 and report[:11]==bytes.fromhex('035247420301123456')+bytes([mode,1])
    from pebble_rgb import query_report,parse_reply
    assert query_report(bytes.fromhex('123456'))==q
    decoded_reply=parse_reply(reply,bytes.fromhex('123456'))
    assert decoded_reply['custom_firmware'] and decoded_reply['saved_record_valid']
    for offset in (0,4,5,6,28):
        bad=bytearray(reply);bad[offset]^=1
        try:parse_reply(bytes(bad),bytes.fromhex('123456'))
        except ValueError:pass
        else:raise AssertionError('Accepted bad identity/nonce')
    manifest=json.loads((OUT/'manifest.json').read_text())
    patched=(OUT/'zephyr-rgb.clear.bin').read_bytes()
    assert len(patched)==len(original) and patched[:48]==original[:48]
    assert patched[CAVE:CAVE+len(m.code)]==m.code
    assert hashlib.sha256(patched).hexdigest()==manifest['clear_sha256']
    declared=set()
    for c in manifest['changes']: declared.update(range(c['offset'],c['offset']+c['length']))
    assert all(i in declared for i,(x,y) in enumerate(zip(original,patched)) if x!=y)
    assert struct.unpack_from('<I',patched,0x4a94c)[0]==m.worker
    assert patched[0x189fa:0x18a00]==original[0x189fa:0x18a00]
    native_status=bytearray(original[0x3a4cc:0x3a538])
    native_status[0x3a504-0x3a4cc:0x3a506-0x3a4cc]=bytes.fromhex('0403')
    assert patched[0x3a4cc:0x3a538]==native_status
    with contextlib.redirect_stdout(io.StringIO()):
        decode=runpy.run_path(str(ROOT/'tools/decode_pebble_payloads.py'))['decode']
    assert decode((OUT/'zephyr-rgb.encoded.bin').read_bytes())==patched
    report=dict(persistence_cases=persist_cases,invalid_restore_records=len(bad_records),
                explicit_save_only=True,deduplication_checked=True,boot_jalx_checked=True,
                query_identity_nonce_saved_record_checked=True,
                valid_rgb_cases=len(colors),valid_mode_color_cases=mode_cases,pulse_ticks_checked=pulse_ticks,
                rejected_wire_cases=rejected,native_status_values_checked=256,
                latest_color_coalescing_checked=True,callee_clobber_checked=True,write_bounds_checked=True,
                usb_has_no_calls_checked=True,irq_restore_checked=True,native_timer_preserved=True,patch_ranges_checked=True,
                interrupt_after_unlock_checked=True,native_status_stack_local_checked=True,
                patched_encoding_roundtrip_checked=True,
                limitation='MIPS16 callees, ISA transitions and returns stubbed; no boot, PWM hardware or live USB tested.')
    (OUT/'offline-tests.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
