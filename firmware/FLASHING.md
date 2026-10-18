# Flash the custom RGB firmware

## Requirements

- Supported stock firmware for V-COLOR Manta XFinity **TMXFL1660830WWK**, ENE **6K7732** RGB controller (chip-ID bytes `77 30`, signature `A8 32 16 E8 8C`). A matching identity alone does not establish firmware compatibility; the installer also checks stock firmware pages.
- Windows x64, Python 3.12, and administrator PowerShell.
- OpenRGB with the installed PawnIO driver, `PawnIOLib.dll`, and signed `SmbusPIIX4.bin` module. The default folder is `C:\Program Files\OpenRGB`; use `-OpenRGBDir` for another installation folder. Python flashing tools require no pip packages.
- AMD PIIX4 SMBus port 0. Discovery is limited to RGB controller addresses `0x70..0x73`. Intel transport and other bus configurations are not supported by these tools.

Close OpenRGB, V-COLOR software, GCC/RGB Fusion, SignalRGB, the bridge, and other RGB/SMBus software. Keep power stable. Flashing changes the RGB controller's program flash and can leave lighting unusable if interrupted. These tools do not write DDR SPD.

## 1. Run the flashing script

```powershell
.\firmware\Flash-V2.ps1
```

For a portable or custom OpenRGB installation:

```powershell
.\firmware\Flash-V2.ps1 -OpenRGBDir 'D:\Apps\OpenRGB'
```

The direct Python equivalent is `python firmware/tools/flash_v2.py --execute --openrgb-dir 'D:\Apps\OpenRGB'`. Relative installation paths are resolved from the directory where you launch the command, including when using the PowerShell launcher.

If Python is not on PATH:

```powershell
.\firmware\Flash-V2.ps1 -Python 'C:\Path\To\python.exe'
```

The script lists responding RGB controllers with hardware identity, SMBus address, chip ID, signature, and support status. It also lists Windows DIMM slot/manufacturer/part names. Enter the **number of the controller you want to flash**, or press Enter to cancel. Only one controller is flashed per run. No address argument is required. It rechecks discovery after your selection, then performs the stock-image preflight before programming. Already-patched firmware fails stock preflight; this tool is not a reinstall or rollback utility.

Windows does not reliably map its DIMM slots to RGB controller addresses, so the script shows the inventories separately and does not guess that mapping. Unsupported entries cannot be selected. Discovery does not apply lighting, save settings, reset controllers, or program flash. The list is displayed once; the identity check after selection runs silently.

The launcher checks administrator access and common competing RGB processes. The installer checks the packaged firmware against its reproducible build before programming. It does not automatically close applications. The Python tool uses a shared SMBus mutex and permits programming only on your selected controller.

## 2. Check the result

A successful run prints:

```text
Firmware installed and verified. Application resumed; saved settings preserved.
```

The full JSON report is saved to `firmware/reports/v2-install-<UTC timestamp>.json`; the tool prints its exact path. Generated reports are ignored by Git.

Check that the process exited successfully, the report has no `error`, and these fields are true:

- `all_bounded_readbacks_match_candidate`
- `protection_restored`
- `application_resumed`
- `all_other_modules_unchanged`

`control_present` says whether another compatible controller was available as a control. If present, `control_unchanged` must also be true. With only one controller, there is no independent control observation.

After verifying the result, rerun the launcher and select a different supported stock controller if needed.

## Upgrade v2 to v3: stored-color Random Flicker

E000 v3 retains v2 persistence and makes mode 13 use each LED's stored color instead of generating its own hues. Use the current bridge for Random Flicker's color controls. The upgrade is available in this repository; the v2 release ZIP does not contain it.

With the same prerequisites and RGB applications closed, run from the repository root in administrator PowerShell:

```powershell
.\firmware\Flash-V3.ps1
```

The launcher accepts the same `-Python` and `-OpenRGBDir` options as the v2 launcher. Select one controller per run. This command upgrades only the exact bundled v2 image to v3; stock controllers must first receive v2. Already-v3, mismatched or partially modified firmware is rejected before flash writes. Reports use `firmware/reports/v3-install-<UTC timestamp>.json`.

Only pages `3480` (Random Flicker renderer) and `2000` (checksums, written last) are programmed. The existing saved-settings bytes are captured and verified unchanged; they need not match the reference image. Check the usual success fields above plus `saved_settings_preserved`. The same incomplete-update and uncertain-mailbox guards apply.

## Save lighting and check persistence

Flashing preserves the existing saved-settings block and does not apply or save a new color. Apply your desired lighting through compatible software and explicitly use its save function for this custom firmware. Ordinary OpenRGB Apply is not a save. The [OpenRGB bridge](../bin/README.txt) now provides Save to Device for this firmware.

To test persistence, prevent RGB software from applying settings automatically, shut down and start the computer, and observe the LEDs before software applies anything. Record whether AC power was removed. A controller CPU restart alone does not establish power-loss persistence. Do not reapply a color before observing startup restoration.

## If flashing stops or fails

Keep the JSON report and console error. Do not bypass stock preflight or retry blindly. After a partial update or uncertain mailbox completion, the installer deliberately blocks CPU exit. Do not reset or remove power while programming may still be active; diagnose the recorded state before choosing a recovery action.

Do not flash the entire `.bin` over the controller: it contains default bytes in the live settings range. The bundled stock dump is a reference program image, not a verified full-chip recovery backup. No automatic rollback or full-chip recovery tool is supplied.

Implementation details and porting guidance are in [DEVELOPMENT.md](DEVELOPMENT.md). The supported command list is in [tools/README.md](tools/README.md).
