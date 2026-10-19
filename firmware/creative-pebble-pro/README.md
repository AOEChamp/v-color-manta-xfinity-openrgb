# Creative Pebble Pro RGB firmware, protocol v3

`images/MF1710-RGB-v3.fw` is the exact update container flashed and tested on this project's Creative Pebble Pro speakers. It derives from PebbleProFWInstaller_1.0.1.0.exe's stock MF1710.fw. Custom protocol 3 is a local interface version, not Creative's firmware version. Stock USB application identity: VID 041E, PID 3287, interface 0 generic HID collection.

| Artifact | SHA-256 |
| --- | --- |
| Stock MF1710.fw | 5c92e9dbf65713ee2435babb186aa1442d149918029208727b0e4d9e9918248b |
| Patched MF1710-RGB-v3.fw | 7fe19a661d17c2abd1de215c65afb5ae87d1775474c150274f0614a5c7dd90fe |

## What changes

Adds USB RGB commands for Static, Cycle, Pulsate and Off, explicit save via the stock property/NVRAM API, boot restoration, and a query for current/saved state. Direct mode is software-updated Static. Both rings share one mode/color. The 12-byte OPENRGB_V1 property contains a magic word, packed mode/RGB command and its complement. Identical saves skip the property setter/flush. Ordinary updates remain volatile. Local button changes do not overwrite the explicit startup default. Invalid/missing records keep stock boot behavior; pending host commands win over boot restoration.

Injected code and key occupy 1,440 bytes of reclaimed diagnostic text; affected literal pointers are redirected to existing empty text. Application remains **839,360 bytes**, fitting each declared 950,272-byte slot with **110,912 bytes spare**. Update container stays 4,890,640 bytes. No new global RAM is reserved; the maximum added wrapper stack use is up to 128 bytes before native callees. Runtime stack margin is not measured. Bootloader, partition data, other FAT members and container DB tail remain unchanged in the rebuilt image.

## Installing firmware separately

The OpenRGB plugin installer never flashes speakers. Obtain Creative's official 1.0.1.0 updater and its matching extracted Tool directory containing ATSSDK.exe and its dependencies; these updater executables/libraries are not distributed separately here. Keep a matching stock updater for returning to stock firmware. Verify the patched hash above before use.

Close RGB applications, supply stable power, and enter the speaker's firmware-update mode using the Creative updater's procedure. The tested update-mode device was a single Actions WinUSB device VID_10D6/PID_10D6. Do not guess the button sequence or substitute a different device/updater. This firmware targets the tested Pebble Pro package only.

The successful development flash used elevated `ATSSDK.exe` with the absolute patched `.fw` path as its sole argument, with working directory set to the extracted Tool directory. From PowerShell, substituting actual paths:

```powershell
$tool = 'C:\ExtractedCreativeUpdater\tmp\Tool'
$image = (Resolve-Path '.\firmware\creative-pebble-pro\images\MF1710-RGB-v3.fw').Path
if ((Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash -ne '7FE19A661D17C2ABD1DE215C65AFB5AE87D1775474C150274F0614A5C7DD90FE') { throw 'Wrong firmware image' }
# Run only once the intended speaker is confirmed in update mode:
$update = Start-Process -FilePath (Join-Path $tool 'ATSSDK.exe') -ArgumentList ('"' + $image + '"') -WorkingDirectory $tool -Verb RunAs -Wait -PassThru
$update.ExitCode
```

An exit code of zero is not a boot or persistence test. Return to normal power-on, install/use the plugin, save a color/mode, then disconnect **both** power inputs and confirm it returns. Protocol-3 readback and saved red Pulsate were verified on hardware; the user confirmed restoration after full power loss. Soft standby restoration and arbitrary device revisions were not established.

**Recovery limit:** the full stock update recipe writes mbrec.bin at offset 0, even though its bytes are unchanged in this patch. An interrupted update can damage the flash bootloader. Mirrored boot partitions, invalid-image ADFU entry and a recovery GPIO path were identified/emulated, but live recovery after a failed flash and the recovery button mapping were not verified. Do not treat the boot checks as a guarantee of recovery.

## Rebuild and offline tests

Python 3.12:

```text
python -m pip install -r firmware/creative-pebble-pro/requirements-dev.txt
python firmware/creative-pebble-pro/tools/build.py
python firmware/creative-pebble-pro/tools/test_pebble_rgb_persistent.py
python firmware/creative-pebble-pro/tools/test_pebble_bootloader.py
```

Build uses the shipped patch manifest to reverse the patch, recovers and hash-checks the exact stock container/application, reassembles the source and requires a byte-for-byte match to the shipped tested image. It derives the 32-byte affine encoding from paired SDFS members, validates parameter CRCs and both application slots, and checks that only the existing application FAT member changes. Inputs, intermediate payloads and reports go under this directory's ignored build/. No device access occurs.

The instruction tests execute injected MIPS32 code with native callees/ISA returns stubbed: 24 persistence cases, 20 bad restore records, 262 legacy RGB cases, 1,048 mode/color cases and 17,030 pulse ticks. The boot test executes the supplied selector with synthetic flash, stops at application entry, and stubs ROM/peripherals; all eight cases pass. Historical native-parser readback/config checks are retained in validation/, explicitly separate from newly reproducible checks. Property getters may use cached state; readback alone cannot prove NVRAM durability.

## USB protocol and helper

See [PROTOCOL.md](PROTOCOL.md). The optional Windows helper uses OpenRGB's installed HID library: `python firmware/creative-pebble-pro/tools/pebble_rgb.py --read`. `--mode pulse FF0000 --save` explicitly changes and saves lighting; it is never run by build/CI. Runtime plugins require this v3 firmware and reject stock/older builds.
