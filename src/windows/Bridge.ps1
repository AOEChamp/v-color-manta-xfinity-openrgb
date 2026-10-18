param(
    [ValidateSet('Install','Uninstall','Start','Stop')][string]$Action = 'Start',
    [string]$SettingsPath,
    [string]$ExpectedUser,
    [switch]$Library
)
$ErrorActionPreference = 'Stop'
$script:BridgeRoot = $PSScriptRoot

function Get-InstallDirectory {
    Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\VColorOpenRGBBridge'
}

function Get-BridgeConfig {
    $executable = Join-Path $script:BridgeRoot 'VColorOpenRGBBridge.exe'
    if (-not (Test-Path -LiteralPath $executable)) { throw 'Bridge executable missing. Keep all files from bin together.' }
    $json = & $executable --print-config
    if ($LASTEXITCODE -ne 0) { throw 'OpenRGB discovery failed. Check bridge-config.json and your OpenRGB PawnIO installation.' }
    $json | ConvertFrom-Json
}

function Get-BridgeListener([int]$Port) {
    @(Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Get-PreviousTask {
    $task = Get-ScheduledTask -TaskName $script:TaskName -ErrorAction SilentlyContinue
    if ($task) {
        if ($task.Actions.Count -ne 1 -or
            [IO.Path]::GetFileName($task.Actions[0].Execute) -ne 'powershell.exe' -or
            $task.Actions[0].Arguments -notmatch '-File\s+"[^"]+\\(Bridge|Start-OpenRGB-RAM)\.ps1"') {
            throw 'The bridge task has an unrecognized action. It has not been changed.'
        }
    }
    $task
}

function Stop-BridgeInstances([int]$Port, $Task) {
    $session = (Get-Process -Id $PID).SessionId
    $instances = @(Get-CimInstance Win32_Process -Filter "Name='VColorOpenRGBBridge.exe'" | Where-Object SessionId -EQ $session)
    $listeners = Get-BridgeListener $Port
    foreach ($listener in $listeners) {
        $owner = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess)
        if (-not $owner -or $owner.Name -ne 'VColorOpenRGBBridge.exe' -or $owner.SessionId -ne $session) {
            throw "Port $Port is used by another application. Change port in bridge-config.json; no application was stopped."
        }
    }
    if ($Task -and $Task.State -eq 'Running') { Stop-ScheduledTask -TaskName $script:TaskName }
    # Upgrade previous bridge instances for this signed-in user/session only.
    foreach ($process in $instances) {
        $handle = Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
        if ($handle) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
            if (-not $handle.WaitForExit(5000)) { throw 'Previous bridge did not stop; installation files have not been replaced.' }
        }
    }
}

function Copy-Installation([string]$Destination) {
    $source = [IO.Path]::GetFullPath($script:BridgeRoot).TrimEnd('\')
    $target = [IO.Path]::GetFullPath($Destination).TrimEnd('\')
    if ($source -eq $target) { return }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    $files = @('VColorOpenRGBBridge.exe','Bridge.ps1','Install.cmd','Uninstall.cmd','Start.cmd','Stop.cmd',
               'bridge-config.example.json','README.txt','LICENSE','THIRD_PARTY_NOTICES.md',
               'PYTHON-LICENSE.txt','PYINSTALLER-COPYING.txt')
    foreach ($file in $files) {
        Copy-Item -LiteralPath (Join-Path $source $file) -Destination (Join-Path $target $file) -Force
    }
    $runtime = Join-Path $source '_internal'
    if (-not (Test-Path -LiteralPath $runtime -PathType Container)) { throw 'Bundled _internal runtime is missing.' }
    foreach ($file in Get-ChildItem -LiteralPath $runtime -Recurse -File) {
        $relative = $file.FullName.Substring($source.Length + 1)
        $destinationFile = Join-Path $target $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $destinationFile -Parent) | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destinationFile -Force
    }
    $localConfig = Join-Path $source 'bridge-config.json'
    $installedConfig = Join-Path $target 'bridge-config.json'
    if ((Test-Path -LiteralPath $localConfig) -and -not (Test-Path -LiteralPath $installedConfig)) {
        Copy-Item -LiteralPath $localConfig -Destination $installedConfig
    }
}

function Wait-Bridge([int]$Port, [string]$Executable, [int]$Attempts = 60) {
    for ($attempt=0; $attempt -lt $Attempts; $attempt++) {
        foreach ($listener in @(Get-BridgeListener $Port)) {
            $owner = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess)
            if ($owner -and $owner.ExecutablePath -eq $Executable) { return }
        }
        Start-Sleep -Milliseconds 500
    }
    $log = Join-Path $script:BridgeRoot 'logs\bridge.log'
    $detail = Get-Content -LiteralPath $log -Tail 6 -ErrorAction SilentlyContinue
    throw "Bridge did not start on port $Port. $detail"
}

