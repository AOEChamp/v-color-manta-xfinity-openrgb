# Windows x64 plugin installer

Keep Install.cmd, Uninstall.cmd, Plugins.ps1 and both DLLs together. Install.cmd requests elevation and installs both native plugins for the same Windows user. Close the OpenRGB desktop app first; the Windows service may remain running. No firmware is flashed and no Python runtime is installed.

For a portable installation:

```powershell
.\bin\Plugins.ps1 -OpenRGBDir 'D:\OpenRGB' -SettingsDir 'D:\OpenRGB\config'
```

SettingsDir must be the configuration directory actually used by the desktop app. The desktop app needs administrator privileges for RAM PawnIO access. Installation adds its per-user RUNASADMIN compatibility flag; uninstall intentionally retains that flag because OpenRGB hardware access may still require it.

Migration recognizes only the existing VColorOpenRGBBridge task for the current SID and installed launcher under LOCALAPPDATA\Programs\VColorOpenRGBBridge. Unexpected task actions cause an error before changes. Unrelated SDK clients/plugins are preserved. A backup directory is printed on success. Failure restores replaced DLLs/settings and the old task's enabled/running state. The prior bridge application remains installed for rollback.

Uninstall.cmd removes only VColorRamPlugin.dll and PebbleProPlugin.dll. It does not re-enable the bridge or revert firmware. To restore the previous bridge, close OpenRGB, uninstall these plugins, restore OpenRGB.json from the chosen plugin-backups directory, then enable and start the existing VColorOpenRGBBridge scheduled task in Task Scheduler. A full settings restore also restores unrelated settings from that backup date. Existing disabled-plugin entries may remain in OpenRGB.json after uninstall.
