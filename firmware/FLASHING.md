# Flash the final custom firmware

## Supported setup

This package supports only the exact stock image for V-COLOR TMXFL1660830WWK described in [DEVELOPMENT.md](DEVELOPMENT.md). It discovers responding RGB controllers in the validated `0x70..0x73` range on PIIX4 port 0 and lets you select one. It is not a generic DIMM updater. Already-patched firmware will fail stock preflight; do not bypass that check.

Flashing changes the DIMM's RGB-controller program flash and can leave lighting unusable if interrupted. The supplied stock program dump is a reference backup, not a verified full-chip recovery image. Never write this image to DDR SPD.

Requirements:

- Windows x64, administrator PowerShell, and Python 3.12 available as `python` (or provide its full path with `-Python`).
- OpenRGB installed at `C:\Program Files\OpenRGB`, with its installed PawnIO driver, `PawnIOLib.dll`, and signed `SmbusPIIX4.bin`.
- Close OpenRGB, V-COLOR software, GCC/RGB Fusion, SignalRGB, the bridge, and any other RGB/SMBus application. Keep power stable throughout.

The necessary project flashing scripts and their Python transport dependencies are included under `tools/` and `bridge/`. Flashing uses the Python standard library. The external driver/library/module come from the user's OpenRGB installation and are not bundled; copying files alone would not install the driver. No proprietary vendor flashing utility is required.

## Verify the package

From the repository root:

```powershell
Get-FileHash firmware/images/vcolor-7730-e000-v2.bin -Algorithm SHA256
```

Expected: `0263291e72b23c074d9048ecb626b915ffe5e48c8a53264a82ef8530627b7df3`.

## Flash one target

Open PowerShell as Administrator, change to the repository root, then run:

```powershell
.\firmware\Flash-V2.ps1
```

If Python is not on PATH:

```powershell
.\firmware\Flash-V2.ps1 -Python 'C:\Path\To\python.exe'
```

Inspect the generated `firmware/images/v2-install-*.json`. Success requires `all_bounded_readbacks_match_candidate`, `protection_restored`, `application_resumed`, and `control_unchanged` to be true, with no error. The process must exit successfully. After checking the first target, rerun the selector to flash another supported stock module:

```powershell
.\firmware\Flash-V2.ps1
```

Before flashing, the script lists RGB controller identities and Windows DIMM slot/manufacturer/part names, then asks for a controller number. Windows slots are not assumed to map to RGB addresses. An address adapter permits mutations only to the selected controller. Other compatible controllers are checked for unchanged state. A single compatible controller can also be selected; its report records that no control module was present. Stock preflight compares bounded firmware pages with the reference; it is not a full live-image hash. The selected identity and known boot vector are also checked, with identity revalidation after selection. Reproducible local image construction is checked before programming.

The installer enters the CPU bootloader using stop/run register `0202` and flags `0606`. It stages and verifies each complete 128-byte payload twice, writes pages `4180`, `4200`, `6B00`, `6E00`, `6E80`, then `2000`, and reads each back immediately. A second bounded verification covers changed pages, neighbors, vector and all 384 saved-settings bytes (2,304 bytes per pass). Protections are restored before application exit. It does not overwrite E000 settings or automatically apply/save lighting.

## Save and check persistence

Flashing enables the controller's existing save mechanism; it does not save a chosen color. After applying the desired lighting through a compatible controller implementation, command `AA` at `E0A0` requests a runtime save. Ordinary OpenRGB apply is not a save, and this repository does not yet package a final OpenRGB Save integration.

For an explicit static-red test on target 71, close other RGB software and run from `firmware/` in administrator PowerShell:

```powershell
python tools/save_red_e000.py --v2 --execute
```

This deliberately applies red, issues one save, and verifies the saved block. For target 73, the separately invoked test also performs a CPU restart:

```powershell
python tools/second_dimm_e000_v2.py --stage save-restart --execute
```

This applies and saves red on 73, restarts its controller CPU, and checks restored registers without reapplying lighting afterward. A CPU restart is not power removal. Inspect reports for successful verification and unchanged control module. For a power-persistence test, shut down and start the computer with RGB software prevented from applying settings; observe visible output. Record whether AC power was removed. Do not reapply a color before observing startup restoration.

## If an operation fails

Preserve the generated JSON report. Do not retry blindly, bypass preflight, or flash the whole `.bin`: it contains default bytes in the saved-settings range. After partial programming or uncertain mailbox completion, the installer intentionally blocks CPU exit; do not reset or power-cycle while a flash request may still be active. Diagnose the recorded state before deciding on recovery. No automated rollback or full-chip recovery is supplied.
