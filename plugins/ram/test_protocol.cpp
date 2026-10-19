// SPDX-License-Identifier: GPL-2.0-or-later
#include "Protocol.h"
#include <cassert>
#include <iostream>
struct Event{unsigned address,reg;std::vector<uint8_t> data;};
struct Bus{
 std::vector<Event> events;int fail=-1;
 void Block(unsigned address,unsigned reg,const std::vector<uint8_t>& data){
  if(int(events.size())==fail)throw std::runtime_error("simulated bus failure");
  events.push_back({address,reg,data});
 }
 void Write(unsigned a,unsigned r,uint8_t v){Block(a,r,{v});}
};
int main(){
 VColor::Colors colors{0x332211,0x665544,0x998877,0xCCBBAA,0xFFEEDD,0,0xFFFFFF,0x030201};
 for(unsigned m=0;m<15;++m)for(unsigned speed=0;speed<5;++speed){
  Bus b;bool valid=VColor::modes[m].animated||speed==0;
  try{VColor::Apply(b,0x73,colors,m,speed,true);assert(valid);}catch(const std::invalid_argument&){assert(!valid);assert(b.events.empty());continue;}
  assert(b.events.size()==4);assert(b.events[0].address==0x73);assert(b.events[0].reg==0xE300);
  if(m==2)assert(b.events[0].data==std::vector<uint8_t>(24));
  else assert(b.events[0].data==std::vector<uint8_t>({0x11,0x33,0x22,0x44,0x66,0x55,0x77,0x99,0x88,0xAA,0xCC,0xBB,0xDD,0xFF,0xEE,0,0,0,255,255,255,1,3,2}));
  assert(b.events[1].reg==0xE020);assert(b.events[1].data==std::vector<uint8_t>({0,uint8_t(m==2?1:VColor::modes[m].value),uint8_t(speed),0}));
  assert(b.events[2].reg==0xE02F&&b.events[2].data[0]==1);
  assert(b.events[3].reg==0xE0A0&&b.events[3].data[0]==0xAA);
 }
 for(int failure=0;failure<4;++failure){Bus b;b.fail=failure;try{VColor::Apply(b,0x71,colors,1,0,true);assert(false);}catch(const std::runtime_error&){}assert(int(b.events.size())==failure);for(auto& e:b.events)assert(e.reg!=0xE0A0);}
 Bus b;VColor::Apply(b,0x71,colors,1,0,false);assert(b.events.size()==3);
 for(unsigned m:{15u,0xFFFFFFFFu}){Bus invalid;try{VColor::Apply(invalid,0x71,colors,m,0,true);assert(false);}catch(const std::invalid_argument&){}assert(invalid.events.empty());}
 std::cout<<"Protocol tests passed: all modes/speeds, RBG order, Off, explicit save, failures before save.\n";
}
