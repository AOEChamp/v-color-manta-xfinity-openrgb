# V-Color Manta XFinity for OpenRGB

A Windows bridge that adds compatible V-Color Manta XFinity DDR5 lighting to OpenRGB. Supports eight LEDs per DIMM, Static, Direct and Off modes, individual LED colors, and Save to Device with patched E000 v2 firmware.

## Install

1. Install Windows x64 OpenRGB with its PawnIO driver. Run OpenRGB once, then close it completely, including its tray icon. Close other applications controlling the RAM.
2. Download or clone this repository. Keep the complete `bin` folder together and run **[bin/Install.cmd](bin/Install.cmd)**. Accept elevation using the same Windows account you use for OpenRGB.
3. Wait for **Installed and running**, then open OpenRGB normally and accept its administrator prompt. The RAM devices connect automatically; no SDK or firmware configuration is required.

The installer copies the application to **`%LOCALAPPDATA%\Programs\VColorOpenRGBBridge`**. It replaces an older bridge startup task, saves OpenRGB's localhost SDK connection with a settings backup, and verifies the new bridge is listening before reporting success. It also configures OpenRGB to request administrator rights for native hardware detection. The bridge starts silently at sign-in; OpenRGB keeps its normal hardware detection.

After successful installation, you can move or remove the downloaded repository. The installed application does not depend on that folder. No Python installation is needed. The bridge does not stop, pause or restart other RGB applications or services.

## Configuration and troubleshooting

OpenRGB's folder must contain `OpenRGB.exe`, `PawnIOLib.dll` and `SmbusPIIX4.bin`. The bridge discovers portable installations beside itself, standard Program Files installations and OpenRGB on PATH. If discovery fails, copy `bin/bridge-config.example.json` to `bin/bridge-config.json`, set `openrgb_dir`, and rerun Install. Existing installed configuration is preserved during upgrades; edit it in the installed application folder when updating settings.

The optional settings are `openrgb_dir` (null for discovery), `port` (default 6743) and `smbus_port` (default 0). If another SDK server uses 6743, select a free port before installation. For OpenRGB launched with a custom configuration directory, use:

```powershell
.\bin\Install.cmd -SettingsPath "<full path to OpenRGB.json>"
```

Setup failures are reported in a dialog and `logs/setup-error.log` in the application or download folder. Runtime logs are in the installed application's `logs` folder. OpenRGB settings backups are saved beside `OpenRGB.json`. `Start.cmd` and `Stop.cmd` in the installed folder provide manual control. Closing OpenRGB alone leaves the bridge running.

To uninstall, close OpenRGB and run **Uninstall.cmd** from the installed application folder. It stops the bridge, removes its startup task and saved SDK connection, and restores the previous OpenRGB elevation setting if it has not otherwise changed. The stopped application folder and logs can then be deleted.

## Compatibility and persistence

Requires **Windows x64 and AMD PIIX4 SMBus**. The supported RAM is **TMXFL1660830WWK**, with firmware signature `A8 32 16 E8 8C` and eight LEDs per DIMM. Matching lighting controllers are discovered at addresses `0x70` through `0x73`. Other models and firmware revisions are not assumed compatible. Intel SMBus and Linux are not implemented; PIIX4 port 0 is the hardware-tested configuration.

**Save to Device assumes patched E000 v2 firmware on every matched DIMM.** Apply your lighting, then save each desired DIMM. Ordinary Apply does not persist lighting. Direct saves a snapshot; Off saves black. The bridge does not verify or flash firmware, and the original firmware does not provide the repaired persistence behavior.

The [firmware documentation](firmware/DEVELOPMENT.md) and [flashing instructions](firmware/FLASHING.md) are in the separate top-level `firmware` directory. Firmware tools are separate from the bridge installer.

## Repository layout

| Path | Contents |
| --- | --- |
| `bin/` | Installer, runnable bridge, required runtime, configuration example and notices |
| `src/bridge/` | Python bridge and OpenRGB settings helper |
| `src/windows/` | Installer and launcher source |
| `src/tests/` | Offline bridge, settings, packaging and installer tests |
| `src/tools/` | Build and folder preparation scripts |
| `firmware/` | Firmware source tools, required reference images, tests and research |
| `src/docs/` | Register and SDK protocol documentation |

To build, install Python 3.12 x64 and run:

```powershell
python -m pip install -r src/requirements-dev.txt
.\src\tools\build_release.ps1
```

The build runs offline tests and updates `bin`; it creates no release archive and does not install anything or access RAM. Build intermediates and local settings are ignored by Git. See [src/README.md](src/README.md) for development commands.

GPL-2.0-or-later. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md). Independent interoperability project, with no manufacturer endorsement.
