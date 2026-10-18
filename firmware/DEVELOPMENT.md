# Firmware development and porting

## Hardware and artifacts

Developed against V-COLOR Manta XFinity TMXFL1660830WWK. Observed ENE chip-ID bytes: `77 30`; firmware signature: `A8 32 16 E8 8C`. Embedded labels are `6K7732BT20200731` and `6K7732-20260814-QFN32-OLED`; these are firmware labels, not an inspection of the physical chip marking.

The 65,536-byte program-flash dump was acquired twice with identical contents. Original SHA-256: `beaa0db9a2cee7c0ad0af668fd3860b3a1b4d327f7150941d39d0f3db40c278a`.

`images/vcolor-7730-e000-v2.bin` SHA-256: `0263291e72b23c074d9048ecb626b915ffe5e48c8a53264a82ef8530627b7df3`. Its adjacent JSON is the deterministic build manifest. Its historical offline status describes the build stage; current hardware results are below. The stock dump, intermediate build image and captured settings test fixture are included for reproduction.

## Investigation and tools

Python scripts accessed the controller through OpenRGB's PawnIO transport, using the signed PIIX4 SMBus module on port 0 and a shared Windows SMBus mutex. Vendor HALs and public ENE updater code were examined offline for interoperability. Capstone supplied ARM Thumb disassembly; Unicorn executed actual ARM code with simulated flash/MMIO. PE inspection, native disassembly and ILSpy inspection of managed vendor libraries helped identify flash geometry and stop/run behavior. Vendor applications and DLLs were not executed to perform the patch.

The validated dump path enables bit 0 of register `0410`, selects the flash address at `0411..0413`, issues program READ `13` at `0415`, polls busy bit `80` at `0410`, and reads `0414`. The address auto-increments. Control/address registers are saved and restored. `tools/dump_rgb_firmware.py` makes two matching 64 KiB captures; it is specific to this identity, addresses and controller geometry.

Disassembly identified dispatcher `4138`, serializer `6AB0`, startup `420C`, restore `6E0C`, validator `6E90`, and internal page writer `3624`. Command `AA` at live register `E0A0` invokes save. The original save destination was `1F800`, while startup validation read `1F600`. Upper-region reads returned FF and attempted writes did not change data. This does not prove that all upper storage is absent. A bounded lower-flash experiment established that the internal bootloader writer works at `E000`.

## Final firmware changes

The final firmware makes the existing AA save command and startup restore use the same 384-byte storage block at `E000..E17F`. Existing settings-erase paths use this block too. The saved channel and LED counts restore to the correct live registers: channels at `E0A1`, zero at `E0A2`, and LED count at `E0A3`. One channel/eight LEDs therefore restores as `01 00 08`.

The patch preserves the settings format and color arrays. Both the application checksum complement at `2004` and header checksum at `200E` are regenerated: final values `FFC455B9` and `0502`. Application checksum coverage ends at `B747`, so subsequent settings saves do not invalidate firmware integrity. Bootloader bytes below `1800`, coverage length and identity labels remain unchanged.

Only six 128-byte firmware pages differ from stock: `2000`, `4180`, `4200`, `6B00`, `6E00`, `6E80`. The installer writes the checksum/header page last and preserves live settings rather than flashing the entire 64 KiB image.

## Reproduce and validate offline

From this firmware directory, using Python 3.12 (the development version):

```powershell
python -m pip install -r requirements-dev.txt
python tools/build_e000_firmware.py
python tools/build_e000_v2_firmware.py
python tools/analyze_ram_firmware.py images/vcolor-7730-0x71-20261017T135335444329Z-pass1.bin
python tools/validate_final.py
```

Flashing needs only Python's standard library plus the installed PawnIO transport. Capstone and Unicorn are development dependencies. The builders reject any original image with a different size/hash or unexpected patch bytes. The tests use a captured hardware save and check both color arrays, 1/8/16 LED counts, AA save/fresh-start roundtrip, erase paths, invalid-settings fallback, checksum validators and corruption rejection. Emulator startup tests simulate a fresh CPU state; they are not physical power-loss tests.

Both physical addresses 71 and 73 were installed and readback-verified with v2. The first stick's visible red and shutdown/startup persistence were user-confirmed; the exact AC-removal procedure was not recorded. The second stick passed save/readback and CPU-restart restoration with count 0008, but visible output and shutdown/startup persistence were not separately user-confirmed in the source record.

## Apply this research to other V-COLOR RAM

A shared manufacturer or product family does not establish firmware compatibility. These binaries and hard-coded offsets support only the exact original image above. Do not relax the hash check to flash a different image.

1. Identify the RGB controller, signature, SMBus address, host transport, flash size and page geometry. Keep lighting-controller storage distinct from DDR SPD. The flashing selector checks RGB addresses 70..73 on PIIX4 port 0; older research/save scripts retain their explicit 71/73 targets. These they are not generic scanners or Intel transport implementations.
2. Establish a read path for that controller. Dump its own firmware twice, compare every byte and hashes, preserve the original and acquisition logs, and check register restoration. The bundled dump script can inform an adaptation, but its identity/vector guards should remain until replacements are independently verified. A 64 KiB program dump is not proof of a full-chip or calibration backup.
3. Import the raw image into a suitable ARM little-endian Thumb/Cortex-M disassembler/decompiler, verify vectors and memory mapping, and identify live mailbox dispatch, serializer, validation, startup restore, flash helpers, and checksum algorithms. Capstone's included focused listing is disassembly, not a high-level decompiler. Ghidra can support further decompilation; that workflow is a suggested porting tool, not a claimed step in this build.
4. Trace save destinations and restore sources in that image. Establish whether spare storage is backed, writable, unused and outside checksum coverage; do not assume E000 is free on another firmware. Determine any metadata, integrity, protection and bootloader requirements.
5. Write a new builder tied to the new stock hash and exact expected bytes. Patch that image's own instructions/literals, preserve instruction lengths or account for relocation, repair checksums, and preserve bootloader, calibration, identity and existing live settings. Review every changed page.
6. Emulate the actual save/load and checksum routines with realistic captured settings, clean SRAM, invalid blocks and topology counts. Test page-writer failure and uncertain-completion handling before hardware use.
7. Establish a recovery method appropriate to the new controller. Test a single target with a known stock backup and independent control module, stage/read back each full page, write checksum metadata last, and verify neighbors/settings before resuming. Never automatically retry an unresolved flash write.
8. Validate visible output and shutdown/startup behavior before RGB software applies anything; record separately whether AC power was removed. Preserve evidence and publish support only for the tested hardware/firmware revision.

The packaged flasher is a bounded page updater, not a full-chip recovery or universal rollback utility.
