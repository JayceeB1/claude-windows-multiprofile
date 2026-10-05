<#
.SYNOPSIS
    Tests launch arguments, child config isolation and fail-closed control flow.
.DESCRIPTION
    No Pester, installation, real directories, real processes or credentials.
    Tests the real ProcessStartInfo builder and orchestration with in-memory
    doubles at OS boundaries. Requires Windows PowerShell 5.1 or PowerShell 7.
.EXAMPLE
    .\tests\Test-Launcher.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'These tests require Windows. No Linux runtime PASS is claimed.'
}
$launcher = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\Launch-Claude.ps1'
$tokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $launcher, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
Write-Host 'Preflight PASS: launcher parsed before import.'
# Guard imports against accidentally running the upstream top-level launcher.
$statements = @($ast.EndBlock.Statements | Where-Object {
    $_ -isnot [System.Management.Automation.Language.FunctionDefinitionAst]
})
if ($statements.Count -ne 1 -or
    $statements[0] -isnot [System.Management.Automation.Language.IfStatementAst] -or
    $statements[0].Clauses[0].Item1.Extent.Text -ne '$MyInvocation.InvocationName -ne ''.''') {
    throw 'Launcher import must contain only functions and the dot-source guard.'
}
. $launcher
$script:assertions = 0
function Assert-Equal {
    param([string]$Name, $Expected, $Actual)
    if ($Expected -cne $Actual) { throw "$Name -- expected <$Expected>, got <$Actual>" }
    $script:assertions++
}
function Assert-Failure {
    param([string]$Name, [scriptblock]$Action, [string]$Pattern)
    $caught = $null
    try { & $Action | Out-Null } catch { $caught = $_ }
    if (-not $caught -or $caught.Exception.Message -notmatch $Pattern) {
        throw "$Name did not fail for the expected reason ($Pattern)."
    }
    $script:assertions++
}

# Local overrides are visible only during this call; production functions return
# afterward. No entry point to actual directory creation / process launch is used.
function Invoke-LaunchFixture {
    param([hashtable]$Arguments, [string]$Failure = '')
    $state = [pscustomobject]@{
        Discoveries = 0; Starts = 0; Info = $null
        Directories = [System.Collections.Generic.List[string]]::new()
    }
    function Get-ClaudeExecutable {
        $state.Discoveries++
        if ($Failure -eq 'discovery') { throw 'FAKE_DISCOVERY_FAILURE' }
        return 'C:\Program Files\Claude\app\Claude.exe'
    }
    function Initialize-ClaudeDirectory {
        param([string]$Path)
        if ($Failure -eq 'directory' -or
            ($Failure -eq 'config-directory' -and $state.Directories.Count -eq 1)) {
            throw 'FAKE_DIRECTORY_FAILURE'
        }
        $state.Directories.Add($Path)
    }
    function Start-ClaudeDesktopProcess {
        param([System.Diagnostics.ProcessStartInfo]$StartInfo)
        $state.Starts++
        $state.Info = $StartInfo
        if ($Failure -eq 'start') { throw 'FAKE_START_FAILURE' }
    }
    $caught = $null
    try { Invoke-ClaudeLauncher @Arguments } catch { $caught = $_ }
    [pscustomobject]@{ State = $state; Error = $caught }
}

function Invoke-DiscoveryFixture {
    param([string]$Mode)
    $state = [pscustomobject]@{ Queries = 0; Scans = 0 }
    function Get-AppxPackage {
        [CmdletBinding()]
        param([string]$Name)
        $state.Queries++
        if ($Mode -eq 'fallback') { throw 'FAKE_APPX_UNAVAILABLE' }
        if ($Mode -eq 'missing') { return }
        [pscustomobject]@{ Version = [version]'1.0'; InstallLocation = 'C:\Packages\Old' }
        [pscustomobject]@{ Version = [version]'2.0'; InstallLocation = 'C:\Packages\New' }
    }
    function Test-Path {
        param([string]$LiteralPath, [string]$PathType)
        return $Mode -ne 'missing'
    }
    function Get-ChildItem {
        [CmdletBinding()]
        param([string]$Path)
        Assert-Equal 'fallback remains MSIX only' 'C:\Program Files\WindowsApps\Claude_*__*\app\Claude.exe' $Path
        $state.Scans++
        if ($Mode -eq 'fallback') {
            [pscustomobject]@{ FullName = 'C:\Packages\Fallback\app\Claude.exe' }
        }
    }
    $caught = $null; $exe = $null
    try { $exe = Get-ClaudeExecutable } catch { $caught = $_ }
    [pscustomobject]@{ State = $state; Error = $caught; Exe = $exe }
}

