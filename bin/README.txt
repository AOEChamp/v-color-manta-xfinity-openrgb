V-Color Manta XFinity OpenRGB Bridge

Windows x64 and AMD PIIX4. OpenRGB and its PawnIO driver must already be installed.

INSTALL
Close OpenRGB, including its tray icon, and other RAM lighting software.
Run Install.cmd and accept elevation using your normal Windows account.
The installer copies this package to:
  %LOCALAPPDATA%\Programs\VColorOpenRGBBridge
It saves OpenRGB's SDK connection with a backup,
starts the bridge and verifies it is listening before reporting success.
You can remove the downloaded bridge files after installation. Keep OpenRGB
itself at its recorded location, including portable installations.

Open OpenRGB normally and accept its administrator prompt. RAM devices are
added automatically through the saved localhost connection. Save to Device
assumes patched E000 v2 firmware; ordinary Apply does not persist lighting.
The bridge never pauses or stops other RGB applications or their services.

CUSTOM OPENRGB INSTALLATION
If discovery fails, copy bridge-config.example.json to bridge-config.json and
set openrgb_dir. Setup saves its resolved absolute path in the installed
configuration. Defaults are SDK port 6743 and AMD PIIX4 port 0. To reinstall,
uninstall first; earlier development installations are not migrated.
For a custom OpenRGB settings file, run:
  Install.cmd -SettingsPath "<full path to OpenRGB.json>"

UNINSTALL
Close OpenRGB and run Uninstall.cmd. The startup task and saved SDK connection
are removed, even if OpenRGB has been moved or removed. The installed folder
is left for you to delete after it stops.
Manual Start.cmd and Stop.cmd are available in the installed folder.
Logs are in the installed logs directory; OpenRGB settings backups are beside
OpenRGB.json. The full project README and source are in the repository.
