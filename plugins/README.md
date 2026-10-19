# Native plugin development

- ram/: native ENE Aura 6 PawnIO transport, eight LEDs per matched DIMM, Direct/Static/Off plus twelve effects, per-mode speed, explicit save. Only AMD PIIX4 port 0 and lighting addresses 0x70–0x73 are used. Signature-gated discovery reads current lighting. Transactions hold OpenRGB's global SMBus mutex across register selection, frame/control/apply/save and reselect port 0. Save requires the patched v1 RAM firmware; identity alone cannot prove that patch is installed. No automatic save retries or firmware writes occur.
- pebble-pro/: native HID control-output requests and interrupt-input queries; validates patched v1 identity, capabilities and nonce before registration. Both rings share one LED/zone. Save checks the returned saved record; durable storage still needs a power-loss test. Reconnect scanning runs every five seconds; physical hotplug was not tested and a changed HID path can leave a stale entry until reload. Black Static and Off have identical live output. Physical button changes are not continuously reflected in OpenRGB.

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

Both plugins support the API-5/Qt-6.8.3 host. RAM validation covers both DIMMs (0x71, 0x73), distinct per-LED colors, all fifteen mode register values, animated speeds, lighting-preserving discovery and graceful unload. Tests restore the initial frame/control bytes. Save sequencing and failures before save are unit-tested; the plugin validation does not include persistent RAM writes or a power-cycle test.

Speaker validation covers all five modes, saved-state readback, plugin unregister/unload and restoration of saved red Pulsate after full power loss. Offline tests cover protocol identity/nonce/records and RAM mode/speed/RBG/save sequences, including injected failures. They do not prove every firmware animation visually. RAM effect names/speed conventions follow the related ENE implementation.

The host emits a virtual-controller destructor warning, then joins its worker and exits normally; API 5 exposes no Shutdown method. The plugins use the supplied unregister/delete APIs. Plugin lifecycle waits drain GUI notifications before joining discovery, and callback locks are released before host deletion.
