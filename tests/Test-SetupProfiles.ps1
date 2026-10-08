<#
.SYNOPSIS
    Tests Setup.ps1 profile resolution without installing or launching anything.
.DESCRIPTION
    Parses the production parameter block and profile loop, then executes ONLY
    those fragments with in-memory directory/shortcut doubles. No COM, registry,
    MSIX, credentials, profile contents, or real filesystem writes are used.
    Requires Windows PowerShell 5.1 or PowerShell 7 on Windows; no Pester needed.
.PARAMETER SetupPath
    Setup.ps1 under test; defaults to this checkout's production file.
.PARAMETER BaselinePath
    Optional original Setup.ps1. Its hashtable collision must fail specifically
    with a hashtable conversion error. Other failures do not count as regression
    reproduction. CI supplies the pinned upstream file.
.EXAMPLE
    .\tests\Test-SetupProfiles.ps1
#>
[CmdletBinding()]
param(
    [string]$SetupPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\Setup.ps1'),
    [string]$BaselinePath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'These path tests require Windows. No cross-platform PASS is claimed.'
}
$script:assertions = 0
function Assert-Equal {
    param([string]$Name, $Expected, $Actual)
    if ($Expected -cne $Actual) {
        throw "$Name -- expected <$Expected>, got <$Actual>"
    }
    $script:assertions++
}

function Get-ProfileLoop {
    param([string]$Path)
    $tokens = $null; $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        (Resolve-Path -LiteralPath $Path).Path, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
    $loops = @($ast.EndBlock.Statements | Where-Object {
        $_ -is [System.Management.Automation.Language.ForEachStatementAst] -and
        $_.Variable.VariablePath.UserPath -eq 'name' -and
        $_.Condition.Extent.Text -eq '$Profile'
    })
    if ($loops.Count -ne 1 -or -not $ast.ParamBlock) {
        throw 'Expected exactly one top-level profile loop and the real parameter block.'
    }
    # Do not execute the installer's MSIX/icon/COM/registry/copy/serialization code.
    # Fail closed if a future edit adds an unexpected command to the tested loop.
    $commands = @($loops[0].FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.CommandAst]
    }, $true))
    foreach ($command in $commands) {
        if ($command.GetCommandName() -notin @('Join-Path', 'Write-Host', 'New-Item', 'Out-Null')) {
            throw "Unexpected command in profile loop: $($command.Extent.Text)"
        }
    }
    $preamble = @'
$ErrorActionPreference = 'Stop'
$profileMap = [ordered]@{}
'@
    $epilogue = @'
[pscustomobject]@{ Profiles = $profileMap; DataOverrides = $DataDir; ConfigOverrides = $ConfigDir }
'@
    [scriptblock]::Create($ast.ParamBlock.Extent.Text + "`n" + $preamble + "`n" +
        $loops[0].Extent.Text + "`n" + $epilogue)
}

function Invoke-ProfileFixture {
    param([scriptblock]$Loop, [hashtable]$Arguments = @{})
    $created = [System.Collections.Generic.List[string]]::new()
    $shortcuts = [System.Collections.Generic.List[object]]::new()
    # Shadow directory creation; do not create even the synthetic test root.
    function New-Item {
        param([string]$ItemType, [switch]$Force, [string]$Path)
        if ($ItemType -ne 'Directory' -or -not $Force) { throw 'Unexpected New-Item use.' }
        $created.Add($Path)
    }
    $wsh = [pscustomobject]@{ Shortcuts = $shortcuts }
    $wsh | Add-Member ScriptMethod CreateShortcut {
        param([string]$Path)
        $item = [pscustomobject]@{
            Path = $Path; TargetPath = ''; Arguments = ''; IconLocation = ''
            Description = ''; WorkingDirectory = ''; Saved = $false
        }
        $item | Add-Member ScriptMethod Save { $this.Saved = $true }
        $this.Shortcuts.Add($item)
        return $item
    }
    $desktop = Join-Path $env:USERPROFILE 'Desktop'
    $binDir = Join-Path $env:USERPROFILE 'ClaudeProfiles\bin'
    $vbs = Join-Path $binDir 'launch.vbs'
    $armPath = Join-Path $binDir 'Arm-ClaudeLogin.ps1'
    $iconLocation = (Join-Path $binDir 'claude.ico') + ',0'
    $result = & $Loop @Arguments
    [pscustomobject]@{
        Profiles = $result.Profiles
        DataOverrides = $result.DataOverrides; ConfigOverrides = $result.ConfigOverrides
        Directories = $created; Shortcuts = $shortcuts; BinDir = $binDir; Vbs = $vbs
    }
}

