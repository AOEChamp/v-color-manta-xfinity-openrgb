// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <QObject>
#include <QLabel>
#include <QPointer>
#include <QTimer>
#include <atomic>
#include <memory>
#include <thread>
#include "OpenRGBPluginInterface.h"
#include "PawnBus.h"

class VColorRamPlugin:public QObject,public OpenRGBPluginInterface {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID OpenRGBPluginInterface_IID FILE "metadata.json")
    Q_INTERFACES(OpenRGBPluginInterface)
    struct Device {
        VColorRamPlugin* plugin;
        unsigned address=0;
        RGBControllerInterface* controller=nullptr;
        std::atomic<bool> initializing{true};
        std::mutex lifecycle;
        void Apply(bool save);
    };
    OpenRGBPluginAPIInterface* api=nullptr;
    std::unique_ptr<VColor::PawnBus> bus;
    std::vector<std::unique_ptr<Device>> devices;
    std::thread scan_thread;
    std::atomic<bool> scanning{false},stopping{false};
    QPointer<QWidget> widget;
    QPointer<QLabel> status;

    void Scan();
    void Discover();
    void Message(const std::string& message,bool error=false);
    static void Update(void* object){static_cast<Device*>(object)->Apply(false);}
    static void UpdateZone(void* object,int){Update(object);}
    static void Save(void* object){static_cast<Device*>(object)->Apply(true);}
public:
    ~VColorRamPlugin() override {Unload();}
    OpenRGBPluginInfo GetPluginInfo() override;
    unsigned int GetPluginAPIVersion() override{return OPENRGB_PLUGIN_API_VERSION;}
    void Load(OpenRGBPluginAPIInterface* plugin_api) override;
    QWidget* GetWidget() override;
    QMenu* GetTrayMenu() override{return nullptr;}
    void Unload() override;
    void OnProfileAboutToLoad() override{}
    void OnProfileLoad(nlohmann::json) override{}
    nlohmann::json OnProfileSave() override{return nlohmann::json::object();}
    unsigned char* OnSDKCommand(unsigned int,unsigned char*,unsigned int* size) override{*size=0;return nullptr;}
    void ProfileManagerUpdated(unsigned int) override{}
    void ResourceManagerUpdated(unsigned int) override{}
    void SettingsManagerUpdated(unsigned int) override{}
};
