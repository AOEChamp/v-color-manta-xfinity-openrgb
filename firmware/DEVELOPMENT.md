# Firmware development and porting

## Hardware and artifacts

Developed against V-COLOR Manta XFinity TMXFL1660830WWK. Observed ENE chip-ID bytes: `77 30`; firmware signature: `A8 32 16 E8 8C`. Embedded labels are `6K7732BT20200731` and `6K7732-20260814-QFN32-OLED`; these are firmware labels, not an inspection of the physical chip marking.

The 65,536-byte program-flash dump was acquired twice with identical contents. Original SHA-256: `beaa0db9a2cee7c0ad0af668fd3860b3a1b4d327f7150941d39d0f3db40c278a`.

`images/vcolor-7730-e000-v2.bin` SHA-256: `0263291e72b23c074d9048ecb626b915ffe5e48c8a53264a82ef8530627b7df3`. Its adjacent JSON is the deterministic build manifest. Its historical offline status describes the build stage; current hardware results are below. The stock dump and captured settings test fixture are included for reproduction.

## Controller flash specifications and memory map

The supported controller has **64 KiB (65,536 bytes) of program flash**, at `0x0000..0xFFFF`, with **128-byte pages**. The vendor library's chip table assigns this capacity and page size to chip ID `77 30`; two identical full-range captures and the boundary probes described below corroborate the program-flash map. These specifications apply to the exact controller/image identified above, not every ENE controller or V-COLOR kit.

All ranges below are inclusive program-flash offsets, not DDR SPD or live SMBus register addresses.

| Range | Size | Contents or purpose |
| --- | --- | --- |
| `0x0000..0x17FF` | 6,144 bytes | Bootloader region; unchanged by the patch |
| `0x1800..0xB747` | 40,776 bytes | Application checksum span, including the header below; the checksum calculation excludes the 16-byte header |
| `0x2000..0x200F` | 16 bytes | Application header, including firmware length and checksums; part of the application region above |
| `0xB748..0xFFFF` | 18,616 bytes | Entirely zero-filled in the verified stock image; the last nonzero byte is at `0xB747` |
| `0xE000..0xE17F` | 384 bytes | Patched saved-settings block inside that blank tail: three aligned pages at `0xE000`, `0xE080`, and `0xE100` |

The blank tail contains `00`, not the erased-flash value `FF`. Blank image contents alone do not establish that every location is writable or safe to repurpose. `0xE000` was selected inside the 64 KiB program range and outside application checksum coverage, then tested with the controller's internal bootloader writer: a marker changed `00 -> 01`, read back correctly, and was restored to `00`, with the rest of the page and checked neighbors unchanged. Later application-mode saves verified the complete relocated settings block. The patch uses only those three settings pages; it does not claim the entire blank tail as general-purpose storage.

### Why the original settings addresses do not work

The stock save routine writes three pages at `0x1F800`, `0x1F880`, and `0x1F900`; startup validation/restore reads `0x1F600..0x1F77F`. These are different locations and are all outside the controller's 64 KiB program-flash range. The original save therefore does not store persistent colors. These upper addresses must not be confused with the distinct lower-flash offsets `0xF600` or `0xF800`.

Boundary probes found a sharp transition from `00` at the end of the captured program range to `FF` at `0x10000`. Sampled upper addresses returned `FF`; duplicate peripheral and bootloader reads of the original save/restore blocks were also entirely `FF`. An internal bootloader write at `0x1F800`, using the same writer that worked at `0xE000`, completed its mailbox request but left the page unchanged. Mailbox completion alone is therefore not proof that settings were stored.

The peripheral read interface accepts addresses wider than the backed program-flash range: reads crossing `0x1FFFF..0x20000` wrap to the firmware's first bytes, and an explicit read at `0x20000` matches offset zero. This is an observed **128 KiB read-window alias**, not 128 KiB of usable flash. Likewise, an `FF` response outside the program range is not evidence of writable storage. The 64 KiB program image does not include or establish the size of any separate calibration/trim storage and is not a verified full-chip recovery backup.

## Investigation and tools

Python scripts accessed the controller through OpenRGB's PawnIO transport, using the signed PIIX4 SMBus module on port 0 and a shared Windows SMBus mutex. Vendor HALs and public ENE updater code were examined offline for interoperability. Capstone supplied ARM Thumb disassembly; Unicorn executed actual ARM code with simulated flash/MMIO. PE inspection, native disassembly and ILSpy inspection of managed vendor libraries helped identify flash geometry and stop/run behavior. Vendor applications and DLLs were not executed to perform the patch.

The validated dump path enables bit 0 of register `0410`, selects the flash address at `0411..0413`, issues program READ `13` at `0415`, polls busy bit `80` at `0410`, and reads `0414`. The address auto-increments. Control/address registers are saved and restored. `tools/_internal/dump_rgb_firmware.py` preserves the acquisition routine used to make two matching 64 KiB captures; it is specific to this identity, addresses and controller geometry.

Disassembly identified dispatcher `4138`, serializer `6AB0`, startup `420C`, restore `6E0C`, validator `6E90`, and internal page writer `3624`. Command `AA` at live register `E0A0` invokes save. The memory map and hardware probes above explain why the stock upper-address destinations were replaced with the validated lower-flash block at `E000`.

## E000 v2 persistence changes

The final firmware makes the existing AA save command and startup restore use the same 384-byte storage block at `E000..E17F`. Existing settings-erase paths use this block too. The saved channel and LED counts restore to the correct live registers: channels at `E0A1`, zero at `E0A2`, and LED count at `E0A3`. One channel/eight LEDs therefore restores as `01 00 08`.

