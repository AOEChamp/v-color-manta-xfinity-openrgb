"""Same-size firmware FAT member access; no device APIs."""
import struct,hashlib
sha=lambda b:hashlib.sha256(b).hexdigest()
u32=lambda b,p:struct.unpack_from('<I',b,p)[0]
u16=lambda b,p:struct.unpack_from('<H',b,p)[0]

class Image:
    def __init__(self,outer):
        assert outer[:12]==b'100TMFWFSTCA'
        self.outer=outer
        self.length=u32(outer,12)
        self.data=outer[16:16+self.length]
        assert self.data[:11]==b'ACTS-FWT001'
        self.sector=u16(self.data,11)
        self.cluster_size=self.sector*self.data[13]
        self.fat_start=u16(self.data,14)*self.sector
        self.data_start=self.fat_start+self.data[16]*u32(self.data,36)*self.sector
        self.root=u32(self.data,44)
        assert self.sector==512 and self.cluster_size==4096
    def offset(self,cluster): return self.data_start+(cluster-2)*self.cluster_size
    def chain(self,cluster):
        seen=set()
        while 2<=cluster<0xffffff8:
            assert cluster not in seen and cluster!=0xffffff7
            seen.add(cluster)
            yield cluster
            cluster=u32(self.data,self.fat_start+4*cluster)&0xfffffff
        assert cluster>=0xffffff8
    def entry(self,shortname):
        found=[]
        for cluster in self.chain(self.root):
            start=self.offset(cluster)
            for off in range(start,start+self.cluster_size,32):
                d=self.data[off:off+32]
                if d[:11]!=shortname or d[0] in (0,0xe5) or d[11]==15:continue
                first=u16(d,26)|(u16(d,20)<<16)
                size=u32(d,28)
                chain=list(self.chain(first))
                assert len(chain)*self.cluster_size>=size
                found.append(dict(directory_offset=off,first_cluster=first,size=size,clusters=chain))
        assert len(found)==1,found
        return found[0]
    def extract_xor(self,entry):
        b=b''.join(self.data[self.offset(c):self.offset(c)+self.cluster_size] for c in entry['clusters'])
        return bytes(x^0x38 for x in b[:entry['size']])
    def replace_xor(self,entry,content):
        assert len(content)==entry['size']
        result=bytearray(self.outer)
        for i,c in enumerate(entry['clusters']):
            part=content[i*self.cluster_size:(i+1)*self.cluster_size]
            pos=16+self.offset(c)
            result[pos:pos+len(part)]=bytes(x^0x38 for x in part)
        return bytes(result)
