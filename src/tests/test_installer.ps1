# Runs without elevation, registry edits, scheduled tasks, or hardware access.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\windows\Bridge.ps1') -Library
function Assert($Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Assert-Throws([scriptblock]$Code, [string]$Expected) {
    try { & $Code } catch { Assert ($_.ToString() -like ('*' + $Expected + '*')) ('Wrong error: ' + $_); return }
    throw ('Expected failure: ' + $Expected)
}
$buildRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\build'))
$testRoot = Join-Path $buildRoot ('installer-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
try {
    $payload = Join-Path $testRoot 'payload'
    $installed = Join-Path $testRoot 'installed'
    New-Item -ItemType Directory -Force -Path $payload,$installed,(Join-Path $payload '_internal') | Out-Null
    foreach ($name in @('VColorOpenRGBBridge.exe','Bridge.ps1','Install.cmd','Uninstall.cmd','Start.cmd','Stop.cmd','bridge-config.example.json','README.txt','LICENSE','THIRD_PARTY_NOTICES.md','PYTHON-LICENSE.txt','PYINSTALLER-COPYING.txt','bridge-config.json')) {
        'payload' | Set-Content -LiteralPath (Join-Path $payload $name)
    }
    'runtime' | Set-Content -LiteralPath (Join-Path $payload '_internal\python312.dll')
    $script:BridgeRoot = $payload
    Copy-Installation $installed
    Assert (Test-Path -LiteralPath (Join-Path $installed '_internal\python312.dll')) 'Bundled runtime was not installed'
    Assert (-not (Test-Path -LiteralPath (Join-Path $installed 'bridge-config.json'))) 'Unresolved source configuration was copied'
    Assert (-not (Test-Path -LiteralPath (Join-Path $installed 'src'))) 'Source copied into application folder'

    # A listener is not proof that this executable started.
    function Get-BridgeListener { @([pscustomobject]@{ OwningProcess=123 }) }
    $script:FakeOwner = [pscustomobject]@{ ExecutablePath=(Join-Path $testRoot 'wrong.exe') }
    function Get-CimInstance { $script:FakeOwner }
    function Start-Sleep { }
    $script:BridgeRoot = $installed
    Assert-Throws { Wait-Bridge 6743 (Join-Path $installed 'VColorOpenRGBBridge.exe') 1 } 'did not start'
    $script:FakeOwner.ExecutablePath = Join-Path $installed 'VColorOpenRGBBridge.exe'
    Wait-Bridge 6743 $script:FakeOwner.ExecutablePath 1

    # Only the public install location's task and processes may be stopped.
    $script:TaskName = 'test-task'
    $script:UserSid = 'test-user'
    function Get-InstallDirectory { $installed }
    $script:FakeTask = [pscustomobject]@{ State='Ready'; Actions=@([pscustomobject]@{
        Execute=(Join-Path $PSHOME 'powershell.exe');
        Arguments=('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $installed 'Bridge.ps1') + '" -Action Start')
    }) }
    function Get-ScheduledTask { $script:FakeTask }
    Assert ($null -ne (Get-BridgeTask)) 'Installed task was not recognized'
    $originalArguments = $script:FakeTask.Actions[0].Arguments
    $script:FakeTask.Actions[0].Arguments = '-File "C:\old\Start-OpenRGB-RAM.ps1"'
    Assert-Throws { Get-BridgeTask } 'unrecognized action'
    $script:FakeTask.Actions[0].Arguments = $originalArguments
    $script:StoppedIds = @()
    function Get-Process {
        param($Name,$Id)
        if ($Id -eq $PID) { return [pscustomobject]@{SessionId=7} }
        $handle = [pscustomobject]@{}
        $handle | Add-Member ScriptMethod WaitForExit { param($Timeout) return $true }
        $handle
    }
    function Get-CimInstance {
        [pscustomobject]@{ProcessId=123;SessionId=7;ExecutablePath=(Join-Path $installed 'VColorOpenRGBBridge.exe')}
        [pscustomobject]@{ProcessId=456;SessionId=7;ExecutablePath=(Join-Path $payload 'VColorOpenRGBBridge.exe')}
        [pscustomobject]@{ProcessId=789;SessionId=8;ExecutablePath=(Join-Path $installed 'VColorOpenRGBBridge.exe')}
    }
    function Stop-Process { param($Id); $script:StoppedIds += $Id }
    Stop-BridgeInstances $script:FakeTask
    Assert ($script:StoppedIds.Count -eq 1 -and $script:StoppedIds[0] -eq 123) 'Stopped a different application folder or session'

    # Exercise setup with all OS mutations mocked; real files record saved state.
    $script:FakeTask = $null
    $script:TaskStarted = $false
    $script:TaskRemoved = $false
    $script:FailReadiness = $false
    $script:OpenRGBRunning = $false
    $script:PortOccupied = $false
    $script:Copied = $false
    $script:BridgeRoot = $payload
    $script:PortableOpenRGB = Join-Path $payload 'OpenRGB'
    function Get-Process { if ($script:OpenRGBRunning) { [pscustomobject]@{Name='OpenRGB'} } }
    function Get-BridgeConfig {
        if ($script:BridgeRoot -eq $installed) { throw 'OpenRGB discovery unavailable after relocation' }
        [pscustomobject]@{ port=6744; smbus_port=1; openrgb_dir=$script:PortableOpenRGB }
    }
    function Get-BridgeListener { if ($script:PortOccupied) { @([pscustomobject]@{OwningProcess=123}) } else { @() } }
    function Stop-BridgeInstances { $script:Stopped = $true }
    function Copy-Installation { $script:Copied = $true }
    function Save-Client {
        param($Operation,$Path,$Port)
        $script:ClientOperation=$Operation; $script:ClientPort=$Port; $script:ClientPath=$Path
        [pscustomobject]@{ settings_file=(Join-Path $testRoot 'OpenRGB.json') }
    }
    function Get-ItemProperty { $null }
    function New-ItemProperty { }
    function Remove-ItemProperty { }
    function New-Item { }
    function New-ScheduledTaskAction {
        param($Execute,$Argument,$WorkingDirectory)
        $script:RegisteredArguments = $Argument
        [pscustomobject]@{}
    }
    function New-ScheduledTaskTrigger { [pscustomobject]@{} }
    function New-ScheduledTaskPrincipal { [pscustomobject]@{} }
    function New-ScheduledTaskSettingsSet { [pscustomobject]@{} }
    function Register-ScheduledTask { }
    function Unregister-ScheduledTask { $script:TaskRemoved = $true }
    function Start-ScheduledTask { $script:TaskStarted = $true }
    function Wait-Bridge { if ($script:FailReadiness) { throw 'readiness verification failed' } }
    $script:PortOccupied = $true
    Assert-Throws { Install-Bridge } 'already in use'
    Assert (-not $script:Copied) 'Copied files before checking port'
    $script:PortOccupied = $false
    $result = Install-Bridge
    Assert $script:TaskStarted 'Installer did not start task'
    Assert ($script:RegisteredArguments -like '*-WindowStyle Hidden*') 'Startup task would leave a visible window'
    Assert ($script:BridgeRoot -eq $installed) 'Task should use installed files, not the download'
    Assert ($result -like '*Installed and running*') 'Installer did not report verified success'
    $savedConfig = Get-Content -LiteralPath (Join-Path $installed 'bridge-config.json') -Raw | ConvertFrom-Json
    Assert ($savedConfig.openrgb_dir -eq $script:PortableOpenRGB) 'Discovered absolute OpenRGB path was lost'
    Assert ($savedConfig.port -eq 6744 -and $savedConfig.smbus_port -eq 1) 'Selected ports were lost'
    $stateFile = Join-Path $installed 'install-state.json'
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    Assert ($state.sdk_port -eq 6744) 'Uninstall port was not saved'
    $script:Copied = $false
    Assert-Throws { Install-Bridge } 'already installed'
    Assert (-not $script:Copied) 'Repeated installation changed files'

    # Uninstall works without OpenRGB discovery or a readable runtime config.
    'invalid config' | Set-Content -LiteralPath (Join-Path $installed 'bridge-config.json')
    $script:Stopped = $false
    Uninstall-Bridge | Out-Null
    Assert $script:Stopped 'Uninstall did not stop the installed bridge'
    Assert $script:TaskRemoved 'Uninstall did not remove startup'
    Assert ($script:ClientOperation -eq 'remove' -and $script:ClientPort -eq 6744) 'Uninstall did not use its saved SDK port'
    Assert ($script:ClientPath -eq $state.settings_file) 'Uninstall did not use its saved settings file'
    Assert (-not (Test-Path -LiteralPath $stateFile)) 'Successful uninstall did not clear state'

    $script:BridgeRoot = $payload
    $script:FailReadiness = $true
    Assert-Throws { Install-Bridge } 'readiness verification failed'
    $script:OpenRGBRunning = $true
    $script:Copied = $false
    Assert-Throws { Install-Bridge } 'Close OpenRGB completely'
    Assert (-not $script:Copied) 'Installer changed files before checking OpenRGB'
    Write-Output 'First-install, portable-path persistence, task ownership, readiness and discovery-independent uninstall checks passed.'
} finally {
    $resolvedTest = [IO.Path]::GetFullPath($testRoot)
    if (-not $resolvedTest.StartsWith($buildRoot + '\installer-test-')) { throw 'Unsafe test cleanup path' }
    Microsoft.PowerShell.Management\Remove-Item -LiteralPath $resolvedTest -Recurse -Force
}
