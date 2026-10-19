// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "Protocol.h"
#include <Windows.h>
#include <hidsdi.h>
#include <hidapi.h>
#include <QCoreApplication>
#include <QLibrary>
#include <QString>
#include <chrono>
#include <mutex>
#include <random>
#include <string>
#include <thread>
#include <vector>

namespace Pebble {
class HidApi {
    QLibrary library;
    template<typename T> T symbol(const char* name) {
        auto p=library.resolve(name);
        if(!p)throw std::runtime_error(std::string("Missing HID API: ")+name);
        return reinterpret_cast<T>(p);
    }
public:
    decltype(&hid_enumerate) enumerate;
    decltype(&hid_free_enumeration) free_enumeration;
    decltype(&hid_open_path) open_path;
    decltype(&hid_close) close;
    decltype(&hid_read_timeout) read_timeout;
    HidApi():library(QCoreApplication::applicationDirPath()+"/hidapi-hotplug.dll") {
        if(!library.load())throw std::runtime_error(library.errorString().toStdString());
        enumerate=symbol<decltype(enumerate)>("hid_enumerate");
        free_enumeration=symbol<decltype(free_enumeration)>("hid_free_enumeration");
        open_path=symbol<decltype(open_path)>("hid_open_path");
        close=symbol<decltype(close)>("hid_close");
        read_timeout=symbol<decltype(read_timeout)>("hid_read_timeout");
    }
    std::vector<std::string> Paths() {
        std::vector<std::string> paths;
        auto head=enumerate(0x041e,0x3287);
        for(auto p=head;p;p=p->next)
            if(p->interface_number==0&&p->usage_page==1&&p->usage==0)paths.emplace_back(p->path);
        free_enumeration(head);return paths;
    }
};

class Transport {
    HidApi& api;
    hid_device* input=nullptr;
    HANDLE output=INVALID_HANDLE_VALUE;
    std::mt19937 random{std::random_device{}()};
    bool have_last=false;
    unsigned last_mode=0;
    uint32_t last_color=0;
    void Open() {
        input=api.open_path(path.c_str());
        if(!input)throw std::runtime_error("Cannot open Pebble HID input");
        output=CreateFileW(QString::fromStdString(path).toStdWString().c_str(),
            GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,OPEN_EXISTING,0,nullptr);
        if(output==INVALID_HANDLE_VALUE){api.close(input);input=nullptr;throw std::runtime_error("Cannot open Pebble control handle");}
    }
    void Send(const Report& report) {
        if(!HidD_SetOutputReport(output,const_cast<unsigned char*>(report.data()),64))
            throw std::runtime_error("Pebble control transfer failed (busy or disconnected), Windows error "+std::to_string(GetLastError()));
    }
public:
    std::mutex mutex;
    const std::string path;
    Transport(HidApi& api_,const std::string& path_):api(api_),path(path_) {
        // Open input before querying so the reply cannot be discarded.
        Open();
    }
    ~Transport(){if(output!=INVALID_HANDLE_VALUE)CloseHandle(output);if(input)api.close(input);}
    void Reopen() {
        if(output!=INVALID_HANDLE_VALUE){CloseHandle(output);output=INVALID_HANDLE_VALUE;}
        if(input){api.close(input);input=nullptr;}
        have_last=false;Open();
    }
    // Caller holds mutex for all I/O, including a complete save/query sequence.
    State Read() {
        if(!input||output==INVALID_HANDLE_VALUE)throw std::runtime_error("Pebble is disconnected");
        std::string error="No custom firmware reply";
        for(int attempt=0;attempt<6;++attempt) {
            uint32_t nonce=random()&0xffffff;
            try {
                Report discarded{};
                for(int n=0;n<64&&api.read_timeout(input,discarded.data(),64,0)>0;++n){}
                Send(Query(nonce));
                for(int packet=0;packet<4;++packet) {
                    Report reply{};int count=api.read_timeout(input,reply.data(),64,250);
                    if(count<0)throw std::runtime_error("Pebble HID read failed");
                    if(count==0)break;
                    if(count==64){try{
                        State s=Parse(reply,nonce);
                        if(have_last) {
                            unsigned raw=last_mode==1?1:last_mode==2?254:255;
                            if(s.raw_mode!=raw||(s.target_valid&&s.target!=last_color))have_last=false;
                        }
                        return s;
                    }catch(const std::exception& e){error=e.what();}}
                }
            }catch(const std::exception& e){error=e.what();}
            std::this_thread::sleep_for(std::chrono::milliseconds(40));
        }
        throw std::runtime_error(error);
    }
    void Apply(unsigned mode,uint32_t rgb,bool save) {
        if(mode==1||mode==3)rgb=0; // These modes ignore color.
        rgb&=0xffffff;
        if(!save&&have_last&&mode==last_mode&&rgb==last_color)return;
        Send(Set(mode,rgb,save));have_last=true;last_mode=mode;last_color=rgb;
        if(save) {
            // Prevent another local update from replacing the pending save.
            State state=Read();
            if(!state.saved_valid||state.saved_mode!=mode||state.saved_color!=rgb)
                throw std::runtime_error("Saved setting read-back differs; retry Save to Device");
        }
    }
};
}
