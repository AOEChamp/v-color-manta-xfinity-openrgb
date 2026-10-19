param(
    [ValidateSet('Install','Uninstall')][string]$Action = 'Install',
    [string]$OpenRGBDir = 'C:\Program Files\OpenRGB',
    [string]$SettingsDir = (Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'OpenRGB'),
    [string]$ExpectedUser,
    [switch]$Library
)
$ErrorActionPreference = 'Stop'
$payloadNames = @('VColorRamPlugin.dll','PebbleProPlugin.dll')

function Read-Settings([string]$Path) {
    Add-Type -AssemblyName System.Web.Extensions
    $parser = New-Object System.Web.Script.Serialization.JavaScriptSerializer
    $parser.MaxJsonLength = 16777216
    # Case-sensitive dictionaries preserve OpenRGB's differently cased keys.
    return ,($parser.DeserializeObject([IO.File]::ReadAllText($Path)))
}

function Convert-BridgeConnection($Settings) {
    if ($Settings.ContainsKey('Client') -and $Settings['Client'] -and $Settings['Client'].ContainsKey('clients')) {
        $Settings['Client']['clients'] = @($Settings['Client']['clients'] | Where-Object {
            -not ($_.ContainsKey('ip') -and $_.ContainsKey('port') -and $_['ip'] -eq '127.0.0.1' -and $_['port'] -eq 6743)
        })
    }
    # Explicitly enable the installed plugins, preserving unrelated entries.
    if (-not $Settings.ContainsKey('Plugins')) { $Settings['Plugins'] = @{} }
    if (-not $Settings['Plugins']) { $Settings['Plugins'] = @{} }
    $entries = @($Settings['Plugins']['plugins'] | Where-Object {
        $_ -and $_['name'] -notin @('V-Color Manta XFinity RAM','Creative Pebble Pro')
    })
    $entries += @(
        @{name='V-Color Manta XFinity RAM'; enabled=$true; description='Eight LEDs per DIMM, hardware effects and explicit Save to Device through PawnIO.'},
        @{name='Creative Pebble Pro'; enabled=$true; description='Mode, color and Save to Device for Pebble Pro custom firmware v3. Both rings share one zone.'}
    )
    $Settings['Plugins']['plugins'] = $entries
    return ,$Settings
}

function Write-Settings($Settings,[string]$Path) {
    [IO.File]::WriteAllText($Path,($Settings | ConvertTo-Json -Depth 100),(New-Object Text.UTF8Encoding($false)))
}

