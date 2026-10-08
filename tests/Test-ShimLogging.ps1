<#
.SYNOPSIS
    Tests explicit routing, child config, one-shot state and secret-free logs.
.DESCRIPTION
    Real planner/dispatcher with OS boundaries doubled; only synthetic data.
    A separate disposable-directory test exercises real lock/marker IO, never
    a Claude profile, registry key, credential or application process.
.EXAMPLE
    .\tests\Test-ShimLogging.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Windows tests only.' }
$scripts = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts'
$shim = Join-Path $scripts 'ClaudeOpenShim.ps1'
foreach ($file in @($shim, (Join-Path $scripts 'Arm-ClaudeLogin.ps1'), (Join-Path $scripts 'Launch-Claude.ps1'))) {
    $tokens = $null; $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($file, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw 'PARSER_FAILED' }
}
$tokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($shim, [ref]$tokens, [ref]$parseErrors)
$top = @($ast.EndBlock.Statements | Where-Object {
    $_ -isnot [System.Management.Automation.Language.FunctionDefinitionAst]
})
if ($top.Count -ne 4 -or $top[3].Clauses[0].Item1.Extent.Text -ne '$MyInvocation.InvocationName -ne ''.''') {
    throw 'UNSAFE_SHIM_IMPORT'
}
for ($i = 0; $i -lt 3; $i++) {
    if ($top[$i].Left.Extent.Text -ne @('$Base', '$TargetFile', '$LogFile')[$i]) { throw 'UNSAFE_SHIM_IMPORT' }
}
$exits = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.ExitStatementAst] }, $true))
if ($exits.Count -ne 1 -or $exits[0].Extent.Text -ne 'exit (Invoke-ClaudeShim -Url $Url)') { throw 'UNSAFE_SHIM_EXIT' }
. $shim
. (Join-Path $scripts 'Arm-ClaudeLogin.ps1')
Write-Host 'Preflight PASS: parser, guarded imports and exit contract.'
$script:assertions = 0; $script:scenarios = 0
$events = 'MISSING_URL|INVALID_URL|ROUTE_BUSY|TARGET_READ_FAILED|APP_DISCOVERY_FAILED|APP_NOT_FOUND|' +
    'ARGUMENT_BUILD_FAILED|LAUNCH_REQUESTED|LAUNCH_FAILED|RESET_FAILED|DISPATCH_COMPLETE'
$logPattern = '\A\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d event=(' + $events + ') target=(unknown|stock|profile)\z'
function Assert-Equal {
    param([string]$Name, $Expected, $Actual)
    if ($Expected -cne $Actual) { throw "ASSERTION_FAILED: $Name" }
    $script:assertions++
}
function Assert-LogSchema {
    param([string]$Line)
    if ($Line -cnotmatch $logPattern) { throw 'LOG_SCHEMA_LEAK' }
    $script:assertions++
}
function Assert-Rejected {
    param([string]$Name, [scriptblock]$Action)
    $failed = $false
    try { & $Action | Out-Null } catch { $failed = $true }
    Assert-Equal $Name $true $failed
}
# Deliberately non-stock existing A: the custom config must survive dispatch.
$manifestText = @'
{"defaultProfile":"A","profiles":{"A":{"dataDir":"C:\\Profiles\\Existing [A]","configDir":"C:\\Config\\Existing A","isDefault":true},"B":{"dataDir":"C:\\Profiles\\Added B","configDir":"C:\\Config\\Added B","isDefault":false}}}
'@
$planA = Get-ClaudeRoutePlan $manifestText 'A'
$planB = Get-ClaudeRoutePlan $manifestText 'b'
$intentB = New-ClaudeRouteIntent $planB

