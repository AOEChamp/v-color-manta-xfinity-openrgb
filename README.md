# OpenRGB plugins for V-Color RAM and Creative Pebble Pro

Native Windows x64 OpenRGB plugins for V-COLOR Manta XFinity DDR5 RAM and Creative Pebble Pro speakers, plus the firmware patches that let each device restore saved lighting after power loss.

| Device | Control | Persistent lighting |
| --- | --- | --- |
| V-Color Manta XFinity TMXFL1660830WWK | Eight independent LEDs per DIMM, 15 modes, hardware speed control | Patched v1 ENE firmware |
| Creative Pebble Pro | Both speaker rings together; Direct, Static, Pulsate, Cycle, Off | Patched v1 firmware with explicit save and readback |

## Install the plugins

1. Install Windows x64 OpenRGB with plugin API **5** and **Qt 6.8.3 MSVC x64**, including its PawnIO driver. Tested host: OpenRGB v1.1, commit `8e16de27858cf2be6af54a33ce003df74cb9fd3e`. Other Qt/plugin ABI versions are not interchangeable.
2. Fully exit the OpenRGB desktop app, including its tray icon. Its session-0 Windows service may remain running.
3. Download/extract this repository and run [bin/Install.cmd](bin/Install.cmd). Keep the bin folder together. Accept elevation as the same Windows user that runs OpenRGB.
4. Open OpenRGB and accept its administrator prompt. Enable both plugins in the Plugins page if necessary. Select the RAM or speakers in Devices.

The installer copies only the two plugin DLLs into `%APPDATA%\OpenRGB\plugins`, explicitly enables them, and makes OpenRGB request administrator privileges by default. UAC still prompts. For portable installations pass `-OpenRGBDir` and `-SettingsDir` to `bin/Plugins.ps1`; the latter contains OpenRGB.json and the plugins folder.

This OpenRGB build loads plugins in the desktop application, **not its headless Windows service**. Keep the elevated desktop app running for live control. Enable Shared SMBus Access so native OpenRGB, its service and the RAM plugin coordinate bus transactions. SDK clients need OpenRGB's Serve all devices setting to see plugin controllers.

Use **Save to Device** to store the current lighting; normal updates and profile loads remain volatile. Installing plugins does not flash firmware. RAM persistence requires the patched v1 firmware. Stock Pebble firmware does not expose this RGB command/query protocol and is deliberately rejected by speaker discovery.

## Firmware

- [V-Color ENE firmware and flashing](firmware/FLASHING.md): patched v1 image, stock-image guards, per-DIMM flashing tool, checksums and tests. RAM model TMXFL1660830WWK, chip ID `77 30`, firmware signature `A8 32 16 E8 8C`; only the exact documented stock image is supported.
- [Creative Pebble Pro firmware, protocol and installation](firmware/creative-pebble-pro/README.md): patched v1 update container, build source, query/color helper and offline validation. Confirmed saved red Pulsate returns after disconnecting both power inputs. This does not establish recovery after an interrupted full firmware update.

The firmware patches change lighting controllers, not DDR SPD or audio drivers. Flashing is a separate, explicit operation; read the applicable device guide.

## Build and validation

See [plugins/README.md](plugins/README.md) for the pinned OpenRGB headers, Qt/compiler setup, offline protocol tests, build output and hardware validation limits. CI builds both DLLs and runs installer settings tests plus both firmware suites without hardware access. Prebuilt DLLs are in bin; CI artifacts contain the same installer layout rebuilt from source.

Run `bin/Uninstall.cmd` with the desktop app closed to remove the two DLLs. Firmware and settings backups are retained. See [bin/README.md](bin/README.md) for removal and restoring backups.

Independent interoperability work; no vendor endorsement. Project source is GPL-2.0-or-later. Firmware containers include third-party code with separate rights; see [third-party notices](THIRD_PARTY_NOTICES.md).
