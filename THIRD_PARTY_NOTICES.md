# Third-party notices

Project bridge transport source is GPL-2.0-or-later; see LICENSE. Firmware binaries contain original ENE/V-COLOR program code plus local interoperability patches. The project source license does not grant rights to third-party firmware; no vendor redistribution license has been established here.

PawnIOLib.dll, the signed SmbusPIIX4.bin module and the PawnIO driver are loaded from the user's OpenRGB installation and are not redistributed. Python is required separately for the firmware tools and source builds; the standalone bridge bundles its runtime. Capstone and Unicorn are optional development dependencies installed under their own licenses. Proprietary vendor DLLs, decompilation products and vendor installers are not included.

The standalone Windows bridge embeds Python 3.12.14; see PYTHON-LICENSE.txt in its package (src/licenses/PYTHON-LICENSE.txt in the source tree). PyInstaller 6.22.3 builds the executable; its bootloader license and exception are in PYINSTALLER-COPYING.txt (also under src/licenses).