The patch preserves the settings format and color arrays. Both the application checksum complement at `2004` and header checksum at `200E` are regenerated: final values `FFC455B9` and `0502`. Application checksum coverage ends at `B747`, so subsequent settings saves do not invalidate firmware integrity. Bootloader bytes below `1800`, coverage length and identity labels remain unchanged.

Only six 128-byte firmware pages differ from stock: `2000`, `4180`, `4200`, `6B00`, `6E00`, `6E80`. The installer writes the checksum/header page last and preserves live settings rather than flashing the entire 64 KiB image.

## Reproduce and validate offline

### E000 v3: stored-color Random Flicker

`images/vcolor-7730-e000-v3-stored-flicker.bin` has SHA-256 `43a01f0446d3069e3057d5a0ec8c3c176a0dc1be262fba7cb9ee916333feb105`. Build it with `python tools/build_firmware.py --version 3`. The original-image hash guard and all v2 persistence fixes remain in place.

V3 replaces only the color-output instructions at `34A8..34D7`: each LED's stored R,B,G bytes are multiplied by that LED's existing random intensity and shifted right eight bits. Intensities remain 16 and 128; random choices, counters, iteration and speed are unchanged. The only pages changed from v2 are `3480` and the checksum/header page `2000`. Settings format, identity strings and bootloader are unchanged.

`validate_final.py` includes 384 paired original/patched ARM-renderer frames covering red, green, blue, black, white and mixed per-LED colors; it verifies identical random state/counters, source-buffer and adjacent-byte preservation, mode-13 dispatch, save/startup roundtrips and checksums. Fourteen upgrade cases cover both selected DIMM addresses, settings preservation, stock/already-v3/mismatched preflight rejection, readback errors, explicit bootloader errors and uncertain completion. These are offline checks and do not establish visible output or power-loss behavior.

`Flash-V3.ps1` uses the existing bounded writer with exact v2 preflight, captures live saved settings and verifies them unchanged, writes only the two changed pages (checksum last), and retains the incomplete-update/CPU-exit guards. It does not apply lighting or issue a save command.

### Commands

From this firmware directory, using Python 3.12 (the development version):

```powershell
python -m pip install -r requirements-dev.txt
python tools/build_firmware.py
python tools/analyze_firmware.py images/vcolor-7730-stock.bin
python tools/validate_final.py
```

Flashing needs only Python's standard library plus the installed PawnIO transport. Capstone and Unicorn are development dependencies. The builders reject any original image with a different size/hash or unexpected patch bytes. The tests use a captured hardware save and check both color arrays, 1/8/16 LED counts, AA save/fresh-start roundtrip, erase paths, invalid-settings fallback, checksum validators and corruption rejection. Emulator startup tests simulate a fresh CPU state; they are not physical power-loss tests.

Both physical addresses 71 and 73 were installed and readback-verified with v2. The first stick's visible red and shutdown/startup persistence were user-confirmed; the exact AC-removal procedure was not recorded. The second stick passed save/readback and CPU-restart restoration with count 0008, but visible output and shutdown/startup persistence were not separately user-confirmed in the source record.

## Apply this research to other V-COLOR RAM

A shared manufacturer or product family does not establish firmware compatibility. These binaries and hard-coded offsets support only the exact original image above. Do not relax the hash check to flash a different image.

1. Identify the RGB controller, signature, SMBus address, host transport, flash size and page geometry. Keep lighting-controller storage distinct from DDR SPD. The flashing selector checks RGB addresses 70..73 on PIIX4 port 0; the acquisition reference routine retains its original 71/73 assumptions. These are not generic scanners or Intel transport implementations.
2. Establish a read path for that controller. Dump its own firmware twice, compare every byte and hashes, preserve the original and acquisition logs, and check register restoration. The bundled dump script can inform an adaptation, but its identity/vector guards should remain until replacements are independently verified. A 64 KiB program dump is not proof of a full-chip or calibration backup.
3. Import the raw image into a suitable ARM little-endian Thumb/Cortex-M disassembler/decompiler, verify vectors and memory mapping, and identify live mailbox dispatch, serializer, validation, startup restore, flash helpers, and checksum algorithms. Capstone's included focused listing is disassembly, not a high-level decompiler. Ghidra can support further decompilation; that workflow is a suggested porting tool, not a claimed step in this build.
4. Trace save destinations and restore sources in that image. Establish whether spare storage is backed, writable, unused and outside checksum coverage; do not assume E000 is free on another firmware. Determine any metadata, integrity, protection and bootloader requirements.
5. Write a new builder tied to the new stock hash and exact expected bytes. Patch that image's own instructions/literals, preserve instruction lengths or account for relocation, repair checksums, and preserve bootloader, calibration, identity and existing live settings. Review every changed page.
6. Emulate the actual save/load and checksum routines with realistic captured settings, clean SRAM, invalid blocks and topology counts. Test page-writer failure and uncertain-completion handling before hardware use.
7. Establish a recovery method appropriate to the new controller. Test a single target with a known stock backup and independent control module, stage/read back each full page, write checksum metadata last, and verify neighbors/settings before resuming. Never automatically retry an unresolved flash write.
8. Validate visible output and shutdown/startup behavior before RGB software applies anything; record separately whether AC power was removed. Preserve evidence and publish support only for the tested hardware/firmware revision.

The packaged flasher is a bounded page updater, not a full-chip recovery or universal rollback utility.
