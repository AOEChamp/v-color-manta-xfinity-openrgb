param(
    [Parameter(Mandatory=$true)][ValidateSet('0x71','0x73')][string]$Target,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run PowerShell as Administrator.' }
$competing = @(Get-Process | Where-Object { $_.ProcessName -match '^(GCC|OpenRGB|VColorOpenRGBBridge|SignalRgb|SignalRgbLauncher|hid|v-color|RGBFusion.*)$' })
if ($competing.Count) { throw 'Close competing RGB applications before flashing.' }
Push-Location $PSScriptRoot
try {
    & $Python tools/flash_v2.py --target $Target --execute
    if ($LASTEXITCODE -ne 0) { throw 'Flash failed. Preserve the report and follow FLASHING.md failure guidance.' }
} finally { Pop-Location }
