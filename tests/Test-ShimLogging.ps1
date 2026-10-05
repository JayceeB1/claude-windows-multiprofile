<#
.SYNOPSIS
    Proves that shim dispatch logs/output never include synthetic callback data.
.DESCRIPTION
    Parser preflight, then the real shim with in-memory OS/IO doubles. No real
    process, profile, credential, registry, log or marker is read/written. The
    dispatched URL is checked unchanged. Both terminating and nonterminating
    errors carry synthetic secrets to test the error-reporting boundary.
.EXAMPLE
    .\tests\Test-ShimLogging.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'These tests require Windows; no Linux runtime PASS is claimed.'
}
$shim = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\ClaudeOpenShim.ps1'
$tokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $shim, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
# Only path assignments and the explicit entry guard may run during import.
$top = @($ast.EndBlock.Statements | Where-Object {
    $_ -isnot [System.Management.Automation.Language.FunctionDefinitionAst]
})
if ($top.Count -ne 4 -or
    $top[3] -isnot [System.Management.Automation.Language.IfStatementAst] -or
    $top[3].Clauses[0].Item1.Extent.Text -ne '$MyInvocation.InvocationName -ne ''.''') {
    throw 'Shim import must remain inert.'
}
for ($i = 0; $i -lt 3; $i++) {
    if ($top[$i] -isnot [System.Management.Automation.Language.AssignmentStatementAst] -or
        $top[$i].Left.Extent.Text -ne @('$Base', '$TargetFile', '$LogFile')[$i]) {
        throw 'Unexpected top-level statement.'
    }
}
$exits = @($ast.FindAll({ param($n)
    $n -is [System.Management.Automation.Language.ExitStatementAst]
}, $true))
if ($exits.Count -ne 1 -or $exits[0].Extent.Text -ne 'exit (Invoke-ClaudeShim -Url $Url)') {
    throw 'Only the entry guard may exit; return the dispatch status unchanged.'
}
Write-Host 'Preflight PASS: shim parsed; guarded import and exit contract checked.'
. $shim

$script:assertions = 0
$script:scenarios = 0
$eventCodes = 'MISSING_URL|TARGET_READ_FAILED|APP_DISCOVERY_FAILED|APP_NOT_FOUND|' +
    'ARGUMENT_BUILD_FAILED|LAUNCH_REQUESTED|LAUNCH_FAILED|RESET_FAILED|DISPATCH_COMPLETE'
$logPattern = '\A\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d event=(' + $eventCodes +
    ') target=(unknown|stock|profile)\z'
function Assert-Equal {
    param([string]$Name, $Expected, $Actual)
    # Deliberately do not render failed values: even the test reporter stays safe.
    if ($Expected -cne $Actual) { throw "ASSERTION_FAILED: $Name" }
    $script:assertions++
}
function Assert-LogSchema {
    param([string]$Line)
    if ($Line -cnotmatch $logPattern) { throw 'LOG_SCHEMA_LEAK' }
    $script:assertions++
}