if ($Library) { return }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if ($ExpectedUser -and $identity.User.Value -ne $ExpectedUser) { throw 'Elevate as the same Windows user that runs OpenRGB.' }
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Action ' + $Action +
        ' -OpenRGBDir "' + $OpenRGBDir + '" -SettingsDir "' + $SettingsDir + '" -ExpectedUser ' + $identity.User.Value
    $child = Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -PassThru -Wait -ArgumentList $arguments
    exit $child.ExitCode
}
$executable = Join-Path $OpenRGBDir 'OpenRGB.exe'
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { throw 'OpenRGB.exe not found; pass -OpenRGBDir.' }
$sessionId = (Get-Process -Id $PID).SessionId
if (Get-Process OpenRGB -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $sessionId }) {
    throw 'Exit the OpenRGB desktop application, including its tray icon, before installing or removing plugins. The session-0 service may remain running.'
}
$pluginsDir = Join-Path $SettingsDir 'plugins'
if ($Action -eq 'Uninstall') {
    foreach ($name in $payloadNames) {
        $target = Join-Path $pluginsDir $name
        if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target }
    }
    Write-Output 'Plugins removed. The old bridge remains disabled; backups are retained. Firmware was not changed.'
    exit 0
}
foreach ($name in @('PawnIOLib.dll','SmbusPIIX4.bin','hidapi-hotplug.dll')) {
    if (-not (Test-Path -LiteralPath (Join-Path $OpenRGBDir $name))) { throw "OpenRGB dependency missing: $name" }
}
foreach ($name in $payloadNames) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $name))) { throw "Missing plugin payload: $name" }
}
$settingsPath = Join-Path $SettingsDir 'OpenRGB.json'
$settings = if (Test-Path -LiteralPath $settingsPath) { Read-Settings $settingsPath } else { @{} }
$null = Convert-BridgeConnection $settings
$taskName = 'VColorOpenRGBBridge-' + $identity.User.Value
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$bridgeRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\VColorOpenRGBBridge'
$bridgeScript = Join-Path $bridgeRoot 'Bridge.ps1'
if ($task -and ($task.Actions.Count -ne 1 -or $task.Actions[0].Arguments -notlike ('*"' + $bridgeScript + '"*'))) {
    throw 'Unexpected bridge startup task; no changes made.'
}
$backup = Join-Path $SettingsDir ('plugin-backups\' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $backup,$pluginsDir | Out-Null
$existing = @()
foreach ($name in $payloadNames) {
    if (Test-Path -LiteralPath (Join-Path $pluginsDir $name)) {
        Copy-Item -LiteralPath (Join-Path $pluginsDir $name) -Destination (Join-Path $backup $name)
        $existing += $name
    }
}
$hadSettings = Test-Path -LiteralPath $settingsPath
if ($hadSettings) { Copy-Item -LiteralPath $settingsPath -Destination (Join-Path $backup 'OpenRGB.json') }
$changedTask = $false
$changedElevation = $false
try {
    if ($task) {
        Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath (Join-Path $backup 'bridge-task.xml')
        Disable-ScheduledTask -TaskName $taskName | Out-Null
        $changedTask = $true
    }
    if (Test-Path -LiteralPath $bridgeScript) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $bridgeScript -Action Stop
        if ($LASTEXITCODE -ne 0) { throw 'Could not stop the old bridge' }
    }
    if (Get-Process VColorOpenRGBBridge -ErrorAction SilentlyContinue) { throw 'Stop all RAM bridge instances before installing.' }
    foreach ($name in $payloadNames) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $pluginsDir $name) -Force }
    Write-Settings $settings $settingsPath
    $layers = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers'
    $oldFlags = (Get-ItemProperty -LiteralPath $layers -Name $executable -ErrorAction SilentlyContinue).$executable
    if ($oldFlags -notmatch 'RUNASADMIN') {
        New-Item -Path $layers -Force | Out-Null
        $newFlags = if ($oldFlags) { $oldFlags + ' RUNASADMIN' } else { '~ RUNASADMIN' }
        New-ItemProperty -LiteralPath $layers -Name $executable -Value $newFlags -PropertyType String -Force | Out-Null
        $changedElevation = $true
    }
    @{openrgb=$executable; previous_elevation_flags=$oldFlags; bridge_task=$taskName; previous_bridge_enabled=[bool]($task -and $task.Settings.Enabled)} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backup 'migration.json')
    Write-Output "Installed both native plugins. Backup: $backup. Open OpenRGB and accept its administrator prompt. No firmware was flashed."
} catch {
    if ($changedElevation) {
        if ($oldFlags) { Set-ItemProperty -LiteralPath $layers -Name $executable -Value $oldFlags }
        else { Remove-ItemProperty -LiteralPath $layers -Name $executable }
    }
    foreach ($name in $payloadNames) {
        $target = Join-Path $pluginsDir $name
        if ($name -in $existing) { Copy-Item -LiteralPath (Join-Path $backup $name) -Destination $target -Force }
        elseif (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target }
    }
    if ($hadSettings) { Copy-Item -LiteralPath (Join-Path $backup 'OpenRGB.json') -Destination $settingsPath -Force }
    elseif (Test-Path -LiteralPath $settingsPath) { Remove-Item -LiteralPath $settingsPath }
    if ($changedTask -and $task.Settings.Enabled) { Enable-ScheduledTask -TaskName $taskName | Out-Null }
    if ($changedTask -and $task.State -eq 'Running') { Start-ScheduledTask -TaskName $taskName }
    throw
}
