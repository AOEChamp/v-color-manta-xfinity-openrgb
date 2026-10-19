// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <windows.h>
#include <QCoreApplication>
#include <QFile>
#include <QLibrary>
#include <mutex>
#include <cstring>
#include "Protocol.h"
namespace VColor {
class PawnBus {
 QLibrary dll;
 HANDLE handle=nullptr,mutex=nullptr;
 std::mutex local;
 using Open=HRESULT(WINAPI*)(PHANDLE);
 using Load=HRESULT(WINAPI*)(HANDLE,const UCHAR*,SIZE_T);
 using Execute=HRESULT(WINAPI*)(HANDLE,PCSTR,const ULONG64*,SIZE_T,PULONG64,SIZE_T,PSIZE_T);
 using Close=HRESULT(WINAPI*)(HANDLE);
 Execute execute=nullptr;Close close=nullptr;
 static void Check(HRESULT result){if(result)throw std::runtime_error("PawnIO failure 0x"+QString::number(uint32_t(result),16).toStdString()+"; run OpenRGB as administrator with PawnIO installed");}
 void Exec(const char* name,const std::vector<ULONG64>& input,ULONG64* output,SIZE_T count){SIZE_T used=0;Check(execute(handle,name,input.data(),input.size(),output,count,&used));}
 ULONG64 Transfer(unsigned address,unsigned read,unsigned command,unsigned size,ULONG64 value=0){ULONG64 output[5]{};Exec("ioctl_smbus_xfer",{address,read,command,size,value,0,0,0,0},output,5);return output[0];}
 void Select(unsigned address,unsigned reg){Transfer(address,0,0,3,((reg&255)<<8)|(reg>>8));}
 void Cleanup(){if(handle&&close)close(handle);handle=nullptr;if(mutex)CloseHandle(mutex);mutex=nullptr;}
public:
 PawnBus():dll(QCoreApplication::applicationDirPath()+"/PawnIOLib.dll"){
  try{
   if(!dll.load())throw std::runtime_error(dll.errorString().toStdString());
   auto open=reinterpret_cast<Open>(dll.resolve("pawnio_open"));
   auto load=reinterpret_cast<Load>(dll.resolve("pawnio_load"));
   execute=reinterpret_cast<Execute>(dll.resolve("pawnio_execute"));close=reinterpret_cast<Close>(dll.resolve("pawnio_close"));
   if(!open||!load||!execute||!close)throw std::runtime_error("PawnIOLib exports missing");
   mutex=CreateMutexExW(nullptr,L"Global\\Access_SMBUS.HTP.Method",0,SYNCHRONIZE|MUTEX_MODIFY_STATE);
   if(!mutex)throw std::runtime_error("Cannot open OpenRGB SMBus mutex");
   Check(open(&handle));QFile file(QCoreApplication::applicationDirPath()+"/SmbusPIIX4.bin");
   if(!file.open(QIODevice::ReadOnly))throw std::runtime_error("SmbusPIIX4.bin missing");
   auto blob=file.readAll();Check(load(handle,reinterpret_cast<const UCHAR*>(blob.constData()),blob.size()));
  }catch(...){Cleanup();throw;}
 }
 ~PawnBus(){Cleanup();}
 template<class F> auto Transaction(F action)->decltype(action()){
  std::lock_guard<std::mutex> lock(local);
  auto result=WaitForSingleObject(mutex,3000);
  if(result!=WAIT_OBJECT_0&&result!=WAIT_ABANDONED)throw std::runtime_error("SMBus mutex unavailable");
  struct Guard{HANDLE h;~Guard(){ReleaseMutex(h);}} guard{mutex};
  ULONG64 output[1]{};Exec("ioctl_piix4_port_sel",{0},output,1);
  return action();
 }
 std::vector<uint8_t> Read(unsigned address,unsigned reg,unsigned count){Select(address,reg);std::vector<uint8_t> data;while(count--)data.push_back(uint8_t(Transfer(address,1,0x81,2)));return data;}
 void Block(unsigned address,unsigned reg,const std::vector<uint8_t>& data){
  if(data.empty()||data.size()>32)throw std::invalid_argument("Invalid block size");
  Select(address,reg);uint8_t raw[40]{};raw[0]=uint8_t(data.size());std::memcpy(raw+1,data.data(),data.size());
  std::vector<ULONG64> input={address,0,3,5};for(unsigned i=0;i<40;i+=8){ULONG64 word;std::memcpy(&word,raw+i,8);input.push_back(word);}
  ULONG64 output[5]{};Exec("ioctl_smbus_xfer",input,output,5);
 }
 void Write(unsigned address,unsigned reg,uint8_t value){Select(address,reg);Transfer(address,0,1,2,value);}
};
}