function Invoke-ShimFixture {
    param([string]$Callback, [string]$Mode = '', [string]$Marker = 'C:\Profiles\Private [B]')
    $state = [pscustomobject]@{
        Logs = [System.Collections.Generic.List[string]]::new()
        Starts = [System.Collections.Generic.List[object]]::new()
        Resets = [System.Collections.Generic.List[string]]::new()
        Reads = 0; Queries = 0; LogAttempts = 0; Output = @()
    }
    # Every IO boundary is replaced; no real log or installation is used.
    function Test-Path {
        [CmdletBinding()]
        param([string]$LiteralPath)
        if ($LiteralPath -eq $TargetFile) {
            if ($Mode -eq 'marker-probe') { throw "RAW_MARKER_ERROR $Callback" }
            return $Mode -ne 'no-marker'
        }
        if ($Mode -eq 'exe-probe') { throw "RAW_EXE_ERROR $Callback" }
        return $Mode -ne 'missing-exe'
    }
    function Get-Content {
        [CmdletBinding()]
        param([string]$LiteralPath, [int]$First)
        $state.Reads++
        if ($LiteralPath -ne $TargetFile -or $First -ne 1) { throw 'UNEXPECTED_READ' }
        if ($Mode -eq 'marker-read') { throw "RAW_READ_ERROR $Callback $Marker" }
        return $Marker
    }
    function Get-AppxPackage {
        [CmdletBinding()]
        param([string]$Name)
        $state.Queries++
        if ($Mode -eq 'discovery') { throw "RAW_DISCOVERY_ERROR $Callback" }
        if ($Mode -eq 'no-app') { return }
        [pscustomobject]@{ Version = [version]'1.0'; InstallLocation = 'C:\Packages\Old' }
        [pscustomobject]@{ Version = [version]'2.0'; InstallLocation = 'C:\Packages\New' }
    }
    function Add-Content {
        [CmdletBinding()]
        param([string]$LiteralPath, [string]$Value)
        $state.LogAttempts++
        if ($LiteralPath -ne $LogFile) { throw 'UNEXPECTED_LOG_PATH' }
        if ($Mode -eq 'log-write' -or
            ($Mode -eq 'completion-log' -and $state.LogAttempts -eq 2)) {
            throw "RAW_LOG_ERROR $Callback $Marker"
        }
        $state.Logs.Add($Value)
    }
    function Start-Process {
        [CmdletBinding()]
        param([string]$FilePath, [string]$ArgumentList)
        $state.Starts.Add([pscustomobject]@{ File = $FilePath; Args = $ArgumentList })
        if ($Mode -eq 'launch') { throw "RAW_START_ERROR $ArgumentList" }
        if ($Mode -eq 'launch-nonterminating') { Write-Error "RAW_START_ERROR $ArgumentList" }
    }
    function Set-Content {
        [CmdletBinding()]
        param([string]$LiteralPath, [string]$Value, [string]$Encoding)
        if ($LiteralPath -ne $TargetFile -or $Encoding -ne 'ASCII') { throw 'UNEXPECTED_RESET' }
        if ($Mode -eq 'reset') { throw "RAW_RESET_ERROR $Callback" }
        $state.Resets.Add($Value)
    }
    if ($Mode -eq 'builder') {
        function Get-ClaudeLaunchArgString {
            param([string]$Target, [string]$Url)
            throw "RAW_BUILDER_ERROR $Target $Url"
        }
    }
    # Collect ALL explicit streams, not only success output or route.log writes.
    $state.Output = @(Invoke-ClaudeShim -Url $Callback *>&1)
    return $state
}

function Assert-ShimResult {
    param($Result, [int]$Code, [string[]]$Events, [string]$Kind,
        [int]$Starts = 0, [int]$Resets = 0)
    Assert-Equal 'only the integer status is emitted' 1 $Result.Output.Count
    Assert-Equal 'status is an integer, not an error or secret-bearing object' $true ($Result.Output[0] -is [int])
    Assert-Equal 'dispatch status' $Code $Result.Output[0]
    Assert-Equal 'start count' $Starts $Result.Starts.Count
    Assert-Equal 'reset count' $Resets $Result.Resets.Count
    Assert-Equal 'event count' $Events.Count $Result.Logs.Count
    for ($i = 0; $i -lt $Events.Count; $i++) {
        Assert-LogSchema $Result.Logs[$i]
        Assert-Equal 'event sequence and target kind' $true (
            $Result.Logs[$i].EndsWith(('event={0} target={1}' -f $Events[$i], $Kind)))
    }
    if ($Resets) { Assert-Equal 'reset value unchanged' 'default' $Result.Resets[0] }
    $script:scenarios++
}

