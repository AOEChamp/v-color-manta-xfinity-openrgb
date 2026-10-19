QT += core gui widgets
TEMPLATE = lib
CONFIG += plugin c++17 release
CONFIG -= debug debug_and_release
TARGET = PebbleProPlugin
DESTDIR = $$PWD/../../build/bin
OBJECTS_DIR = $$PWD/../../build/pebble-pro/obj
MOC_DIR = $$PWD/../../build/pebble-pro/moc
DEFINES += NOMINMAX WIN32_LEAN_AND_MEAN
HEADERS += PebbleProPlugin.h Transport.h Protocol.h
SOURCES += PebbleProPlugin.cpp
DISTFILES += metadata.json
LIBS += -lhid

OPENRGB_SOURCE = $$(OPENRGB_SOURCE)
isEmpty(OPENRGB_SOURCE): error(Set OPENRGB_SOURCE to the pinned OpenRGB checkout)
INCLUDEPATH += $$OPENRGB_SOURCE $$OPENRGB_SOURCE/RGBController $$OPENRGB_SOURCE/dependencies/json $$OPENRGB_SOURCE/dependencies/hidapi-hotplug-win/include
