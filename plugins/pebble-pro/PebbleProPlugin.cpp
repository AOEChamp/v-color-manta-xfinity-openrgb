// SPDX-License-Identifier: GPL-2.0-or-later
#include "PebbleProPlugin.h"
#include <QPushButton>
#include <QVBoxLayout>
#include <QMetaObject>
#include <QEventLoop>
#include <QThread>

OpenRGBPluginInfo PebbleProPlugin::GetPluginInfo() {
    OpenRGBPluginInfo info{};
    info.Name="Creative Pebble Pro";info.Version="0.1.0";info.Commit="patched-v1";
    info.Description="Mode, color and Save to Device for Pebble Pro patched v1 firmware. Both rings share one zone.";
    info.Location=OPENRGB_PLUGIN_LOCATION_SETTINGS;info.Label="Pebble Pro";
    info.ProtocolVersion=0;return info;
}

void PebbleProPlugin::Message(const std::string& message,bool error) {
    if(api)api->LogEntry(__FILE__,__LINE__,error?1:3,"[Pebble Pro] %s",message.c_str());
    QMetaObject::invokeMethod(this,[this,text=QString::fromStdString(message)]{
        if(status)status->setText(text);
    },Qt::QueuedConnection);
}

void PebbleProPlugin::Load(OpenRGBPluginAPIInterface* plugin_api) {
    api=plugin_api;stopping=false;
    try{hid=std::make_unique<Pebble::HidApi>();}
    catch(const std::exception& e){Message(e.what(),true);return;}
    scan_timer=new QTimer(this);
    connect(scan_timer,&QTimer::timeout,this,[this]{Scan();});
    scan_timer->start(5000);
    Scan();
}

QWidget* PebbleProPlugin::GetWidget() {
    if(widget)return widget;
    widget=new QWidget;
    auto layout=new QVBoxLayout(widget);
    auto help=new QLabel("Both speaker rings share one color and mode. Select the device in Devices to control lighting.\n"
        "Save to Device stores the current mode/color as the power-on default. Ordinary updates and profiles stay volatile.\n"
        "Requires Pebble Pro patched v1 firmware. Discovery only queries identity/state.");
    help->setWordWrap(true);layout->addWidget(help);
    status=new QLabel("Detecting speakers...");status->setWordWrap(true);layout->addWidget(status);
    auto rescan=new QPushButton("Rescan speakers");layout->addWidget(rescan);
    connect(rescan,&QPushButton::clicked,this,[this]{Scan();});
    layout->addStretch();return widget;
}

void PebbleProPlugin::Scan() {
    if(stopping||!hid||scanning.exchange(true))return;
    if(scan_thread.joinable())scan_thread.join();
    scan_thread=std::thread([this]{
        try{Discover();}catch(const std::exception& e){Message(e.what(),true);}
        scanning=false;
    });
}

void PebbleProPlugin::Discover() {
    auto paths=hid->Paths();
    for(const auto& path:paths) {
        if(stopping)return;
        bool known=false;
        for(const auto& d:devices)if(d->transport->path==path){
            known=true;
            std::lock_guard<std::mutex> lock(d->transport->mutex);
            try{d->transport->Read();}
            catch(const std::exception&){
                try{d->transport->Reopen();d->transport->Read();Message("Speakers reconnected; current lighting preserved.");}
                catch(const std::exception& e){Message(e.what(),true);}
            }
            break;
        }
        if(known)continue;
        try {
            auto d=std::make_unique<Device>();d->plugin=this;
            d->transport=std::make_unique<Pebble::Transport>(*hid,path);
            Pebble::State state;
            {std::lock_guard<std::mutex> lock(d->transport->mutex);state=d->transport->Read();}
            // Query must identify custom firmware before registration or writes.
            RGBController_Setup setup{};
            setup.name="Creative Pebble Pro";setup.vendor="Creative";
            setup.description="Patched v1 firmware; both speaker rings combined";
            setup.version="Patched v1";setup.serial=path;
            setup.location="HID: "+path;setup.type=DEVICE_TYPE_SPEAKER;
            setup.flags=CONTROLLER_FLAG_VIRTUAL;
            const char* names[]={"Direct","Static","Pulsate","Cycle","Off"};
            const int values[]={0,0,2,1,3};
            for(int i=0;i<5;++i) {
                mode m;m.name=names[i];m.value=values[i];
                m.flags=MODE_FLAG_MANUAL_SAVE|MODE_FLAG_REQUIRES_ENTIRE_DEVICE;
                if(i<3){m.flags|=MODE_FLAG_HAS_PER_LED_COLOR;m.color_mode=MODE_COLORS_PER_LED;}
                setup.modes.push_back(m);
            }
            zone z;z.name="Both speaker rings";z.type=ZONE_TYPE_SINGLE;
            z.leds_count=z.leds_min=z.leds_max=1;setup.zones.push_back(z);
            led l;l.name="Both rings";l.value=0;setup.leds.push_back(l);
            setup.active_mode=state.raw_mode==254||state.raw_mode==2?2:
                state.raw_mode==1?3:state.raw_mode==0?4:1;
            if(state.raw_mode==255&&state.output==0)setup.active_mode=4;
            setup.object_ptr=d.get();
            setup.DeviceUpdateLEDs=&Update;setup.DeviceUpdateZoneLEDs=&UpdateZone;
            setup.DeviceUpdateSingleLED=&UpdateZone;setup.DeviceUpdateMode=&Update;
            setup.DeviceSaveMode=&Save;
            d->controller=api->CreateVirtualRGBController(&setup);
            if(!d->controller)throw std::runtime_error("OpenRGB did not create the controller");
            d->controller->SetColor(0,state.target_valid?state.target:state.output);
            Device* registered=d.get();devices.push_back(std::move(d));
            api->RegisterVirtualRGBController(registered->controller);
            registered->initializing=false;
            Message("Connected: Creative Pebble Pro, patched v1 firmware. Current lighting preserved.");
        }catch(const std::exception& e){Message(std::string("Device not registered: ")+e.what(),true);}
    }
    if(devices.empty())Message("No compatible speakers found. Connect the Pebble Pro with patched v1 firmware.");
}

void PebbleProPlugin::Device::Apply(bool save) {
    if(plugin->stopping)return;
    std::lock_guard<std::mutex> lifecycle_lock(lifecycle);
    if(initializing||plugin->stopping||!controller)return;
    try {
        std::lock_guard<std::mutex> lock(transport->mutex);
        int selected=controller->GetActiveMode();
        constexpr unsigned mapping[]={0,0,2,1,3};
        if(selected<0||selected>=5)throw std::runtime_error("Invalid OpenRGB lighting mode");
        transport->Apply(mapping[selected],controller->GetColor(0),save);
        if(save)plugin->Message("Save to Device: saved mode/color read-back matches. Power-on default updated.");
    }catch(const std::exception& e){plugin->Message(e.what(),true);}
}

void PebbleProPlugin::Unload() {
    if(stopping.exchange(true))return;
    if(scan_timer){scan_timer->stop();delete scan_timer;scan_timer=nullptr;}
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
    devices.clear();hid.reset();api=nullptr;
}
