# Native plugin development

- ram/: native ENE Aura 6 PawnIO transport, eight LEDs per matched DIMM, Direct/Static/Off plus twelve effects, per-mode speed, explicit save. Only AMD PIIX4 port 0 and lighting addresses 0x70–0x73 are used. Signature-gated discovery reads current lighting. Transactions hold OpenRGB's global SMBus mutex across register selection, frame/control/apply/save and reselect port 0. Running bridge processes block discovery and writes. Save requires the previously patched RAM firmware; identity alone cannot prove that patch is installed. No automatic save retries or firmware writes occur.
- pebble-pro/: native HID control-output requests and interrupt-input queries; validates custom v3 identity, capabilities and nonce before registration. Both rings share one LED/zone. Save checks the returned saved record; durable storage still needs a power-loss test. Reconnect scanning runs every five seconds; physical hotplug was not tested and a changed HID path can leave a stale entry until reload. Black Static and Off have identical live output. Physical button changes are not continuously reflected in OpenRGB.

## Build

Use Visual Studio 2022 x64 C++ tools and Windows SDK with Qt **6.8.3 msvc2022_64**. Point OPENRGB_SOURCE to an OpenRGB checkout at `e2bae772a9c8a05142e8af1b0efb1c9eb39e74d3` from https://github.com/CalcProgrammer1/OpenRGB. No OpenRGB core changes or library linking are required; standalone plugin interfaces are used. Runtime PawnIO/HID/Qt libraries come from the user's OpenRGB installation and are not bundled.

From a Windows shell (replace paths):

```powershell
$env:QT_ROOT = 'C:\Qt\6.8.3\msvc2022_64'
$env:OPENRGB_SOURCE = 'C:\src\OpenRGB'
.\plugins\build.cmd
powershell.exe -NoProfile -File plugins/test_installer.ps1
```

The build finds VS using vswhere unless cl is already available, builds both plugins, runs both C++ protocol tests, and updates the DLLs in bin/. Intermediate output stays in build/. Do not install a Qt/architecture/API-mismatched DLL.

## Validation

The original sources were hardware-tested against the installed API-5/Qt-6.8.3 host before this repository move. RAM: both DIMMs (0x71, 0x73), distinct per-LED colors, all fifteen mode register values, animated speeds and lighting-preserving discovery; original frame/control bytes restored. The plugin unloads on graceful host exit. Save sequencing and failures before save are unit-tested; no persistent RAM writes or power-cycle test were performed during the plugin migration.

Speakers: all five modes and saved red Pulsate verified through independent firmware readback; clean plugin unregister/unload. Earlier full-power-loss testing confirmed saved red Pulsate restoration. Historical evidence is in firmware/creative-pebble-pro/validation. Offline tests cover protocol identity/nonce/records and RAM mode/speed/RBG/save sequences, including injected failures. They do not prove every firmware animation visually. RAM effect names/speed conventions follow the related ENE implementation.

The host emits a virtual-controller destructor warning, then joins its worker and exits normally; API 5 exposes no Shutdown method. The plugins use the supplied unregister/delete APIs. Plugin lifecycle waits drain GUI notifications before joining discovery, and callback locks are released before host deletion.