$originalConfig = [Environment]::GetEnvironmentVariable('CLAUDE_CONFIG_DIR', 'Process')
$probeName = 'CLAUDE_LAUNCHER_TEST_SENTINEL'
$originalProbe = [Environment]::GetEnvironmentVariable($probeName, 'Process')
try {
    $env:CLAUDE_CONFIG_DIR = 'C:\Config\Unrelated Parent'
    [Environment]::SetEnvironmentVariable($probeName, 'preserve-me', 'Process')
    $exe = 'C:\Program Files\Claude\app\Claude.exe'
    $cases = @(
        @{ Path = 'C:\Profiles\A'; Expected = '--user-data-dir="C:\Profiles\A"' },
        @{ Path = 'C:\Users\John Doe\Claude [A]'; Expected = '--user-data-dir="C:\Users\John Doe\Claude [A]"' },
        @{ Path = 'C:\Profiles\A\'; Expected = '--user-data-dir="C:\Profiles\A\\"' },
        @{ Path = 'C:\'; Expected = '--user-data-dir="C:\\"' },
        @{ Path = '\\server\share\Profile A'; Expected = '--user-data-dir="\\server\share\Profile A"' },
        @{ Path = 'C:\Profiles\one\..\two'; Expected = '--user-data-dir="C:\Profiles\two"' }
    )
    # Exercise Unicode without depending on the script's PS 5.1 text encoding.
    $unicodePath = 'C:\Profiles\Andr' + [char]0xE9
    $cases += @{ Path = $unicodePath; Expected = '--user-data-dir="' + $unicodePath + '"' }
    foreach ($case in $cases) {
        $info = New-ClaudeStartInfo -ExecutablePath $exe -ProfileDir $case.Path
        Assert-Equal 'one quoted profile argument' $case.Expected $info.Arguments
        Assert-Equal 'executable not mixed into arguments' $exe $info.FileName
        Assert-Equal 'no shell activation' $false $info.UseShellExecute
        Assert-Equal 'stock does not inherit config' $false $info.EnvironmentVariables.ContainsKey('CLAUDE_CONFIG_DIR')
        Assert-Equal 'unrelated environment retained' 'preserve-me' $info.EnvironmentVariables[$probeName]
        Assert-Equal 'builder does not change parent' 'C:\Config\Unrelated Parent' $env:CLAUDE_CONFIG_DIR
    }
    $a = New-ClaudeStartInfo $exe 'C:\Profiles\A' 'C:\Config\A'
    $b = New-ClaudeStartInfo $exe 'C:\Profiles\B' 'C:\Config\B'
    Assert-Equal 'A child config' 'C:\Config\A' $a.EnvironmentVariables['CLAUDE_CONFIG_DIR']
    Assert-Equal 'B child config' 'C:\Config\B' $b.EnvironmentVariables['CLAUDE_CONFIG_DIR']
    $b.EnvironmentVariables['CLAUDE_CONFIG_DIR'] = 'C:\Config\Changed B'
    Assert-Equal 'A and B environment copies are independent' 'C:\Config\A' $a.EnvironmentVariables['CLAUDE_CONFIG_DIR']
    Assert-Equal 'parent survives A then B' 'C:\Config\Unrelated Parent' $env:CLAUDE_CONFIG_DIR
    $empty = New-ClaudeStartInfo $exe 'C:\Profiles\Stock' ''
    Assert-Equal 'explicit empty selects stock too' $false $empty.EnvironmentVariables.ContainsKey('CLAUDE_CONFIG_DIR')

    foreach ($bad in @('', ' ', 'relative', 'C:relative', '\root-relative', 'HKCU:\Software',
        'C:\Bad" --injected', "C:\Bad`nPath", 'C:\Bad*Path', '\\?\C:\device')) {
        Assert-Failure 'invalid profile' { New-ClaudeStartInfo $exe $bad } 'ProfileDir'
        if ($bad -ne '') {
            Assert-Failure 'invalid config' { New-ClaudeStartInfo $exe 'C:\Good' $bad } 'ConfigDir'
        }
    }
    Assert-Failure 'missing exe' { New-ClaudeStartInfo '' 'C:\Good' } 'executable'
    $argsA = @{ ProfileDir = 'C:\Profiles\A'; ConfigDir = 'C:\Config\A' }
    foreach ($mode in @('', 'discovery', 'directory', 'config-directory', 'start')) {
        $result = Invoke-LaunchFixture $argsA $mode
        Assert-Equal 'one discovery' 1 $result.State.Discoveries
        Assert-Equal 'parent intact after orchestration' 'C:\Config\Unrelated Parent' $env:CLAUDE_CONFIG_DIR
        if ($mode -eq '') {
            Assert-Equal 'successful orchestration' $null $result.Error
            Assert-Equal 'one start' 1 $result.State.Starts
            Assert-Equal 'two directory requests' 2 $result.State.Directories.Count
            Assert-Equal 'profile directory requested' 'C:\Profiles\A' $result.State.Directories[0]
            Assert-Equal 'config directory requested' 'C:\Config\A' $result.State.Directories[1]
            Assert-Equal 'child receives chosen config' 'C:\Config\A' $result.State.Info.EnvironmentVariables['CLAUDE_CONFIG_DIR']
        } else {
            $reason = if ($mode -eq 'config-directory') { 'directory' } else { $mode }
            Assert-Equal 'specific OS failure propagates' ('FAKE_' + $reason.ToUpper() + '_FAILURE') $result.Error.Exception.Message
            $expectedStarts = if ($mode -eq 'start') { 1 } else { 0 }
            $expectedDirs = switch ($mode) { 'start' { 2 } 'config-directory' { 1 } default { 0 } }
            Assert-Equal 'no start after prerequisite failure' $expectedStarts $result.State.Starts
            Assert-Equal 'no unexpected directory request' $expectedDirs $result.State.Directories.Count
        }
    }
    $stock = Invoke-LaunchFixture @{ ProfileDir = 'C:\Profiles\Stock' }
    Assert-Equal 'stock creates only profile directory' 1 $stock.State.Directories.Count
    Assert-Equal 'stock start strips inherited config' $false $stock.State.Info.EnvironmentVariables.ContainsKey('CLAUDE_CONFIG_DIR')
    foreach ($badArgs in @(@{}, @{ ProfileDir = 'relative' },
        @{ ProfileDir = 'C:\Good'; ConfigDir = 'relative' })) {
        $result = Invoke-LaunchFixture $badArgs
        Assert-Equal 'invalid input rejected before discovery' 0 $result.State.Discoveries
        Assert-Equal 'invalid input creates nothing' 0 $result.State.Directories.Count
        Assert-Equal 'invalid input never starts' 0 $result.State.Starts
        Assert-Equal 'invalid input reports an error' $true ($null -ne $result.Error)
    }
    foreach ($mode in 'normal', 'fallback', 'missing') {
        $result = Invoke-DiscoveryFixture $mode
        Assert-Equal 'MSIX discovery queried once' 1 $result.State.Queries
        if ($mode -eq 'normal') {
            Assert-Equal 'newest package selected' 'C:\Packages\New\app\Claude.exe' $result.Exe
            Assert-Equal 'no unnecessary fallback scan' 0 $result.State.Scans
            Assert-Equal 'discovery succeeded' $null $result.Error
        } elseif ($mode -eq 'fallback') {
            Assert-Equal 'MSIX fallback used' 'C:\Packages\Fallback\app\Claude.exe' $result.Exe
            Assert-Equal 'one fallback scan' 1 $result.State.Scans
            Assert-Equal 'fallback succeeded' $null $result.Error
        } else {
            Assert-Equal 'missing app returns no exe' $null $result.Exe
            Assert-Equal 'missing app is an explicit error' $true ($result.Error.Exception.Message -like '*not found*')
        }
    }
    [Environment]::SetEnvironmentVariable('CLAUDE_CONFIG_DIR', $null, 'Process')
    $info = New-ClaudeStartInfo $exe 'C:\Profiles\Stock'
    Assert-Equal 'absent parent config stays absent in child' $false $info.EnvironmentVariables.ContainsKey('CLAUDE_CONFIG_DIR')
    $info = New-ClaudeStartInfo $exe 'C:\Profiles\A' 'C:\Config\A'
    Assert-Equal 'explicit config works with absent parent' 'C:\Config\A' $info.EnvironmentVariables['CLAUDE_CONFIG_DIR']
    Assert-Equal 'absent parent is not populated' $null ([Environment]::GetEnvironmentVariable('CLAUDE_CONFIG_DIR', 'Process'))
    Write-Host "PASS: $script:assertions launcher assertions; no real process, profile or Desktop runtime tested."
} finally {
    [Environment]::SetEnvironmentVariable('CLAUDE_CONFIG_DIR', $originalConfig, 'Process')
    [Environment]::SetEnvironmentVariable($probeName, $originalProbe, 'Process')
}