# No credential is used: sentinels exercise query, fragment, custom key and path.
$callbacks = @(
    'claude://oauth/callback?code=FAKE_CODE&state=FAKE_STATE',
    'claude://oauth/callback#access_token=FAKE_ACCESS&refresh_token=FAKE_REFRESH',
    'claude://FAKE_PATH?unknown=FAKE_CUSTOM&redirect=https%3A%2F%2Ffake.invalid%2F#FAKE_FRAGMENT'
)
foreach ($callback in $callbacks) {
    foreach ($marker in @('default', 'C:\Profiles\Private [B]', 'C:\FAKE_TARGET_SECRET')) {
        $result = Invoke-ShimFixture -Callback $callback -Marker $marker
        $kind = if ($marker -eq 'default') { 'stock' } else { 'profile' }
        Assert-ShimResult $result 0 @('LAUNCH_REQUESTED', 'DISPATCH_COMPLETE') $kind 1 1
        $expected = Get-ClaudeLaunchArgString -Target $marker -Url $callback
        Assert-Equal 'complete callback forwarded unchanged' $expected $result.Starts[0].Args
        Assert-Equal 'newest MSIX selected' 'C:\Packages\New\app\Claude.exe' $result.Starts[0].File
        Assert-Equal 'target read once' 1 $result.Reads
    }
}
foreach ($missing in @('', ' ')) {
    $result = Invoke-ShimFixture -Callback $missing
    Assert-ShimResult $result 1 @('MISSING_URL') 'unknown'
    Assert-Equal 'no profile read for missing input' 0 $result.Reads
    Assert-Equal 'no app discovery for missing input' 0 $result.Queries
}
$result = Invoke-ShimFixture -Callback $callbacks[0] -Mode 'no-marker'
Assert-ShimResult $result 0 @('LAUNCH_REQUESTED', 'DISPATCH_COMPLETE') 'stock' 1 1
Assert-Equal 'no read when marker absent' 0 $result.Reads
Assert-Equal 'stock callback arguments unchanged' ('"' + $callbacks[0] + '"') $result.Starts[0].Args

$failureCases = @(
    @{ Mode = 'marker-probe'; Event = 'TARGET_READ_FAILED'; Kind = 'unknown' },
    @{ Mode = 'marker-read'; Event = 'TARGET_READ_FAILED'; Kind = 'unknown' },
    @{ Mode = 'discovery'; Event = 'APP_DISCOVERY_FAILED'; Kind = 'profile' },
    @{ Mode = 'exe-probe'; Event = 'APP_DISCOVERY_FAILED'; Kind = 'profile' },
    @{ Mode = 'no-app'; Event = 'APP_NOT_FOUND'; Kind = 'profile' },
    @{ Mode = 'missing-exe'; Event = 'APP_NOT_FOUND'; Kind = 'profile' },
    @{ Mode = 'builder'; Event = 'ARGUMENT_BUILD_FAILED'; Kind = 'profile' }
)
foreach ($case in $failureCases) {
    $result = Invoke-ShimFixture -Callback $callbacks[1] -Mode $case.Mode
    Assert-ShimResult $result 1 @($case.Event) $case.Kind
}
foreach ($mode in @('launch', 'launch-nonterminating')) {
    $result = Invoke-ShimFixture -Callback $callbacks[2] -Mode $mode
    Assert-ShimResult $result 1 @('LAUNCH_REQUESTED', 'LAUNCH_FAILED') 'profile' 1 0
}
$result = Invoke-ShimFixture -Callback $callbacks[1] -Mode 'reset'
Assert-ShimResult $result 1 @('LAUNCH_REQUESTED', 'RESET_FAILED') 'profile' 1 0
$result = Invoke-ShimFixture -Callback $callbacks[1] -Mode 'log-write'
Assert-ShimResult $result 1 @() 'profile'
Assert-Equal 'log failure does not recurse' 1 $result.LogAttempts
$result = Invoke-ShimFixture -Callback $callbacks[1] -Mode 'completion-log'
Assert-ShimResult $result 1 @('LAUNCH_REQUESTED') 'profile' 1 1
Assert-Equal 'post-dispatch log failure does not recurse' 2 $result.LogAttempts
$result = Invoke-ShimFixture -Callback '' -Mode 'log-write'
Assert-ShimResult $result 1 @() 'unknown'

# Prove the leak guard rejects the old log shape and appended sensitive values.
foreach ($leaky in @(('2026-01-01T00:00:00 C:\Private <- ' + $callbacks[0]),
    ('2026-01-01T00:00:00 event=LAUNCH_FAILED target=profile ' + $callbacks[1]),
    ("2026-01-01T00:00:00 event=DISPATCH_COMPLETE target=profile`n" + $callbacks[2]))) {
    $rejected = $false
    try { Assert-LogSchema $leaky } catch { $rejected = ($_.Exception.Message -eq 'LOG_SCHEMA_LEAK') }
    Assert-Equal 'synthetic leak rejected by schema guard' $true $rejected
}
Write-Host "PASS: $script:scenarios shim scenarios; $script:assertions assertions; no real login, process or filesystem writes."