function Assert-Profile {
    param($Result, [string]$Name, [string]$Data, [string]$Config, [bool]$Default = $false)
    $entry = $Result.Profiles[$Name]
    Assert-Equal "$Name data" $Data $entry.dataDir
    Assert-Equal "$Name config" $Config $entry.configDir
    Assert-Equal "$Name default flag" $Default $entry.isDefault
    Assert-Equal "$Name data creation" $true ($Result.Directories.Contains($Data))
    if ($Config) { Assert-Equal "$Name config creation" $true ($Result.Directories.Contains($Config)) }
    $shortcut = @($Result.Shortcuts | Where-Object { $_.Description -eq "Claude Desktop - $Name profile" })
    Assert-Equal "$Name shortcut count" 1 $shortcut.Count
    $expectedArgs = '"{0}" "{1}"' -f $Result.Vbs, $Data
    if ($Config) { $expectedArgs += ' "{0}"' -f $Config }
    Assert-Equal "$Name shortcut arguments" $expectedArgs $shortcut[0].Arguments
    Assert-Equal "$Name shortcut saved" $true $shortcut[0].Saved
    Assert-Equal "$Name shortcut executable" (Join-Path $env:WINDIR 'System32\wscript.exe') $shortcut[0].TargetPath
    Assert-Equal "$Name working directory" $Result.BinDir $shortcut[0].WorkingDirectory
    Assert-Equal "$Name stable icon" ((Join-Path $Result.BinDir 'claude.ico') + ',0') $shortcut[0].IconLocation
}

function Assert-HashtableCollision {
    param([string]$Name, [scriptblock]$Loop)
    $caught = $null
    try { $null = Invoke-ProfileFixture -Loop $Loop }
    catch { $caught = $_ }
    if (-not $caught -or $caught.Exception.ToString() -notmatch 'System\.Collections\.Hashtable') {
        throw "$Name did not reproduce the expected hashtable conversion failure."
    }
    Write-Host "PASS: $Name rejected specifically for a hashtable conversion failure."
    $script:assertions++
}

$environmentNames = @('USERPROFILE', 'APPDATA', 'WINDIR')
$originalEnvironment = @{}
foreach ($key in $environmentNames) {
    $originalEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}
