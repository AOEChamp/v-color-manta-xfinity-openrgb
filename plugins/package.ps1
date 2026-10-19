$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
foreach ($name in @('VColorRamPlugin.dll','PebbleProPlugin.dll')) {
    Copy-Item -LiteralPath (Join-Path $repo ('build\bin\' + $name)) -Destination (Join-Path $repo ('bin\' + $name)) -Force
}
$hashes = [ordered]@{}
foreach ($relative in @('bin/VColorRamPlugin.dll','bin/PebbleProPlugin.dll','firmware/creative-pebble-pro/images/MF1710-RGB-v3.fw')) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha.ComputeHash([IO.File]::ReadAllBytes((Join-Path $repo $relative)))
        $hashes[$relative] = [BitConverter]::ToString($digest).Replace('-','').ToLowerInvariant()
    } finally { $sha.Dispose() }
}
[IO.File]::WriteAllText((Join-Path $repo 'bin\SHA256SUMS.json'),($hashes | ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
