# V-Color RGB firmware — patched v1

## Hardware and artifacts

Supported hardware: V-COLOR Manta XFinity TMXFL1660830WWK. Observed ENE chip-ID bytes: `77 30`; firmware signature: `A8 32 16 E8 8C`. Embedded labels are `6K7732BT20200731` and `6K7732-20260814-QFN32-OLED`; these are firmware labels, not an inspection of the physical chip marking.

Stock reference program image: 65,536 bytes. SHA-256: `beaa0db9a2cee7c0ad0af668fd3860b3a1b4d327f7150941d39d0f3db40c278a`.

`images/vcolor-7730-patched-v1.bin` SHA-256: `43a01f0446d3069e3057d5a0ec8c3c176a0dc1be262fba7cb9ee916333feb105`. Its adjacent JSON is the deterministic build manifest. The stock dump and captured settings test fixture are included for reproduction.

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

The blank tail contains `00`, not the erased-flash value `FF`. Patched v1 uses only the three validated settings pages at `0xE000..0xE17F`, within the 64 KiB program range and outside application checksum coverage. Their write/readback behavior and complete application-mode settings saves are verified. The rest of the blank tail is not established as general-purpose storage.

### Why the original settings addresses do not work

The stock save routine writes three pages at `0x1F800`, `0x1F880`, and `0x1F900`; startup validation/restore reads `0x1F600..0x1F77F`. These are different locations and are all outside the controller's 64 KiB program-flash range. The original save therefore does not store persistent colors. These upper addresses must not be confused with the distinct lower-flash offsets `0xF600` or `0xF800`.

Upper addresses outside the 64 KiB program range return `FF` without establishing writable storage. The read interface aliases across a 128 KiB window; this is not 128 KiB of usable program flash. Mailbox completion alone does not prove data was stored. The 64 KiB reference image does not include or establish separate calibration/trim storage and is not a verified full-chip recovery backup.

## Patched v1 implementation

Patched v1 makes the existing AA save command and startup restore use the same 384-byte storage block at `E000..E17F`. Existing settings-erase paths use this block too. The saved channel and LED counts restore to the correct live registers: channels at `E0A1`, zero at `E0A2`, and LED count at `E0A3`. One channel/eight LEDs therefore restores as `01 00 08`.

The patch preserves the settings format and color arrays. Both the application checksum complement at `2004` and header checksum at `200E` are regenerated: values `FFC45922` and `046F`. Application checksum coverage ends at `B747`, so subsequent settings saves do not invalidate firmware integrity. Bootloader bytes below `1800`, coverage length and identity labels remain unchanged.

Seven 128-byte firmware pages differ from stock: `2000`, `3480`, `4180`, `4200`, `6B00`, `6E00`, `6E80`. The installer writes the checksum/header page last and leaves the settings pages untouched rather than flashing the entire 64 KiB image.

Random Flicker's color-output instructions at `34A8..34D7` multiply each LED's stored R,B,G bytes by that LED's existing random intensity and shift right eight bits. Intensities remain 16 and 128; random choices, counters, iteration and speed are unchanged.

## Reproduce and validate offline

From this firmware directory, using Python 3.12 (the development version):

```powershell
python -m pip install -r requirements-dev.txt
python tools/build_firmware.py
python tools/analyze_firmware.py images/vcolor-7730-stock.bin
python tools/validate_firmware.py
```

Flashing needs only Python's standard library plus the installed PawnIO transport. Capstone and Unicorn are development dependencies. The builders reject any original image with a different size/hash or unexpected patch bytes. The tests use a captured hardware save and check both color arrays, 1/8/16 LED counts, AA save/fresh-start roundtrip, erase paths, invalid-settings fallback, checksum validators and corruption rejection. Emulator startup tests simulate a fresh CPU state; they are not physical power-loss tests.

Renderer validation includes 384 paired stock/patched ARM frames covering red, green, blue, black, white and mixed per-LED colors. It checks identical random state/counters, source-buffer and adjacent-byte preservation, mode-13 dispatch, and save/startup roundtrips. Installer validation covers selected-address routing, stock preflight rejection, readback errors, explicit bootloader errors and uncertain completion. These are offline checks and do not establish visible output or power-loss behavior.

## Porting to other V-COLOR RAM

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