function Start-Bridge {
    $config = Get-BridgeConfig
    $executable = Join-Path $script:BridgeRoot 'VColorOpenRGBBridge.exe'
    if ((Get-BridgeListener $config.port).Count) {
        Wait-Bridge $config.port $executable 1
        return
    }
    $mutex = New-Object Threading.Mutex($false, ('Local\VColorBridge-' + $config.port))
    if (-not $mutex.WaitOne(0)) { $mutex.Dispose(); throw 'Another bridge launcher is active.' }
    $child = $null
    try {
        New-Item -ItemType Directory -Force -Path (Join-Path $script:BridgeRoot 'logs') | Out-Null
        $child = Start-Process -FilePath $executable -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $script:BridgeRoot 'logs\bridge.stdout.log') `
            -RedirectStandardError (Join-Path $script:BridgeRoot 'logs\bridge.log')
        Wait-Bridge $config.port $executable
        $child.WaitForExit()
        if ($child.ExitCode -ne 0) { throw 'Bridge stopped unexpectedly; see logs\bridge.log.' }
    } finally {
        if ($child -and -not $child.HasExited) { Stop-Process -Id $child.Id -Force }
        $mutex.ReleaseMutex()
        $mutex.Dispose()
    }
}

function Save-Client([string]$Operation, [string]$Path) {
    $arguments = @('--configure-client', $Operation)
    if ($Path) { $arguments += @('--settings-file', $Path) }
    $result = & (Join-Path $script:BridgeRoot 'VColorOpenRGBBridge.exe') @arguments
    if ($LASTEXITCODE -ne 0) { throw 'OpenRGB settings could not be updated. See the error above; setup has not completed.' }
    $result | ConvertFrom-Json
}

function Install-Bridge {
    if (Get-Process OpenRGB -ErrorAction SilentlyContinue) { throw 'Close OpenRGB completely (including its tray icon), then run Install.cmd again.' }
    $config = Get-BridgeConfig
    $previous = Get-PreviousTask
    Stop-BridgeInstances $config.port $previous
    $installed = Get-InstallDirectory
    Copy-Installation $installed
    $script:BridgeRoot = $installed
    $config = Get-BridgeConfig
    $stateFile = Join-Path $installed 'install-state.json'
    $state = if (Test-Path -LiteralPath $stateFile) { Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json } else { $null }
    $client = Save-Client 'install' $(if ($SettingsPath) { $SettingsPath } elseif ($state) { $state.settings_file })
    $executable = Join-Path $config.openrgb_dir 'OpenRGB.exe'
    $layers = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers'
    $oldFlags = (Get-ItemProperty -LiteralPath $layers -Name $executable -ErrorAction SilentlyContinue).$executable
    $originalFlags = if ($state -and $state.openrgb_executable -eq $executable) { $state.previous_elevation_flags } else { $oldFlags }
    $newFlags = if ($oldFlags -match 'RUNASADMIN') { $oldFlags } elseif ($oldFlags) { $oldFlags + ' RUNASADMIN' } else { '~ RUNASADMIN' }
    New-Item -Path $layers -Force | Out-Null
    New-ItemProperty -LiteralPath $layers -Name $executable -Value $newFlags -PropertyType String -Force | Out-Null
    @{ settings_file=$client.settings_file; openrgb_executable=$executable; previous_elevation_flags=$originalFlags; installed_elevation_flags=$newFlags } | ConvertTo-Json | Set-Content -LiteralPath $stateFile
    $taskArguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $installed 'Bridge.ps1') + '" -Action Start'
    $action = New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument $taskArguments -WorkingDirectory $installed
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $script:UserSid
    $principal = New-ScheduledTaskPrincipal -UserId $script:UserSid -LogonType Interactive -RunLevel Highest
    $taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $script:TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $taskSettings -Description 'Starts the V-Color OpenRGB RAM bridge at sign-in.' -Force | Out-Null
    Start-ScheduledTask -TaskName $script:TaskName
    Wait-Bridge $config.port (Join-Path $installed 'VColorOpenRGBBridge.exe')
    "Installed and running in $installed. Open OpenRGB normally and accept its administrator prompt. Both RAM devices connect automatically."
}

function Uninstall-Bridge {
    if (Get-Process OpenRGB -ErrorAction SilentlyContinue) { throw 'Close OpenRGB completely, then run Uninstall.cmd again.' }
    $script:BridgeRoot = Get-InstallDirectory
    $config = Get-BridgeConfig
    Stop-BridgeInstances $config.port (Get-PreviousTask)
    Unregister-ScheduledTask -TaskName $script:TaskName -Confirm:$false -ErrorAction SilentlyContinue
    $stateFile = Join-Path $script:BridgeRoot 'install-state.json'
    if (Test-Path -LiteralPath $stateFile) {
        $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        $null = Save-Client 'remove' $state.settings_file
        $layers = 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers'
        $current = (Get-ItemProperty -LiteralPath $layers -Name $state.openrgb_executable -ErrorAction SilentlyContinue).($state.openrgb_executable)
        if ($current -eq $state.installed_elevation_flags) {
            if ($state.previous_elevation_flags) { Set-ItemProperty -LiteralPath $layers -Name $state.openrgb_executable -Value $state.previous_elevation_flags }
            else { Remove-ItemProperty -LiteralPath $layers -Name $state.openrgb_executable -ErrorAction SilentlyContinue }
        }
        Remove-Item -LiteralPath $stateFile
    }
    'Startup and saved connection removed. The stopped application folder and logs can now be deleted.'
}

if ($Library) { return }
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    if ($ExpectedUser -and $identity.User.Value -ne $ExpectedUser) { throw 'Elevate with the same Windows account used for OpenRGB.' }
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Action ' + $Action + ' -ExpectedUser ' + $identity.User.Value
        if ($SettingsPath) { $arguments += ' -SettingsPath "' + $SettingsPath + '"' }
        $setup = Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -Wait -PassThru -ArgumentList $arguments
        exit $setup.ExitCode
    }
    $script:UserSid = $identity.User.Value
    $script:TaskName = 'VColorOpenRGBBridge-' + $script:UserSid
    $message = switch ($Action) {
        Install { Install-Bridge }
        Uninstall { Uninstall-Bridge }
        Start { Start-Bridge }
        Stop { $config=Get-BridgeConfig; Stop-BridgeInstances $config.port (Get-PreviousTask); 'Bridge stopped.' }
    }
    if ($Action -in @('Install','Uninstall')) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show([string]$message, 'V-Color OpenRGB Bridge') | Out-Null
    }
} catch {
    New-Item -ItemType Directory -Force -Path (Join-Path $script:BridgeRoot 'logs') | Out-Null
    ($_ | Out-String) | Set-Content -LiteralPath (Join-Path $script:BridgeRoot 'logs\setup-error.log')
    if ($Action -ne 'Start') {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show([string]$_, 'V-Color Bridge: action failed') | Out-Null
    }
    exit 1
}