function Invoke-ShimFixture {
    param([string]$Callback, [string]$Mode = '', [string]$Marker = $intentB,
        [string]$Manifest = $manifestText, [switch]$Replay)
    $state = [pscustomobject]@{
        Logs = [System.Collections.Generic.List[string]]::new()
        Starts = [System.Collections.Generic.List[object]]::new()
        Resets = [System.Collections.Generic.List[string]]::new()
        Marker = $Marker; Reads = 0; Queries = 0; LogAttempts = 0
        Locked = $false; Disposed = $false; Output = @(); Replay = @(); Nested = @()
    }
    function Open-ClaudeRouteLock {
        if ($Mode -eq 'lock' -or $state.Locked) { throw "RAW_LOCK $Callback" }
        $state.Locked = $true
        $handle = [pscustomobject]@{ State = $state }
        $handle | Add-Member ScriptMethod Dispose { $this.State.Locked = $false; $this.State.Disposed = $true }
        return $handle
    }
    function Read-ClaudeRouteText {
        param([string]$Name, [switch]$Optional)
        $state.Reads++
        if ($Name -eq 'target.txt') {
            if ($Mode -eq 'marker-read') { throw "RAW_READ $Callback" }
            return $state.Marker
        }
        if ($Name -ne 'profiles.json') { throw 'UNEXPECTED_READ' }
        if ($Mode -eq 'manifest-read') { throw "RAW_MANIFEST $Callback" }
        return $Manifest
    }
    function Set-ClaudeRouteText {
        param([string]$Text)
        if ($Mode -eq 'reset') { throw "RAW_WRITE $Callback" }
        Assert-Equal 'marker write is under lock' $true $state.Locked
        $state.Marker = $Text; $state.Resets.Add($Text)
    }
    function Get-AppxPackage {
        [CmdletBinding()]param([string]$Name)
        $state.Queries++
        if ($Mode -eq 'discovery') { throw "RAW_DISCOVERY $Callback" }
        if ($Mode -eq 'no-app') { return }
        [pscustomobject]@{ Version = [version]'1.0'; InstallLocation = 'C:\Packages\Old' }
        [pscustomobject]@{ Version = [version]'2.0'; InstallLocation = 'C:\Packages\New' }
    }
    function Test-Path {
        [CmdletBinding()]param([string]$LiteralPath)
        if ($Mode -eq 'exe-probe') { throw "RAW_EXE $Callback" }
        return $Mode -ne 'missing-exe'
    }
    function Add-Content {
        [CmdletBinding()]param([string]$LiteralPath, [string]$Value)
        $state.LogAttempts++
        if ($LiteralPath -ne $LogFile) { throw 'UNEXPECTED_LOG_PATH' }
        if ($Mode -eq 'log-write' -or ($Mode -eq 'completion-log' -and $state.LogAttempts -eq 2)) {
            throw "RAW_LOG $Callback"
        }
        $state.Logs.Add($Value)
    }
    function Start-ClaudeCallbackProcess {
        [CmdletBinding()]param([Diagnostics.ProcessStartInfo]$StartInfo)
        Assert-Equal 'lock held during start' $true $state.Locked
        Assert-Equal 'intent already consumed at start' 'consumed' (($state.Marker | ConvertFrom-Json).status)
        $state.Starts.Add($StartInfo)
        if ($Mode -eq 'launch') { throw "RAW_START $Callback" }
        if ($Mode -eq 'launch-nonterminating') { Write-Error "RAW_START $Callback" }
        if ($Mode -eq 'concurrent') { $state.Nested = @(Invoke-ClaudeShim $Callback *>&1) }
    }
    if ($Mode -eq 'builder') {
        function New-ClaudeCallbackStartInfo {
            param([string]$ExecutablePath, $Plan, [string]$Callback)
            throw "RAW_BUILDER $Callback"
        }
    }
    $state.Output = @(Invoke-ClaudeShim -Url $Callback *>&1)
    if ($Replay) { $state.Replay = @(Invoke-ClaudeShim -Url $Callback *>&1) }
    return $state
}
function Assert-ShimResult {
    param($Result, [int]$Code, [string[]]$Events, [string]$Kind = 'profile', [int]$Starts = 0, [int]$Resets = 0)
    Assert-Equal 'one output only' 1 $Result.Output.Count
    Assert-Equal 'output is integer, no raw error' $true ($Result.Output[0] -is [int])
    Assert-Equal 'dispatch status' $Code $Result.Output[0]
    Assert-Equal 'start count' $Starts $Result.Starts.Count
    Assert-Equal 'consume count' $Resets $Result.Resets.Count
    Assert-Equal 'event count' $Events.Count $Result.Logs.Count
    Assert-Equal 'lock released' $false $Result.Locked
    for ($i = 0; $i -lt $Events.Count; $i++) {
        Assert-LogSchema $Result.Logs[$i]
        Assert-Equal 'exact event and category' $true $Result.Logs[$i].EndsWith(('event={0} target={1}' -f $Events[$i], $Kind))
    }
    if ($Resets) { Assert-Equal 'tombstone, not stock fallback' '{"version":2,"status":"consumed"}' $Result.Resets[0] }
    $script:scenarios++
}
$callbacks = @(
    'claude://oauth/callback?code=FAKE_CODE&state=FAKE_STATE',
    'claude://oauth/callback#access_token=FAKE_ACCESS&refresh_token=FAKE_REFRESH',
    'claude://FAKE_PATH?unknown=FAKE_CUSTOM&redirect=https%3A%2F%2Ffake.invalid%2F#FAKE_FRAGMENT'
)
$parentConfig = [Environment]::GetEnvironmentVariable('CLAUDE_CONFIG_DIR', 'Process')
try {
    $env:CLAUDE_CONFIG_DIR = 'C:\Config\Unrelated Parent'
    foreach ($callback in $callbacks) {
        foreach ($plan in @($planA, $planB)) {
            $result = Invoke-ShimFixture $callback -Marker (New-ClaudeRouteIntent $plan)
            Assert-ShimResult $result 0 @('LAUNCH_REQUESTED', 'DISPATCH_COMPLETE') 'profile' 1 1
            Assert-Equal 'full callback and exact profile' (Get-ClaudeLaunchArgString $plan.DataDir $callback) $result.Starts[0].Arguments
            Assert-Equal 'exact config forwarded on cold start' $plan.ConfigDir $result.Starts[0].EnvironmentVariables['CLAUDE_CONFIG_DIR']
            Assert-Equal 'no shell launch' $false $result.Starts[0].UseShellExecute
            Assert-Equal 'newest MSIX' 'C:\Packages\New\app\Claude.exe' $result.Starts[0].FileName
            Assert-Equal 'parent config untouched' 'C:\Config\Unrelated Parent' $env:CLAUDE_CONFIG_DIR
        }
    }
    $stockText = $manifestText.Replace('C:\\Config\\Existing A', '')
    $stockPlan = Get-ClaudeRoutePlan $stockText 'A'
    $result = Invoke-ShimFixture $callbacks[0] -Marker (New-ClaudeRouteIntent $stockPlan) -Manifest $stockText
    Assert-ShimResult $result 0 @('LAUNCH_REQUESTED', 'DISPATCH_COMPLETE') 'profile' 1 1
    Assert-Equal 'explicitly selected stock strips inherited config' $false $result.Starts[0].EnvironmentVariables.ContainsKey('CLAUDE_CONFIG_DIR')
    Assert-Equal 'stock still has explicit data dir' $true $result.Starts[0].Arguments.StartsWith('--user-data-dir=')
} finally { $env:CLAUDE_CONFIG_DIR = $parentConfig }
foreach ($missing in @('', ' ')) {
    $result = Invoke-ShimFixture $missing
    Assert-ShimResult $result 1 @('MISSING_URL') 'unknown'
    Assert-Equal 'no read on missing URL' 0 $result.Reads
}
foreach ($bad in @('https://fake.invalid/', 'claude://', 'claude://x/" --injected',
    "claude://x/a`nb", 'claude://user@host/path', 'claude://x/back\slash')) {
    $result = Invoke-ShimFixture $bad
    Assert-ShimResult $result 1 @('INVALID_URL') 'unknown'
    Assert-Equal 'invalid URL touches no intent' 0 $result.Reads
}
foreach ($badMarker in @('', 'default', 'C:\Profiles\Added B', '{}', '{bad',
    '{"version":2,"status":"disarmed"}', '{"version":2,"status":"consumed"}',
    (New-ClaudeRouteIntent $planB ([datetimeoffset]::UtcNow.AddMinutes(-6))),
    (New-ClaudeRouteIntent $planB ([datetimeoffset]::UtcNow.AddMinutes(1))))) {
    $result = Invoke-ShimFixture $callbacks[0] -Marker $badMarker
    Assert-ShimResult $result 1 @('TARGET_READ_FAILED') 'unknown'
    Assert-Equal 'no discovery or fallback on ambiguous target' 0 $result.Queries
}
$result = Invoke-ShimFixture $callbacks[0] -Manifest ($manifestText + ' ')
Assert-ShimResult $result 1 @('TARGET_READ_FAILED') 'unknown'
$badManifests = @(
    $manifestText.Replace('C:\\Profiles\\Added B', 'C:\\Profiles\\Existing [A]'),
    $manifestText.Replace('C:\\Config\\Added B', 'C:\\Config\\Existing A\\nested'),
    $manifestText.Replace('C:\\Profiles\\Added B', 'relative'),
    $manifestText.Replace('C:\\Config\\Added B', 'C:\\Config\\bad.'),
    $manifestText.Replace('C:\\Config\\Added B', 'C:\\Config\\a:stream'),
    $manifestText.Replace('"configDir":', '"missingConfig":')
)
foreach ($bad in $badManifests) { Assert-Rejected 'invalid/overlapping manifest rejected' { Get-ClaudeRoutePlan $bad 'B' } }
Assert-Rejected 'unknown named profile rejected' { Get-ClaudeRoutePlan $manifestText 'C' }
$intent = $intentB | ConvertFrom-Json
$intent | Add-Member NoteProperty extra 'FAKE_SECRET'
Assert-Rejected 'extra intent field rejected' { Resolve-ClaudeRouteIntent ($intent | ConvertTo-Json) $manifestText }

