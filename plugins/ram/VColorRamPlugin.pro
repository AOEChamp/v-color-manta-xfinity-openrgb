QT += core gui widgets
TEMPLATE = lib
CONFIG += plugin c++17 release
CONFIG -= debug debug_and_release
TARGET = VColorRamPlugin
DESTDIR = $$PWD/../../build/bin
OBJECTS_DIR = $$PWD/../../build/ram/obj
MOC_DIR = $$PWD/../../build/ram/moc
DEFINES += NOMINMAX WIN32_LEAN_AND_MEAN
HEADERS += VColorRamPlugin.h PawnBus.h Protocol.h
SOURCES += VColorRamPlugin.cpp
DISTFILES += metadata.json


OPENRGB_SOURCE = $$(OPENRGB_SOURCE)
isEmpty(OPENRGB_SOURCE): error(Set OPENRGB_SOURCE to the pinned OpenRGB checkout)
INCLUDEPATH += $$OPENRGB_SOURCE $$OPENRGB_SOURCE/RGBController $$OPENRGB_SOURCE/dependencies/json $$OPENRGB_SOURCE/dependencies/hidapi-hotplug-win/include
