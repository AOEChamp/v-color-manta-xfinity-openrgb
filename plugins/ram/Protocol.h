// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <array>
#include <cstdint>
#include <stdexcept>
#include <vector>
namespace VColor {
struct Mode {const char* name;uint8_t value;bool colors,animated;};
inline constexpr Mode modes[]={
 {"Direct",1,true,false},{"Static",1,true,false},{"Off",0,false,false},
 {"Breathing",2,true,true},{"Flashing",3,true,true},{"Spectrum Cycle",4,false,true},
 {"Rainbow",5,false,true},{"Chase Fade",7,true,true},{"Chase Fade Rainbow",8,false,true},
 {"Chase",9,true,true},{"Chase Rainbow",10,false,true},{"Random Flicker",13,true,true},
 {"Stack",14,false,true},{"Pong",15,false,true},{"Fill Up",16,false,true}};
using Colors=std::array<uint32_t,8>;
template<class Bus> void Apply(Bus& bus,unsigned address,const Colors& colors,unsigned mode,unsigned speed,bool save){
 if(address<0x70||address>0x73||mode>=15||speed>4||(!modes[mode].animated&&speed))
   throw std::invalid_argument("Invalid DIMM address, mode or speed");
 std::vector<uint8_t> frame;
 for(auto color:colors){frame.push_back(mode==2?0:color&255);frame.push_back(mode==2?0:(color>>16)&255);frame.push_back(mode==2?0:(color>>8)&255);}
 bus.Block(address,0xE300,frame);
 bus.Block(address,0xE020,{0,uint8_t(mode==2?1:modes[mode].value),uint8_t(speed),0});
 bus.Write(address,0xE02F,1);
 if(save)bus.Write(address,0xE0A0,0xAA);
}
}