$cases = @(
    @{ Mode = 'lock'; Event = 'ROUTE_BUSY'; Kind = 'unknown'; Consumed = 0 },
    @{ Mode = 'marker-read'; Event = 'TARGET_READ_FAILED'; Kind = 'unknown'; Consumed = 0 },
    @{ Mode = 'manifest-read'; Event = 'TARGET_READ_FAILED'; Kind = 'unknown'; Consumed = 0 },
    @{ Mode = 'reset'; Event = 'RESET_FAILED'; Kind = 'profile'; Consumed = 0 },
    @{ Mode = 'discovery'; Event = 'APP_DISCOVERY_FAILED'; Kind = 'profile'; Consumed = 1 },
    @{ Mode = 'exe-probe'; Event = 'APP_DISCOVERY_FAILED'; Kind = 'profile'; Consumed = 1 },
    @{ Mode = 'no-app'; Event = 'APP_NOT_FOUND'; Kind = 'profile'; Consumed = 1 },
    @{ Mode = 'missing-exe'; Event = 'APP_NOT_FOUND'; Kind = 'profile'; Consumed = 1 },
    @{ Mode = 'builder'; Event = 'ARGUMENT_BUILD_FAILED'; Kind = 'profile'; Consumed = 1 }
)
foreach ($case in $cases) {
    $result = Invoke-ShimFixture $callbacks[1] -Mode $case.Mode
    Assert-ShimResult $result 1 @($case.Event) $case.Kind 0 $case.Consumed
}
foreach ($mode in @('launch', 'launch-nonterminating')) {
    $result = Invoke-ShimFixture $callbacks[2] -Mode $mode
    Assert-ShimResult $result 1 @('LAUNCH_REQUESTED', 'LAUNCH_FAILED') 'profile' 1 1
}
$result = Invoke-ShimFixture $callbacks[1] -Mode 'log-write'
Assert-ShimResult $result 1 @() 'profile' 0 1
Assert-Equal 'failed log does not recurse' 1 $result.LogAttempts
$result = Invoke-ShimFixture $callbacks[1] -Mode 'completion-log'
Assert-ShimResult $result 1 @('LAUNCH_REQUESTED') 'profile' 1 1
$result = Invoke-ShimFixture '' -Mode 'log-write'
Assert-ShimResult $result 1 @() 'unknown'
$result = Invoke-ShimFixture $callbacks[0] -Replay
Assert-Equal 'first dispatch succeeds' 0 $result.Output[0]
Assert-Equal 'replay is rejected, no A fallback' 1 $result.Replay[0]
Assert-Equal 'replay starts nothing' 1 $result.Starts.Count
Assert-Equal 'replay never rewrites marker' 1 $result.Resets.Count
foreach ($line in $result.Logs) { Assert-LogSchema $line }
$result = Invoke-ShimFixture $callbacks[0] -Mode 'concurrent'
Assert-Equal 'outer dispatch succeeds' 0 $result.Output[0]
Assert-Equal 'interleaved callback blocked by lock' 1 $result.Nested[0]
Assert-Equal 'interleaved callback never starts' 1 $result.Starts.Count
foreach ($line in $result.Logs) { Assert-LogSchema $line }
foreach ($leaky in @(('2026-01-01T00:00:00 C:\Private <- ' + $callbacks[0]),
    ('2026-01-01T00:00:00 event=LAUNCH_FAILED target=profile ' + $callbacks[1]),
    ("2026-01-01T00:00:00 event=DISPATCH_COMPLETE target=profile`n" + $callbacks[2]))) {
    Assert-Rejected 'synthetic leak detected' { Assert-LogSchema $leaky }
}

