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
    'existing configuration' | Set-Content -LiteralPath (Join-Path $installed 'bridge-config.json')
    $script:BridgeRoot = $payload
    Copy-Installation $installed
    Assert (Test-Path -LiteralPath (Join-Path $installed '_internal\python312.dll')) 'Bundled runtime was not installed'
    Assert ((Get-Content -LiteralPath (Join-Path $installed 'bridge-config.json')) -eq 'existing configuration') 'Upgrade overwrote user configuration'
    Assert (-not (Test-Path -LiteralPath (Join-Path $installed 'src'))) 'Source copied into application folder'

    # A process listening on the right port is not proof that this bridge started.
    function Get-BridgeListener { @([pscustomobject]@{ OwningProcess=123 }) }
    $script:FakeOwner = [pscustomobject]@{ ExecutablePath=(Join-Path $testRoot 'wrong.exe') }
    function Get-CimInstance { $script:FakeOwner }
    function Start-Sleep { }
    $script:BridgeRoot = $installed
    Assert-Throws { Wait-Bridge 6743 (Join-Path $installed 'VColorOpenRGBBridge.exe') 1 } 'did not start'
    $script:FakeOwner.ExecutablePath = Join-Path $installed 'VColorOpenRGBBridge.exe'
    Wait-Bridge 6743 $script:FakeOwner.ExecutablePath 1

    # Accept an older location for migration, but reject unrelated task actions.
    $script:TaskName = 'test-task'
    $script:UserSid = 'test-user'
    $script:FakeTask = [pscustomobject]@{ State='Ready'; Actions=@([pscustomobject]@{
        Execute=(Join-Path $PSHOME 'powershell.exe');
        Arguments=('-NoProfile -File "' + (Join-Path $testRoot 'old\Start-OpenRGB-RAM.ps1') + '" -NoGui')
    }) }
    function Get-ScheduledTask { $script:FakeTask }
    Assert ($null -ne (Get-PreviousTask)) 'Old bridge task should be replaceable'
    $originalArguments = $script:FakeTask.Actions[0].Arguments
    $script:FakeTask.Actions[0].Arguments = '-File "unrelated.ps1"'
    Assert-Throws { Get-PreviousTask } 'unrecognized action'
    $script:FakeTask.Actions[0].Arguments = $originalArguments

    # Exercise installation control flow with all Windows mutations mocked.
    $script:Stopped = $false
    $script:TaskStarted = $false
    $script:FailReadiness = $false
    $script:OpenRGBRunning = $false
    $script:InstallTarget = $installed
    function Get-InstallDirectory { $script:InstallTarget }
    function Get-Process { if ($script:OpenRGBRunning) { [pscustomobject]@{Name='OpenRGB'} } }
    function Get-BridgeConfig { [pscustomobject]@{ port=6743; openrgb_dir=(Join-Path $testRoot 'OpenRGB') } }
    function Stop-BridgeInstances { $script:Stopped = $true }
    function Copy-Installation { }
    function Save-Client { [pscustomobject]@{ settings_file=(Join-Path $testRoot 'OpenRGB.json') } }
    function Get-ItemProperty { $null }
    function New-ItemProperty { }
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
    function Start-ScheduledTask { $script:TaskStarted = $true }
    function Wait-Bridge { if ($script:FailReadiness) { throw 'readiness verification failed' } }
    $result = Install-Bridge
    Assert $script:Stopped 'Upgrade did not stop previous bridge'
    Assert $script:TaskStarted 'Installer did not start task'
    Assert ($script:RegisteredArguments -like '*-WindowStyle Hidden*') 'Startup task would leave a visible PowerShell window'
    Assert ($script:BridgeRoot -eq $installed) 'Task should use installed files, not the download'
    Assert ($result -like '*Installed and running*') 'Installer did not report verified success'
    $script:FailReadiness = $true
    Assert-Throws { Install-Bridge } 'readiness verification failed'
    $script:OpenRGBRunning = $true
    $script:Stopped = $false
    Assert-Throws { Install-Bridge } 'Close OpenRGB completely'
    Assert (-not $script:Stopped) 'Installer changed running state before checking OpenRGB'
    Write-Output 'Installer migration, installed location, configuration preservation and readiness checks passed.'
} finally {
    $resolvedTest = [IO.Path]::GetFullPath($testRoot)
    if (-not $resolvedTest.StartsWith($buildRoot + '\installer-test-')) { throw 'Unsafe test cleanup path' }
    Microsoft.PowerShell.Management\Remove-Item -LiteralPath $resolvedTest -Recurse -Force
}
