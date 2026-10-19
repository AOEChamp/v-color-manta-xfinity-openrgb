// SPDX-License-Identifier: GPL-2.0-or-later
#include "Protocol.h"
#include <cassert>
#include <iostream>
int main() {
    using namespace Pebble;
    for(unsigned m=0;m<4;++m)for(uint32_t color:{0u,0xffu,0xff00u,0xff0000u,0xffffffu,0x563412u}) {
        auto r=Set(m,color,true);
        assert(r[0]==3&&r[4]==3&&r[5]==1&&r[9]==m&&r[10]==1);
        assert((Word(r,6)&0xffffff)==color);
        for(size_t i=11;i<64;++i)assert(r[i]==0);
        Report reply{};reply[0]=3;reply[1]='R';reply[2]='G';reply[3]='B';reply[4]=3;reply[5]=0x82;reply[6]=15;
        reply[7]=254;reply[8]=0x12;reply[12]=0xff;reply[28]=0x56;reply[29]=0x34;reply[30]=0x12;
        auto put=[&](size_t offset,uint32_t w){for(unsigned j=0;j<4;++j)reply[offset+j]=static_cast<unsigned char>(w>>(8*j));};
        uint32_t w=(m+1)<<24|color;put(16,0x33504752);put(20,w);put(24,~w);
        auto state=Parse(reply,0x123456);
        assert(state.saved_valid&&state.saved_mode==m&&state.saved_color==color&&state.target==255&&state.target_valid);
        for(size_t offset:{0u,4u,5u,6u,28u}){
            auto bad=reply;bad[offset]^=1;bool rejected=false;
            try{Parse(bad,0x123456);}catch(const std::runtime_error&){rejected=true;}assert(rejected);
        }
        reply[24]^=1;assert(!Parse(reply,0x123456).saved_valid);
    }
    assert(Query(0x123456)[5]==2&&Query(0x123456)[6]==0x56);
    std::cout<<"PASS protocol mode/color/save packets, nonce/identity and corrupt saved records\n";
}
