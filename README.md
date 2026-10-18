# V-COLOR Manta XFinity OpenRGB support and persistent colors

This project brings OpenRGB support to V-COLOR Manta XFinity RAM and fixes the RGB-controller firmware so the RAM can remember a saved color across shutdowns and restarts.

There are two parts to that goal:

- **OpenRGB control:** let OpenRGB set the RAM's lighting and send an explicit save command.
- **Persistent colors:** repair the controller's save and startup-restore routines so it can restore the saved lighting when it starts, without waiting for RGB software to reapply it.

This repository includes the **E000 v2 persistence fix** and **E000 v3 stored-color Random Flicker upgrade**, reproducible build tools, offline tests, Windows flashing tools, and a Windows OpenRGB bridge. The bridge provides lighting control and Save to Device; persistent colors require the firmware patch. Flashing the firmware fixes persistence; it does not by itself add a device to OpenRGB.

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
2. Download the [Windows x64 ZIP](https://github.com/AOEChamp/v-color-manta-xfinity-openrgb/releases/latest/download/VColor-OpenRGB-Bridge-Windows-x64.zip), extract it, and run **Install.cmd** from the extracted folder. Keep all extracted files together. Accept elevation using the same Windows account you use for OpenRGB. The repository's [bin folder](bin/) contains the same files.
3. Wait for **Installed and running**, then open OpenRGB normally and accept its administrator prompt. The bridge devices connect through the saved SDK connection.

The installer copies the bridge to `%LOCALAPPDATA%\Programs\VColorOpenRGBBridge` and starts it silently at sign-in. No separate Python installation is needed for the bridge. Apply your lighting and use **Save to Device** on each DIMM to persist it with E000 v2 firmware; ordinary Apply does not save.

See [bridge setup, configuration and removal](bin/README.txt) for portable OpenRGB paths, custom settings files, logs, and uninstalling. See [bridge development](src/README.md) for source and build instructions. The bridge does not flash firmware; use the separate instructions below.

### Lighting modes

The RAM mode list includes Direct, Static and Off, plus the firmware effects: Breathing, Flashing, Spectrum Cycle, Rainbow, Chase Fade (fixed-color and rainbow), Chase (fixed-color and rainbow), Random Flicker, Stack, Pong and Fill Up. Hardware effects expose a speed slider; fixed-color effects also expose per-LED colors. Random Flicker exposes color control for firmware with the mode 13 color patch; older firmware may ignore these colors. Save to Device stores the selected effect and speed with E000 v2 firmware.

Effect IDs are confirmed from the firmware dispatcher. Static, Rainbow and fixed-color Chase have been visually tested. Other effect names and the speed range follow the related ENE controller. E000 v3 changes Random Flicker to scale each LED's stored color by the existing random intensity, retaining its timing and speed behavior. There is no dedicated lightning/storm mode.

## Quick flashing

For **stored-color Random Flicker**, install v2 first if starting from stock, then run `firmware/Flash-V3.ps1` from this repository to upgrade v2 to v3. The v3 upgrade writes only the renderer and checksum pages and preserves saved settings. It requires the exact bundled v2 firmware; it rejects stock, already-v3 and mismatched firmware. See [v3 upgrade instructions](firmware/FLASHING.md#upgrade-v2-to-v3-stored-color-random-flicker). The v2 download below remains the persistence-only flasher.

Download the [flash ZIP](https://github.com/AOEChamp/v-color-manta-xfinity-openrgb/releases/latest/download/VColor-E000-v2-Flasher-Windows-x64.zip), extract it, and follow these instructions from the extracted folder. It contains only the flashing files and instructions; Python and OpenRGB are installed separately.

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
