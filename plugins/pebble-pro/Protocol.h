// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <array>
#include <cstdint>
#include <stdexcept>

namespace Pebble {
using Report=std::array<unsigned char,64>;
struct State {
    unsigned char raw_mode=0;
    uint32_t output=0,target=0,saved_color=0;
    bool target_valid=false,saved_valid=false;
    unsigned char saved_mode=0;
};
inline uint32_t Word(const Report& r,size_t i) {
    return uint32_t(r[i])|uint32_t(r[i+1])<<8|uint32_t(r[i+2])<<16|uint32_t(r[i+3])<<24;
}
inline Report Set(unsigned mode,uint32_t rgb,bool save=false) {
    if(mode>3)throw std::invalid_argument("Invalid Pebble mode");
    Report r{};r[0]=3;r[1]='R';r[2]='G';r[3]='B';r[4]=3;r[5]=1;
    r[6]=static_cast<unsigned char>(rgb);r[7]=static_cast<unsigned char>(rgb>>8);
    r[8]=static_cast<unsigned char>(rgb>>16);r[9]=static_cast<unsigned char>(mode);r[10]=save;
    return r;
}
inline Report Query(uint32_t nonce) {
    Report r=Set(0,nonce);r[5]=2;return r;
}
inline State Parse(const Report& r,uint32_t nonce) {
    if(r[0]!=3||r[1]!='R'||r[2]!='G'||r[3]!='B'||r[4]!=3||r[5]!=0x82||r[6]!=15||
       (Word(r,28)&0xffffff)!=(nonce&0xffffff))
        throw std::runtime_error("Not Pebble patched v1 firmware (or stale reply)");
    State s;s.raw_mode=r[7];s.output=Word(r,8)&0xffffff;s.target=Word(r,12)&0xffffff;
    s.target_valid=s.raw_mode==254||s.raw_mode==255;
    uint32_t word=Word(r,20);
    s.saved_valid=Word(r,16)==0x33504752&&Word(r,24)==~word&&(word>>24)>=1&&(word>>24)<=4;
    if(s.saved_valid){s.saved_mode=(word>>24)-1;s.saved_color=word&0xffffff;}
    return s;
}
}
