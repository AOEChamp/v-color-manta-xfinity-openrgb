"""Execute the supplied MIPS16 boot selector against synthetic flash contents.

ROM service and peripheral routines are stubbed; selection, header checks and
both parameter CRC validations execute the actual supplied bootloader bytes.
Does not read the device or establish its recovery button/ROM behavior.
"""
from pathlib import Path
import json
import struct
import sys
import zlib
ROOT=Path(__file__).resolve().parents[1]
import unicorn
from unicorn.mips_const import *
E=ROOT/'build'
BOOT=(E/'clear/mbrec.bin').read_bytes()
PARAM=(E/'clear/param.bin').read_bytes()
APP=(E/'clear/zephyr.bin').read_bytes()
CANDIDATE_PATH=Path(sys.argv[1]) if len(sys.argv)>1 else E/'patched-v1/zephyr-rgb.clear.bin'
CANDIDATE=CANDIDATE_PATH.read_bytes()
REGS=[UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3]
phys=lambda address:address & 0x1fffffff if 0x80000000<=address<0xc0000000 else address

class Boot:
    def __init__(self,primary=CANDIDATE,secondary=APP,param0=PARAM,param1=PARAM,recovery=False):
        self.u=unicorn.Uc(unicorn.UC_ARCH_MIPS,unicorn.UC_MODE_MIPS32|unicorn.UC_MODE_LITTLE_ENDIAN)
        self.u.mem_map(0x1fc20000,0x20000)
        self.u.mem_write(0x1fc38000,BOOT)
        self.u.mem_map(0x10000,0x40000)
        self.u.mem_map(0x1e000000,0x200000)
        self.u.mem_map(0x1f000000,0x200000)
        self.flash={0x1000:param0,0x3000:param1,0x4000:primary,0xfe000:secondary}
        self.recovery=recovery;self.outcome=None;self.mappings=[];self.messages=[];self.steps=0
        self.u.hook_add(unicorn.UC_HOOK_CODE,self.hook)
    def read(self,address,n):return bytes(self.u.mem_read(phys(address),n))
    def write(self,address,b):self.u.mem_write(phys(address),bytes(b))
    def ret(self,v=0):
        self.u.reg_write(UC_MIPS_REG_V0,v & 0xffffffff)
        self.u.reg_write(UC_MIPS_REG_PC,self.u.reg_read(UC_MIPS_REG_RA))
    def hook(self,u,pc,size,user):
        self.steps+=1
        args=[u.reg_read(r) for r in REGS]
        if pc==0xbfc385c8:
            self.outcome='adfu';u.emu_stop()
        elif pc==0xbf000030:
            self.outcome='application';u.emu_stop()
        elif pc==0x40000:
            self.outcome='returned';u.emu_stop()
        elif pc==0xbfc38604:
            slot,offset,address,encrypted=args
            assert offset in self.flash,(hex(offset),self.mappings)
            self.write(address,self.flash[offset])
            self.mappings.append(dict(slot=slot,flash_offset=offset,address=address,encrypted=encrypted))
            self.ret(1)
        elif pc==0xbfc38b84:
            self.write(args[0],bytes([args[1]&255])*args[2]);self.ret(args[0])
        elif pc==0xbfc38b98:
            self.write(args[0],self.read(args[1],args[2]));self.ret(args[0])
        elif pc==0xbfc38b5c:self.ret(1) # expected encrypted-XIP configuration
        elif pc==0xbfc38bac:
            assert args[0]==5
            self.ret(int(self.recovery))
        elif pc==0xbfc38bf8:
            raw=self.read(args[0],min(100,0x100000000-args[0])).split(b'\0')[0]
            self.messages.append(raw.decode('ascii',errors='replace'));self.ret(0)
        elif pc in (0xbfc38a5c,0xbfc38a74,0xbfc38c64,0xbfc38b38,
                    0xbfc389fc,0xbfc38c30,0xbfc38c40,0xbfc38be0):self.ret(0)
    def run(self,entry=0xbfc38751,args=(1,0,0,0),limit=400000):
        self.u.reg_write(UC_MIPS_REG_SP,0x48000)
        self.u.reg_write(UC_MIPS_REG_RA,0x40000)
        for reg,value in zip(REGS,args):self.u.reg_write(reg,value)
        self.u.emu_start(entry,0,count=limit)
        assert self.outcome is not None,('limit',self.steps)
        assert self.u.reg_read(UC_MIPS_REG_SP)<=0x48000
        return dict(outcome=self.outcome,steps=self.steps,mappings=self.mappings,messages=self.messages)

def corrupt(data,offset):
    result=bytearray(data);result[offset]^=1;return bytes(result)

def main():
    # Native nibble-table CRC implementation must agree with an independent CRC.
    crc_cases=[]
    for data in (b'',b'123456789',PARAM[:0x17c],PARAM[0x180:0x1fc]):
        b=Boot();b.write(0x10000,data)
        b.run(0xbfc38961,(0x10000,len(data),0,0))
        got=b.u.reg_read(UC_MIPS_REG_V0)
        assert got==zlib.crc32(data)
        crc_cases.append(dict(length=len(data),crc32=got))
    cases={
        'stock_primary':dict(primary=APP),
        'patched_primary':dict(),
        'primary_bad_magic_secondary_valid':dict(primary=corrupt(CANDIDATE,0)),
        'both_app_headers_invalid':dict(primary=corrupt(CANDIDATE,0),secondary=corrupt(APP,0)),
        'primary_param_bad_crc_secondary_valid':dict(param0=corrupt(PARAM,24)),
        'both_param_copies_bad_crc':dict(param0=corrupt(PARAM,24),param1=corrupt(PARAM,24)),
        'hardware_recovery_condition':dict(recovery=True),
        'body_corrupted_magic_intact':dict(primary=corrupt(CANDIDATE,0x8000)),
    }
    results={}
    for name,args in cases.items():
        result=Boot(**args).run();results[name]=result
        expected='adfu' if name in ('both_app_headers_invalid','both_param_copies_bad_crc','hardware_recovery_condition') else 'application'
        assert result['outcome']==expected,(name,result)
    primary_offsets=[m['flash_offset'] for m in results['patched_primary']['mappings']]
    backup_offsets=[m['flash_offset'] for m in results['primary_bad_magic_secondary_valid']['mappings']]
    assert primary_offsets[-1]==0x4000 and backup_offsets[-1]==0xfe000
    report=dict(crc_cases=crc_cases,boot_cases=results,
        actual_bootloader_code_executed=True,
        limitations=['Synthetic flash slots, not read from the device.',
          'ROM API/peripheral behavior stubbed; flash encryption configuration assumed.',
          'Application execution stops at its entry; a subsequent hang is not detected here.',
          'Recovery GPIO-to-button mapping and live ADFU operation unverified.',
          'Bootloader initial ROM authentication/load stage not emulated.'])
    (CANDIDATE_PATH.parent/'boot-emulation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({n:r['outcome'] for n,r in results.items()},indent=2))

if __name__=='__main__':main()
