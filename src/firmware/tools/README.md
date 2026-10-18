# Firmware tools

Run these commands from the repository root. Hardware tools require Windows, administrator access, and the OpenRGB/PawnIO installation described in [FLASHING.md](../FLASHING.md).

| Command | Purpose | Hardware changes |
| --- | --- | --- |
| `.\src\firmware\Flash-V2.ps1` | Discover controllers, select one, and install the final firmware | Programs the selected RGB controller |
| `python src/firmware/tools/build_firmware.py` | Reproduce the final binary and manifest from the stock reference | None |
| `python src/firmware/tools/validate_final.py` | Run emulation, discovery/selection, and installer fault tests | None |
| `python src/firmware/tools/analyze_firmware.py <image.bin>` | Write focused ARM Thumb disassembly beside the input image | None |

Use `-Python '<path to python.exe>'` with the PowerShell launcher when Python is not on PATH. `flash_v2.py` supports `--help`; direct flashing through Python requires `--execute`, and the PowerShell launcher is recommended because it also checks administrator access and common conflicting processes.

Use `-OpenRGBDir '<OpenRGB directory>'` for a portable or custom OpenRGB folder. Direct Python calls accept `--openrgb-dir '<OpenRGB directory>'`. The default is the OpenRGB folder under Program Files.

Flashing, including discovery and selection, uses only Python's standard library. Offline validation needs Unicorn; disassembly needs Capstone. Install both with:

```powershell
python -m pip install -r src/firmware/requirements-dev.txt
```

Shared implementation and offline test modules live in `_internal/`. They are imported by the supported commands and are not standalone user tools. They retain strict original-image guards, selected-address routing, bounded page writes, staged-payload/readback checks, and incomplete-update guards. `transport.py` loads the user's installed PawnIO runtime without dynamically rewriting source.

Firmware/reference files live in `../images/`; generated flash/test reports live in `../reports/`. The captured settings block used only by offline tests lives in `../tests/fixtures/`. Keep reports when investigating a failure. No command automatically flashes every detected module, changes DDR SPD, or performs a full-image recovery.
