# V-COLOR Manta XFinity RGB

Custom E000 v2 RGB-controller firmware and tools for V-COLOR Manta XFinity RAM, model TMXFL1660830WWK, with ENE chip-ID bytes `77 30` and firmware signature `A8 32 16 E8 8C`.

ARGB controller: **ENE 6K7732**, identified by the embedded firmware labels (physical package marking has not been inspected). Chip-ID bytes: `77 30`.

Embedded firmware name strings:

- Application: `6K7732-20260814-QFN32-OLED`
- Bootloader: `6K7732BT20200731`

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

The firmware enables the existing controller save/startup-restore path. OpenRGB integration is the repository's intended scope; the complete OpenRGB controller/bridge release is not yet packaged here. The included transport module supplies flashing access through the installed OpenRGB/PawnIO runtime.

This is an independent interoperability project, with no manufacturer endorsement. See [third-party notices](THIRD_PARTY_NOTICES.md).