# Real IO only in this newly created, random temporary metadata directory.
# No tests are executed against the user's profiles. No callback process starts.
function Test-RouteMetadataIO {
    $Base = Join-Path ([IO.Path]::GetTempPath()) ('Claude Route Test ' + [guid]::NewGuid().ToString('N'))
    $TargetFile = Join-Path $Base 'target.txt'; $LogFile = Join-Path $Base 'route.log'
    $null = [IO.Directory]::CreateDirectory($Base)
    $manifestPath = Join-Path $Base 'profiles.json'
    [IO.File]::WriteAllText($manifestPath, $manifestText)
    $counter = [pscustomobject]@{ Opens = 0; Fail = $false; Plan = $null }
    function Open-ClaudeArmedWindow {
        param($Plan)
        $counter.Opens++; $counter.Plan = $Plan
        if ($counter.Fail) { throw 'SYNTHETIC_WINDOW_FAILURE' }
    }
    function Invoke-TestArm {
        param([string]$Name, [switch]$Launch)
        # Suppress safe informational output, inspect only the numeric status.
        return (Invoke-ClaudeArmer -Profile $Name -Launch:$Launch 3>$null 6>$null)
    }
    try {
        Assert-Equal 'arm B using real marker IO' 0 (Invoke-TestArm 'B')
        $before = [IO.File]::ReadAllText($TargetFile)
        $resolved = Resolve-ClaudeRouteIntent $before $manifestText
        Assert-Equal 'B marker resolves exact config' $planB.ConfigDir $resolved.ConfigDir
        Assert-Equal 'cannot overwrite B intent with A' 1 (Invoke-TestArm 'A')
        Assert-Equal 'active marker byte-for-byte unchanged' $before ([IO.File]::ReadAllText($TargetFile))
        $lock = Open-ClaudeRouteLock
        try {
            Assert-Rejected 'real exclusive lock refuses second open' { $other = Open-ClaudeRouteLock; $other.Dispose() }
            Assert-Equal 'armer is blocked by real lock' 1 (Invoke-TestArm 'default')
            Assert-Equal 'lock failure leaves marker intact' $before ([IO.File]::ReadAllText($TargetFile))
        } finally { $lock.Dispose() }
        Assert-Equal 'explicit disarm succeeds' 0 (Invoke-TestArm 'default')
        Assert-Rejected 'disarmed marker never means A' { Resolve-ClaudeRouteIntent (Read-ClaudeRouteText 'target.txt') $manifestText }
        Assert-Equal 'default plus launch rejected' 1 (Invoke-TestArm 'default' -Launch)
        Assert-Equal 'arm named A without changing its paths' 0 (Invoke-TestArm 'A' -Launch)
        Assert-Equal 'existing A exact data forwarded' $planA.DataDir $counter.Plan.DataDir
        Assert-Equal 'existing A custom config forwarded' $planA.ConfigDir $counter.Plan.ConfigDir
        Assert-Equal 'only requested window opened (double)' 1 $counter.Opens
        $null = Invoke-TestArm 'default'
        $counter.Fail = $true
        Assert-Equal 'window failure does not leave active arm' 1 (Invoke-TestArm 'B' -Launch)
        Assert-Equal 'failed optional launch disarms' 'disarmed' ((Read-ClaudeRouteText 'target.txt' | ConvertFrom-Json).status)
        $counter.Fail = $false
        Assert-Equal 'can arm B again after explicit/failure disarm' 0 (Invoke-TestArm 'B')
        $lock = Open-ClaudeRouteLock
        try { Set-ClaudeRouteText '{"version":2,"status":"consumed"}' } finally { $lock.Dispose() }
        Assert-Rejected 'real consumed marker rejects replay' { Resolve-ClaudeRouteIntent (Read-ClaudeRouteText 'target.txt') $manifestText }
        Assert-Equal 'named A can be newly armed after consumption' 0 (Invoke-TestArm 'A')
        Assert-Equal 'manifest unchanged throughout all operations' $manifestText ([IO.File]::ReadAllText($manifestPath))
        Assert-Equal 'no temporary staging files left behind' 0 @(Get-ChildItem -LiteralPath $Base -Filter '*.tmp').Count
        Assert-Equal 'metadata directory only contains known sidecars' 3 @(Get-ChildItem -LiteralPath $Base).Count
        $null = Invoke-TestArm 'default'
        [IO.File]::WriteAllText($TargetFile, 'default')
        Assert-Equal 'legacy marker not silently adopted by armer' 1 (Invoke-TestArm 'B')
        Assert-Equal 'legacy marker requires deliberate disarm' 0 (Invoke-TestArm 'default')
    } finally {
        # Owned random fixture only; no recursive deletion of a configured root.
        Remove-Item -LiteralPath $Base -Recurse -Force
    }
}
Test-RouteMetadataIO
Write-Host "PASS: $script:scenarios dispatch scenarios; $script:assertions assertions; synthetic routing and disposable metadata IO only."
