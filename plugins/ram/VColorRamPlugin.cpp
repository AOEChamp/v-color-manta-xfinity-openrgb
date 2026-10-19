// SPDX-License-Identifier: GPL-2.0-or-later
#include "VColorRamPlugin.h"
#include <QPushButton>
#include <QVBoxLayout>
#include <QMetaObject>
#include <QEventLoop>
#include <QThread>
#include <tlhelp32.h>

OpenRGBPluginInfo VColorRamPlugin::GetPluginInfo() {
    OpenRGBPluginInfo info{};
    info.Name="V-Color Manta XFinity RAM";info.Version="0.1.0";info.Commit="native-pawnio";
    info.Description="Eight LEDs per DIMM, hardware effects and explicit Save to Device through PawnIO.";
    info.Location=OPENRGB_PLUGIN_LOCATION_SETTINGS;info.Label="V-Color RAM";return info;
}

void VColorRamPlugin::Message(const std::string& message,bool error) {
    if(api)api->LogEntry(__FILE__,__LINE__,error?1:3,"[V-Color RAM] %s",message.c_str());
    QMetaObject::invokeMethod(this,[this,text=QString::fromStdString(message)]{
        if(status)status->setText(text);
    },Qt::QueuedConnection);
}

static bool BridgeRunning() {
    HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    if(snapshot==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot check for the RAM bridge");
    PROCESSENTRY32W entry{};entry.dwSize=sizeof(entry);bool found=false;
    if(Process32FirstW(snapshot,&entry))do{if(!_wcsicmp(entry.szExeFile,L"VColorOpenRGBBridge.exe")){found=true;break;}}while(Process32NextW(snapshot,&entry));
    CloseHandle(snapshot);return found;
}
void VColorRamPlugin::Load(OpenRGBPluginAPIInterface* plugin_api) {
    api=plugin_api;stopping=false;Scan();
}
QWidget* VColorRamPlugin::GetWidget() {
    if(widget)return widget;
    widget=new QWidget;auto layout=new QVBoxLayout(widget);
    auto help=new QLabel("Eight LEDs per DIMM and 15 lighting modes. Select a RAM device in Devices.\n"
        "Save to Device requires the previously patched DIMM firmware. Ordinary updates remain volatile.\n"
        "Run the desktop app as administrator. Stop the V-Color bridge before scanning.");
    help->setWordWrap(true);layout->addWidget(help);
    status=new QLabel("Use Rescan to check RAM status.");status->setWordWrap(true);layout->addWidget(status);
    auto rescan=new QPushButton("Rescan RAM");layout->addWidget(rescan);
    connect(rescan,&QPushButton::clicked,this,[this]{Scan();});layout->addStretch();return widget;
}

void VColorRamPlugin::Scan() {
    if(stopping||scanning.exchange(true))return;
    if(scan_thread.joinable())scan_thread.join();
    scan_thread=std::thread([this]{
        try{Discover();}catch(const std::exception& e){Message(e.what(),true);}
        scanning=false;
    });
}

void VColorRamPlugin::Discover() {
    if(BridgeRunning())throw std::runtime_error("Stop VColorOpenRGBBridge before using the native RAM plugin");
    if(!bus)bus=std::make_unique<VColor::PawnBus>();
    for(unsigned address=0x70;address<=0x73;++address){
        if(stopping)return;
        bool known=false;for(const auto& d:devices)if(d->address==address)known=true;
        if(known)continue;
        try{
            VColor::Colors colors{};std::vector<uint8_t> control;
            bus->Transaction([&]{
                if(bus->Read(address,0xB500,5)!=std::vector<uint8_t>{0xA8,0x32,0x16,0xE8,0x8C})
                    throw std::runtime_error("ENE signature mismatch");
                auto frame=bus->Read(address,0xE300,24);control=bus->Read(address,0xE020,4);
                for(unsigned i=0;i<8;++i)colors[i]=frame[i*3]|(uint32_t(frame[i*3+2])<<8)|(uint32_t(frame[i*3+1])<<16);
            });
            auto d=std::make_unique<Device>();d->plugin=this;d->address=address;
            RGBController_Setup setup{};
            auto hex=QString::number(address,16).toStdString();
            setup.name="V-Color Manta XFinity (0x"+hex+")";setup.vendor="V-Color";
            setup.description="ENE Aura 6; eight individually addressable LEDs";
            setup.version="A8 32 16 E8 8C";setup.serial="PIIX4:0:"+hex;
            setup.location="SMBus: AMD PIIX4 port 0, address 0x"+hex;
            setup.type=DEVICE_TYPE_DRAM;setup.flags=CONTROLLER_FLAG_VIRTUAL;setup.active_mode=1;
            for(unsigned i=0;i<15;++i){
                const auto& spec=VColor::modes[i];mode m;m.name=spec.name;m.value=spec.value;
                m.flags=MODE_FLAG_MANUAL_SAVE;
                if(spec.colors){m.flags|=MODE_FLAG_HAS_PER_LED_COLOR;m.color_mode=MODE_COLORS_PER_LED;}
                if(spec.animated){m.flags|=MODE_FLAG_HAS_SPEED;m.speed_min=4;m.speed_max=0;m.speed=2;
                    if(spec.value==control[1]){setup.active_mode=i;if(control[2]<=4)m.speed=control[2];}}
                setup.modes.push_back(m);
            }
            zone z;z.name="DIMM LEDs";z.type=ZONE_TYPE_LINEAR;z.leds_count=z.leds_min=z.leds_max=8;setup.zones.push_back(z);
            for(unsigned i=0;i<8;++i){led l;l.name="LED "+std::to_string(i+1);l.value=i;setup.leds.push_back(l);}
            setup.object_ptr=d.get();setup.DeviceUpdateLEDs=&Update;setup.DeviceUpdateZoneLEDs=&UpdateZone;
            setup.DeviceUpdateSingleLED=&UpdateZone;setup.DeviceUpdateMode=&Update;setup.DeviceSaveMode=&Save;
            d->controller=api->CreateVirtualRGBController(&setup);
            if(!d->controller)throw std::runtime_error("OpenRGB did not create the RAM controller");
            for(unsigned i=0;i<8;++i)d->controller->SetColor(i,colors[i]);
            Device* registered=d.get();devices.push_back(std::move(d));
            api->RegisterVirtualRGBController(registered->controller);registered->initializing=false;
        }catch(const std::exception& e){
            if(api)api->LogEntry(__FILE__,__LINE__,4,"[V-Color RAM] Address 0x%02X skipped: %s",address,e.what());
        }
    }
    Message("Found "+std::to_string(devices.size())+" compatible DIMMs. Discovery preserves lighting.");
}
void VColorRamPlugin::Device::Apply(bool save) {
    if(plugin->stopping)return;
    std::lock_guard<std::mutex> lock(lifecycle);
    if(initializing||plugin->stopping||!controller)return;
    try{
        if(BridgeRunning())throw std::runtime_error("RAM bridge is running; native writes blocked");
        VColor::Colors colors{};for(unsigned i=0;i<8;++i)colors[i]=controller->GetColor(i);
        unsigned selected=controller->GetActiveMode();
        if(selected>=15)throw std::runtime_error("Invalid lighting mode");
        unsigned speed=VColor::modes[selected].animated?controller->GetModeSpeed(selected):0;
        plugin->bus->Transaction([&]{VColor::Apply(*plugin->bus,address,colors,selected,speed,save);});
        if(save)plugin->Message("Save command sent to DIMM. Persistent saves require patched E000 firmware.");
    }catch(const std::exception& e){plugin->Message(e.what(),true);}
}

void VColorRamPlugin::Unload() {
    if(stopping.exchange(true))return;
    if(scan_thread.joinable()) {
        // Registration can be waiting for the GUI's device-list notification.
        // Drain queued events while stopping instead of deadlocking its join.
        if(QCoreApplication::instance()&&QThread::currentThread()==QCoreApplication::instance()->thread())
            while(scanning){QCoreApplication::processEvents(QEventLoop::ExcludeUserInputEvents,20);QThread::msleep(1);}
        scan_thread.join();
    }
    if(api)for(auto& d:devices)if(d->controller) {
        api->UnregisterVirtualRGBController(d->controller);
        {std::lock_guard<std::mutex> lifecycle_lock(d->lifecycle);d->initializing=true;}
        // Do not hold our callback mutex while the host joins its device thread.
        api->DeleteVirtualRGBController(d->controller);
        d->controller=nullptr;
    }
    devices.clear();bus.reset();api=nullptr;
}
