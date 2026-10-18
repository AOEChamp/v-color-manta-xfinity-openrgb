# V-COLOR Manta XFinity OpenRGB support and persistent colors

This project brings OpenRGB support to V-COLOR Manta XFinity RAM and fixes the RGB-controller firmware so the RAM can remember a saved color across shutdowns and restarts.

There are two parts to that goal:

- **OpenRGB control:** let OpenRGB set the RAM's lighting and send an explicit save command.
- **Persistent colors:** repair the controller's save and startup-restore routines so it can restore the saved lighting when it starts, without waiting for RGB software to reapply it.

This repository includes the **E000 v2 firmware patch**, reproducible build tools, offline tests, a Windows flashing tool, and a Windows OpenRGB bridge. The bridge provides lighting control and Save to Device; persistent colors require the firmware patch. Flashing the firmware fixes persistence; it does not by itself add a device to OpenRGB.

## What the firmware fixes

The supported stock firmware writes saved lighting settings to nonexistent addresses. Nothing is stored, so saved colors do not persist across shutdowns and restarts at all. The startup restore routine also uses the wrong byte layout for saved LED counts.

E000 v2 redirects saving and restoring to the same writable settings block and fixes restoration of the channel and LED counts. It preserves the existing settings format and color arrays. After compatible software explicitly saves your lighting, the controller can restore it at startup. Ordinary Apply only changes the current lighting; it does not save it to flash. See the [flashing and persistence guide](firmware/FLASHING.md) for installation and verification.

## Supported hardware

The supplied firmware and flashing tools target V-COLOR Manta XFinity RAM, model **TMXFL1660830WWK**, with ENE chip-ID bytes `77 30` and firmware signature `A8 32 16 E8 8C`. They support only the exact stock firmware image documented in the [development guide](firmware/DEVELOPMENT.md); a matching product name or controller identity alone is not enough.

ARGB controller: **ENE 6K7732**, identified by the embedded firmware labels (physical package marking has not been inspected). Chip-ID bytes: `77 30`.

Embedded firmware name strings:

- Application: `6K7732-20260814-QFN32-OLED`
- Bootloader: `6K7732BT20200731`

## Install the OpenRGB bridge

The bridge supports Windows x64, AMD PIIX4 SMBus, and eight LEDs per DIMM; port 0 is the hardware-tested configuration. Intel SMBus and Linux are not implemented.

1. Install OpenRGB with its PawnIO driver. Run OpenRGB once, then close it completely, including its tray icon. Close other RAM lighting applications.
2. Keep the complete `bin` folder together and run **[bin/Install.cmd](bin/Install.cmd)**. Accept elevation using the same Windows account you use for OpenRGB.
3. Wait for **Installed and running**, then open OpenRGB normally and accept its administrator prompt. The bridge devices connect through the saved SDK connection.

The installer copies the bridge to `%LOCALAPPDATA%\Programs\VColorOpenRGBBridge` and starts it silently at sign-in. No separate Python installation is needed for the bridge. Apply your lighting and use **Save to Device** on each DIMM to persist it with E000 v2 firmware; ordinary Apply does not save.

See [bridge setup, configuration and removal](bin/README.txt) for portable OpenRGB paths, custom settings files, logs, and uninstalling. See [bridge development](src/README.md) for source and build instructions. The bridge does not flash firmware; use the separate instructions below.

## Quick flashing

Install Python 3.12 and OpenRGB with its PawnIO driver. The default OpenRGB folder is `C:\Program Files\OpenRGB`; pass `-OpenRGBDir` to the launcher for another location. Close all RGB/SMBus applications, open **PowerShell as Administrator**, and change to this repository's directory.

```powershell
# List DIMMs, select a controller, and flash it:
.\firmware\Flash-V2.ps1
```

The selector shows the RGB controller's hardware identity and SMBus address. Windows DIMM slot/manufacturer/part names are also listed; Windows does not reliably map those slots to RGB addresses, so the tool does not guess that association. Discovery checks only RGB addresses `0x70..0x73` on PIIX4 port 0. A matching identity is not proof of compatible stock firmware; the installer retains its stock-page preflight.

Flash one selected module per run, then check the generated report before repeating for another module. Keep power stable. Reports are saved in `firmware/reports/`. See the full flashing guide below for prerequisites, verification, and failure handling.

- [Firmware development, changes, validation, and porting](firmware/DEVELOPMENT.md)
- [Flashing and persistence testing](firmware/FLASHING.md)
- [Supported tools and developer commands](firmware/tools/README.md)

This is an independent interoperability project, with no manufacturer endorsement. See [third-party notices](THIRD_PARTY_NOTICES.md).
