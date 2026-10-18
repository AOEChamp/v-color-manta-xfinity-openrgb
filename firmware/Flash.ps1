param(
    [string]$Python = 'python',
    [string]$OpenRGBDir = 'C:\Program Files\OpenRGB'
)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run PowerShell as Administrator.' }
$competing = @(Get-Process | Where-Object { $_.ProcessName -match '^(GCC|OpenRGB|VColorOpenRGBBridge|SignalRgb|SignalRgbLauncher|hid|v-color|RGBFusion.*)$' })
if ($competing.Count) { throw 'Close competing RGB applications before flashing.' }
$OpenRGBDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OpenRGBDir)
Push-Location $PSScriptRoot
try {
    & $Python tools/flash.py --execute --openrgb-dir $OpenRGBDir
    if ($LASTEXITCODE -ne 0) { throw 'Flash failed. Preserve the report and follow FLASHING.md failure guidance.' }
} finally { Pop-Location }
