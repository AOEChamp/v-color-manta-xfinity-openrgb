param(
    [string]$Python = 'python',
    [string]$OpenRGBDir = 'C:\Program Files\OpenRGB'
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Flash-V2.ps1') -Python $Python -OpenRGBDir $OpenRGBDir -FirmwareVersion '3'
