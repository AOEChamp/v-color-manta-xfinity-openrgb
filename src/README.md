# Development

The runtime implementation is in `bridge`, Windows setup in `windows`, and offline tests in `tests`. The top-level `../firmware` directory contains separate firmware research and tools; bridge setup never invokes them.

From the repository root, using Python 3.12 x64 on Windows:

```powershell
python -m pip install -r src/requirements-dev.txt
python -m unittest discover -s src/tests -v
powershell -NoProfile -ExecutionPolicy Bypass -File src/tests/test_installer.ps1
.\src\tools\build_release.ps1
```

The build puts PyInstaller intermediates in ignored `build/`, then copies only runtime files and end-user scripts into `bin/`. Installer tests mock scheduled tasks, registry changes and hardware access. The settings tests verify backups, preservation of unrelated configuration, duplicate handling and uninstall behavior. A successful offline run does not establish real sign-in behavior on every Windows installation.

For source-only inspection:

```powershell
python src/bridge/openrgb_bridge.py --help
python src/bridge/openrgb_bridge.py --print-config
```

These commands do not access RAM. Running the server or `--list` requires administrator access and a supported OpenRGB/PawnIO installation. Source runs can select a configuration with `--config`; compiled runs read `bridge-config.json` beside the executable.

The installed application lives in `%LOCALAPPDATA%\Programs\VColorOpenRGBBridge`. Rebuilding `bin` does not update that installation. To reinstall, close OpenRGB, run the installed `Uninstall.cmd`, then run `bin/Install.cmd`. Setup supports a fresh installation and rejects an existing installation or startup task; it does not migrate development versions. It saves the resolved absolute OpenRGB path before copying the bridge and checks the listening process before claiming success. Uninstall uses the saved SDK port and settings path without requiring OpenRGB discovery.

Firmware build and validation instructions are in [../firmware/DEVELOPMENT.md](../firmware/DEVELOPMENT.md). The [protocol reference](docs/PROTOCOL.md) describes the runtime register sequence.