$root = Join-Path ([IO.Path]::GetTempPath()) ('Claude Profile Test ' + [guid]::NewGuid().ToString('N'))
try {
    $env:USERPROFILE = Join-Path $root 'User With Spaces'
    $env:APPDATA = Join-Path $env:USERPROFILE 'AppData\Roaming'
    $env:WINDIR = Join-Path $root 'Windows'
    $loop = Get-ProfileLoop -Path $SetupPath
    Write-Host "Preflight PASS: Setup parsed; profile loop selected without installation."

    if ($BaselinePath) {
        Assert-HashtableCollision -Name 'Pinned upstream baseline' -Loop (Get-ProfileLoop -Path $BaselinePath)
    }
    # Independently prove that either old variable name is caught by the harness.
    foreach ($variable in 'DataDir', 'ConfigDir') {
        $mutant = [scriptblock]::Create($loop.ToString().Replace('$profile' + $variable, '$' + $variable))
        Assert-HashtableCollision -Name "$variable collision mutant" -Loop $mutant
    }

    $result = Invoke-ProfileFixture -Loop $loop
    Assert-Equal 'default profile count' 2 $result.Profiles.Count
    Assert-Equal 'default directory count' 4 $result.Directories.Count
    foreach ($name in 'Work', 'Personal') {
        Assert-Profile $result $name (Join-Path $env:APPDATA "Claude-$name") `
            (Join-Path $env:USERPROFILE ('.claude-' + $name.ToLower()))
    }
    Assert-Equal 'DataDir stays a hashtable' $true ($result.DataOverrides -is [hashtable])
    Assert-Equal 'ConfigDir stays a hashtable' $true ($result.ConfigOverrides -is [hashtable])

    # Stock first AND stock last: no previous iteration may destroy either map.
    foreach ($order in @(@('Personal', 'Work'), @('Work', 'Personal'))) {
        $result = Invoke-ProfileFixture -Loop $loop -Arguments @{
            Profile = $order; DefaultProfile = 'personal'
        }
        Assert-Profile $result 'Personal' (Join-Path $env:APPDATA 'Claude') '' $true
        Assert-Profile $result 'Work' (Join-Path $env:APPDATA 'Claude-Work') `
            (Join-Path $env:USERPROFILE '.claude-work')
        Assert-Equal 'stock config is not created' 3 $result.Directories.Count
    }

    $data = @{ Personal = (Join-Path $env:APPDATA 'Custom Personal'); Work = (Join-Path $env:APPDATA 'Custom Work') }
    $config = @{ Personal = (Join-Path $root 'Config A'); Work = (Join-Path $root 'Config B') }
    $dataBefore = $data | ConvertTo-Json -Compress
    $configBefore = $config | ConvertTo-Json -Compress
    $arguments = @{ DataDir = $data; ConfigDir = $config; LoginShortcuts = $true }
    $result = Invoke-ProfileFixture -Loop $loop -Arguments $arguments
    foreach ($name in 'Work', 'Personal') { Assert-Profile $result $name $data[$name] $config[$name] }
    Assert-Equal 'caller DataDir unchanged' $dataBefore ($data | ConvertTo-Json -Compress)
    Assert-Equal 'caller ConfigDir unchanged' $configBefore ($config | ConvertTo-Json -Compress)
    Assert-Equal 'both sign-in shortcuts created' 4 $result.Shortcuts.Count
    foreach ($name in 'Work', 'Personal') {
        $signin = @($result.Shortcuts | Where-Object { $_.Path -like "*Claude ($name) - Sign in.lnk" })
        Assert-Equal "$name sign-in count" 1 $signin.Count
        Assert-Equal "$name sign-in saved" $true $signin[0].Saved
        Assert-Equal "$name sign-in executable" `
            (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') $signin[0].TargetPath
        $expected = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Profile "{1}" -Launch' -f `
            (Join-Path $result.BinDir 'Arm-ClaudeLogin.ps1'), $name
        Assert-Equal "$name sign-in arguments" $expected $signin[0].Arguments
    }
    $again = Invoke-ProfileFixture -Loop $loop -Arguments $arguments
    Assert-Equal 'repeat invocation keeps mapping' ($result.Profiles | ConvertTo-Json -Depth 5 -Compress) `
        ($again.Profiles | ConvertTo-Json -Depth 5 -Compress)

    # One override only; an explicit empty ConfigDir must remain supported.
    $result = Invoke-ProfileFixture -Loop $loop -Arguments @{
        ConfigDir = @{ personal = '' }; DataDir = @{ work = $data.Work }
        LoginShortcuts = $true; NoProtocolRouting = $true
    }
    Assert-Profile $result 'Work' $data.Work (Join-Path $env:USERPROFILE '.claude-work')
    Assert-Profile $result 'Personal' (Join-Path $env:APPDATA 'Claude-Personal') ''
    Assert-Equal 'NoProtocolRouting suppresses sign-in shortcuts' 2 $result.Shortcuts.Count
    Assert-Equal 'empty config causes no empty-path directory creation' $false ($result.Directories.Contains(''))

    # Overrides also apply to the explicitly selected stock profile.
    $result = Invoke-ProfileFixture -Loop $loop -Arguments @{
        DefaultProfile = 'Work'; DataDir = $data; ConfigDir = $config
    }
    Assert-Profile $result 'Work' $data.Work $config.Work $true
    Assert-Profile $result 'Personal' $data.Personal $config.Personal
    Assert-Equal 'no real test root created' $false (Test-Path -LiteralPath $root)
    Write-Host "PASS: $script:assertions assertions; no installation, login or Desktop runtime tested."
} finally {
    foreach ($key in $environmentNames) {
        [Environment]::SetEnvironmentVariable($key, $originalEnvironment[$key], 'Process')
    }
}
