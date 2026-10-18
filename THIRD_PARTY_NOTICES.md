# Third-party components

The bridge source is supplied under GPL-2.0-or-later (see LICENSE).

The source repository also contains separate firmware research under src/firmware. Its firmware binaries contain original ENE/V-COLOR program code plus interoperability patches. The project source license does not grant rights to that third-party firmware; no vendor redistribution license has been established here. Firmware is not included in bin.

The standalone Windows package embeds Python 3.12.14, distributed under the Python Software Foundation license and associated notices; see PYTHON-LICENSE.txt. PyInstaller 6.22.3 produces the executable. Its bootloader is GPL-2.0-or-later with the PyInstaller bootloader exception; see PYINSTALLER-COPYING.txt.

The bridge loads the user's existing OpenRGB PawnIOLib.dll and signed SmbusPIIX4.bin from the OpenRGB installation. Neither file is redistributed here. PawnIOLib's source identifies its license as LGPL-2.1-or-later.

Gigabyte, ENE and other vendor libraries were used only for local interoperability research and are not bundled. The portable compiler, tracing/decompilation tools and test-client package used during development are also excluded from this release.
