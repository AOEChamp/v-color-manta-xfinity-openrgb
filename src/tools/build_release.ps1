param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent)
try {
    & $Python -m unittest discover -s src/tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File src/tests/test_installer.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Installer tests failed.' }
    & $Python -m PyInstaller --noconfirm --clean --onedir --name VColorOpenRGBBridge --distpath build/runtime --workpath build/pyinstaller --specpath build --paths src/bridge src/bridge/openrgb_bridge.py
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
    & $Python src/tools/package_release.py
    if ($LASTEXITCODE -ne 0) { throw 'Folder preparation failed.' }
} finally { Pop-Location }
