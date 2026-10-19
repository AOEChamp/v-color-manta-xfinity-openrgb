# Third-party notices

Project plugin transport, patch-generation and interoperability source is GPL-2.0-or-later; see LICENSE. OpenRGB plugin interfaces are consumed from an external pinned OpenRGB checkout, also GPL-2.0-or-later. No OpenRGB or Qt runtime is bundled. Plugins use the user's matching OpenRGB installation, including Qt, PawnIO and HID libraries and the installed PawnIO driver.

ENE/V-COLOR firmware binaries and the Creative Pebble Pro update container include original third-party program code/data plus local interoperability patches. The source license does not grant rights to vendor firmware; no vendor redistribution license has been established here. The Pebble container retains the vendor's other payloads and update recipe unchanged; that container can contain vendor scripts/library payloads. Standalone vendor installers, extracted updater executables/libraries, and decompilation dumps are not included.

Python is installed separately for firmware development/tools; no Python or PyInstaller runtime is shipped for plugins. Unicorn, pypcode, Capstone, the compiler and Qt development tools have their own licenses. This is independent interoperability work, without Creative, V-COLOR, ENE, Actions, OpenRGB or Qt endorsement.
