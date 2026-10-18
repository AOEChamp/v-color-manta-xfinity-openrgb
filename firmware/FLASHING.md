# Flash the custom RGB firmware

## Requirements

- Supported stock firmware for V-COLOR Manta XFinity **TMXFL1660830WWK**, ENE **6K7732** RGB controller (chip-ID bytes `77 30`, signature `A8 32 16 E8 8C`). A matching identity alone does not establish firmware compatibility; the installer also checks stock firmware pages.
- Windows x64, Python 3.12, and administrator PowerShell.
- OpenRGB installed at `C:\Program Files\OpenRGB`, with the installed PawnIO driver, `PawnIOLib.dll`, and signed `SmbusPIIX4.bin` module. Python flashing tools require no pip packages.
- AMD PIIX4 SMBus port 0. Discovery is limited to RGB controller addresses `0x70..0x73`. Intel transport and other bus configurations are not supported by these tools.

Close OpenRGB, V-COLOR software, GCC/RGB Fusion, SignalRGB, the bridge, and other RGB/SMBus software. Keep power stable. Flashing changes the RGB controller's program flash and can leave lighting unusable if interrupted. These tools do not write DDR SPD.

## 1. Inspect the available controllers

Open **PowerShell as Administrator** and change to the repository root:

```powershell
python firmware/tools/list_dimms.py
```

The listing shows each responding RGB controller's hardware identity, SMBus address, chip ID, signature, and whether its identity is supported. It also lists the DIMM slot, manufacturer, and part number reported by Windows.

Windows does not reliably map its DIMM slot/part names to RGB controller addresses. The tool therefore shows those inventories separately. Select by the discovered controller entry; do not infer a slot-to-address mapping. Unsupported entries cannot be selected for flashing. Discovery performs register reads and register-pointer selection; it does not apply lighting, save settings, reset the controller, or program flash.

## 2. Verify the firmware file

```powershell
Get-FileHash firmware/images/vcolor-7730-e000-v2.bin -Algorithm SHA256
```

Expected SHA-256:

```text
0263291e72b23c074d9048ecb626b915ffe5e48c8a53264a82ef8530627b7df3
```

## 3. Select and flash one controller

```powershell
.\firmware\Flash-V2.ps1
```

If Python is not on PATH:

```powershell
.\firmware\Flash-V2.ps1 -Python 'C:\Path\To\python.exe'
```

The script lists the controllers again. Enter the **number of the controller you want to flash**, or press Enter to cancel. Only one controller is flashed per run. No address argument is required. It rechecks discovery after your selection, then performs the stock-image preflight before programming. Already-patched firmware fails stock preflight; this tool is not a reinstall or rollback utility.

The launcher checks administrator access and common competing RGB processes. It does not automatically close applications. The Python tool uses a shared SMBus mutex and permits programming only on your selected controller.

## 4. Check the result

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

## Save lighting and check persistence

Flashing preserves the existing saved-settings block and does not apply or save a new color. Apply your desired lighting through compatible software and explicitly use its save function for this custom firmware. Ordinary OpenRGB Apply is not a save. A complete OpenRGB Save integration is not yet packaged in this repository.

To test persistence, prevent RGB software from applying settings automatically, shut down and start the computer, and observe the LEDs before software applies anything. Record whether AC power was removed. A controller CPU restart alone does not establish power-loss persistence. Do not reapply a color before observing startup restoration.

## If flashing stops or fails

Keep the JSON report and console error. Do not bypass stock preflight or retry blindly. After a partial update or uncertain mailbox completion, the installer deliberately blocks CPU exit. Do not reset or remove power while programming may still be active; diagnose the recorded state before choosing a recovery action.

Do not flash the entire `.bin` over the controller: it contains default bytes in the live settings range. The bundled stock dump is a reference program image, not a verified full-chip recovery backup. No automatic rollback or full-chip recovery tool is supplied.

Implementation details and porting guidance are in [DEVELOPMENT.md](DEVELOPMENT.md). The supported command list is in [tools/README.md](tools/README.md).
