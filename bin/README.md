# Windows x64 plugin installer

Keep Install.cmd, Uninstall.cmd, Plugins.ps1 and both DLLs together. Install.cmd requests elevation and installs both native plugins for the same Windows user. Close the OpenRGB desktop app first; the Windows service may remain running. No firmware is flashed and no Python runtime is installed.

For a portable installation:

```powershell
.\bin\Plugins.ps1 -OpenRGBDir 'D:\OpenRGB' -SettingsDir 'D:\OpenRGB\config'
```

SettingsDir must be the configuration directory actually used by the desktop app. The desktop app needs administrator privileges for RAM PawnIO access. Installation adds its per-user RUNASADMIN compatibility flag; uninstall intentionally retains that flag because OpenRGB hardware access may still require it.

The installer enables the two plugins and preserves all SDK connections and unrelated plugin settings. It backs up OpenRGB.json, replaced DLLs and prior elevation flags under the selected settings directory's plugin-backups folder. A backup directory is printed on success. Installation failure restores replaced DLLs/settings and any elevation flag it changed.

Uninstall.cmd removes only VColorRamPlugin.dll and PebbleProPlugin.dll. It leaves firmware and backups intact. To restore replaced plugin files or settings, close OpenRGB and copy the chosen backup files into their original locations. A full settings restore also restores unrelated settings from that backup date. Disabled-plugin entries may remain in OpenRGB.json after uninstall.
