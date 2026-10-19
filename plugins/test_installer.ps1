# No elevation, registry, scheduled-task or device access.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\bin\Plugins.ps1') -Library
$testDir = Join-Path $PSScriptRoot ('..\build\installer-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $testDir | Out-Null
$path = Join-Path $testDir 'OpenRGB.json'
try {
    '{"Case":{"x":1},"case":{"x":2},"Client":{"clients":[{"ip":"127.0.0.1","port":6743},{"ip":"127.0.0.1","port":6742},{"ip":"192.0.2.1","port":6743}]},"Plugins":{"plugins":[{"name":"Unrelated","enabled":false},{"name":"Creative Pebble Pro","enabled":false}]}}' |
        Set-Content -LiteralPath $path -Encoding ascii
    $settings = Read-Settings $path
    $settings = Convert-BridgeConnection $settings
    Write-Settings $settings $path
    $actual = Read-Settings $path
    if ($actual['Case']['x'] -ne 1 -or $actual['case']['x'] -ne 2) { throw 'Differently cased keys were lost' }
    if ($actual['Client']['clients'].Count -ne 2 -or $actual['Client']['clients'][0]['port'] -ne 6742) { throw 'Wrong SDK clients removed' }
    if ($actual['Plugins']['plugins'].Count -ne 3 -or $actual['Plugins']['plugins'][0]['enabled']) { throw 'Unrelated plugin changed' }
    $again = Convert-BridgeConnection $actual
    if ($again['Plugins']['plugins'].Count -ne 3) { throw 'Repeated migration duplicates plugins' }
    $empty = Convert-BridgeConnection @{}
    if ($empty['Plugins']['plugins'].Count -ne 2) { throw 'New configuration not supported' }
    $nullable = Read-Settings $path
    $nullable['Plugins']=$null
    $nullable['Client']=$null
    $nullable=Convert-BridgeConnection $nullable
    if ($nullable['Plugins']['plugins'].Count -ne 2) { throw 'Null plugin configuration not supported' }
    Write-Output 'PASS plugin installer settings migration, case preservation, unrelated entries, idempotence and empty settings'
} finally {
    # Delete only the exact generated files, without recursive path deletion.
    Remove-Item -LiteralPath $path -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $testDir
}
