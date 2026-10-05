<#
.SYNOPSIS
    Q1/Q2 worker: real routing metadata IO, synthetic discovery/launch only.
.DESCRIPTION
    The Python parent owns the TEMP root and all child process handles. JSON
    stdout events and stdin commands provide barriers; no sleeps or live links.
    Never run against an installed profile. No registry or Claude process access.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$FixtureRoot,
    [Parameter(Mandatory)][string]$Token,
    [Parameter(Mandatory)]
    [ValidateSet('Preflight', 'Arm', 'Callback', 'Lock', 'Probe', 'Expire')][string]$Mode,
    [ValidateSet('A', 'B', 'default')][string]$Profile = 'B',
    [switch]$Hold,
    [ValidateSet('None', 'BeforeConsume', 'AfterConsume', 'AfterLaunch')][string]$PauseAt = 'None',
    [ValidateSet('None', 'Discovery', 'Launch')][string]$FailAt = 'None'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

function Send-Event {
    param([string]$Event, [hashtable]$Fields = @{})
    $Fields.event = $Event
    $Fields.pid = $PID
    [Console]::Out.WriteLine(($Fields | ConvertTo-Json -Compress -Depth 4))
    [Console]::Out.Flush()
}

function Receive-Command {
    param([string]$Expected)
    if ([Console]::In.ReadLine() -cne $Expected) { throw 'BARRIER_COMMAND_INVALID' }
}

function Assert-GuardedImport {
    param([string]$Path, [string[]]$Assignments)
    $tokens = $null; $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw 'PARSER_FAILED' }
    $top = @($ast.EndBlock.Statements | Where-Object {
        $_ -isnot [Management.Automation.Language.FunctionDefinitionAst]
    })
    if ($top.Count -ne ($Assignments.Count + 1) -or
        $top[-1] -isnot [Management.Automation.Language.IfStatementAst] -or
        $top[-1].Clauses[0].Item1.Extent.Text -cne '$MyInvocation.InvocationName -ne ''.''') {
        throw 'UNSAFE_IMPORT'
    }
    for ($i = 0; $i -lt $Assignments.Count; $i++) {
        if ($top[$i].Extent.Text -cne $Assignments[$i]) { throw 'UNSAFE_IMPORT_ASSIGNMENT' }
    }
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'WINDOWS_ONLY' }
    # Require an owned, direct TEMP child; reject a caller-supplied account root.
    $root = [IO.Path]::GetFullPath($FixtureRoot).TrimEnd([char[]]'\/')
    $tempParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([char[]]'\/')
    if ([IO.Path]::GetDirectoryName($root) -ine $tempParent -or
        [IO.Path]::GetFileName($root) -notmatch '^ClaudeRouteQ1-[a-z0-9_]+$' -or
        $Token -notmatch '^[a-f0-9]{32}$') { throw 'NOT_OWNED_TEMP' }
    foreach ($relative in @('', 'owner.txt', 'bin', 'bin\ClaudeOpenShim.ps1',
        'bin\Arm-ClaudeLogin.ps1', 'bin\Launch-Claude.ps1', 'bin\profiles.json',
        'package', 'package\app', 'package\app\Claude.exe')) {
        $item = Get-Item -LiteralPath (Join-Path $root $relative) -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'FIXTURE_ALIAS' }
    }
    if ([IO.File]::ReadAllText((Join-Path $root 'owner.txt')) -cne $Token) { throw 'OWNER_MISMATCH' }
    $bin = Join-Path $root 'bin'
    $shim = Join-Path $bin 'ClaudeOpenShim.ps1'
    $armer = Join-Path $bin 'Arm-ClaudeLogin.ps1'
    $launcher = Join-Path $bin 'Launch-Claude.ps1'
    # Parse every copied source and this worker before importing production.
    foreach ($file in @($PSCommandPath, $shim, $armer, $launcher)) {
        $tokens = $null; $errors = $null
        $null = [Management.Automation.Language.Parser]::ParseFile($file, [ref]$tokens, [ref]$errors)
        if ($errors.Count) { throw 'PARSER_FAILED' }
    }
    Assert-GuardedImport $shim @('$Base = $PSScriptRoot',
        '$TargetFile = Join-Path $Base ''target.txt''', '$LogFile = Join-Path $Base ''route.log''')
    Assert-GuardedImport $armer @()
    Assert-GuardedImport $launcher @()
    $workerProfile = $Profile
    . $shim
    . $armer
    # The armer's parameter block shares this dot-source scope.
    $Profile = $workerProfile
    $fakeExe = Join-Path $root 'package\app\Claude.exe'
    $parentConfig = [Environment]::GetEnvironmentVariable('CLAUDE_CONFIG_DIR', 'Process')
    $callback = 'claude://oauth/callback?code=Q1_SYNTHETIC&state=Q1_SYNTHETIC'

    # Wrap the real lock acquisition only to pause BEFORE marker consumption.
    # Killing this owned worker skips finally; Windows must release its handle.
    $realOpenLock = ${function:Open-ClaudeRouteLock}
    function Open-ClaudeRouteLock {
        $held = & $realOpenLock
        if ($PauseAt -ceq 'BeforeConsume') {
            Send-Event 'before-consume'
            Receive-Command 'release'
        }
        return $held
    }

    # Keep planner/dispatcher/lock/read/write/logger/builder real. Only package
    # discovery and the two actual process-start boundaries are replaced.
    function Get-AppxPackage {
        [CmdletBinding()]param([string]$Name)
        if ($Name -cne '*Claude*') { throw 'UNEXPECTED_DISCOVERY' }
        if ($Hold -or $PauseAt -ceq 'AfterConsume') {
            $marker = Read-ClaudeRouteText 'target.txt' | ConvertFrom-Json
            if ($marker.status -cne 'consumed') { throw 'NOT_CONSUMED_BEFORE_DISCOVERY' }
            Send-Event 'consumed'
            Receive-Command 'release'
        }
        if ($FailAt -ceq 'Discovery') {
            Send-Event 'discovery-failed'
            throw 'SYNTHETIC_DISCOVERY_FAILURE'
        }
        [pscustomobject]@{ Version = [version]'1.0'; InstallLocation = (Join-Path $root 'package') }
    }
    function Start-ClaudeCallbackProcess {
        param([Diagnostics.ProcessStartInfo]$StartInfo)
        if ($FailAt -ceq 'Launch') {
            Send-Event 'launch-failed'
            throw 'SYNTHETIC_LAUNCH_FAILURE'
        }
        $plan = Get-ClaudeRoutePlan (Read-ClaudeRouteText 'profiles.json') $Profile
        . $launcher
        $expected = New-ClaudeStartInfo $fakeExe $plan.DataDir $plan.ConfigDir
        $expected.Arguments += ' "' + $callback + '"'
        if ($StartInfo.FileName -cne $fakeExe -or $StartInfo.UseShellExecute -or
            $StartInfo.Arguments -cne $expected.Arguments -or
            $StartInfo.EnvironmentVariables['CLAUDE_CONFIG_DIR'] -cne $plan.ConfigDir -or
            [Environment]::GetEnvironmentVariable('CLAUDE_CONFIG_DIR', 'Process') -cne $parentConfig -or
            (Read-ClaudeRouteText 'target.txt' | ConvertFrom-Json).status -cne 'consumed') {
            throw 'START_RECEIPT_INVALID'
        }
        # CreateNew fails on a duplicate launch instead of replacing evidence.
        $receipt = Join-Path $root ('launch-' + $PID + '.json')
        $bytes = [Text.Encoding]::UTF8.GetBytes((@{ pid = $PID; profile = $Profile;
            configMatched = $true; parentUnchanged = $true } | ConvertTo-Json -Compress))
        $stream = [IO.File]::Open($receipt, [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) }
        finally { $stream.Dispose() }
        if ($PauseAt -ceq 'AfterLaunch') {
            # Durable launch-double receipt exists, but dispatch acknowledgment
            # has not happened. This is not evidence of real Claude activation.
            Send-Event 'launch-unacknowledged'
            Receive-Command 'release'
        }
        Send-Event 'launch-recorded' @{ profile = $Profile }
    }
    function Open-ClaudeArmedWindow {
        param($Plan)
        if (-not $Hold -or $Plan.Profile -cne $Profile) { throw 'UNEXPECTED_WINDOW_START' }
        Send-Event 'armed' @{ profile = $Plan.Profile }
        Receive-Command 'release'
    }

    Send-Event 'ready' @{ shell = $PSVersionTable.PSVersion.ToString(); mode = $Mode }
    Receive-Command 'go'
    $code = 0
    switch ($Mode) {
        'Preflight' { }
        'Arm' { $code = Invoke-ClaudeArmer -Profile $Profile -Launch:$Hold 3>$null 6>$null }
        'Callback' { $code = Invoke-ClaudeShim -Url $callback }
        'Lock' {
            $lock = Open-ClaudeRouteLock
            try { Send-Event 'lock-held'; Receive-Command 'release' }
            finally { $lock.Dispose() }
        }
        'Probe' { $lock = Open-ClaudeRouteLock; $lock.Dispose() }
        'Expire' {
            $lock = Open-ClaudeRouteLock
            try {
                $plan = Get-ClaudeRoutePlan (Read-ClaudeRouteText 'profiles.json') $Profile
                Set-ClaudeRouteText (New-ClaudeRouteIntent -Plan $plan -Now ([datetimeoffset]::UtcNow.AddMinutes(-6)))
                Send-Event 'expired'
            } finally { $lock.Dispose() }
        }
    }
    Send-Event 'result' @{ code = [int]$code }
    exit $code
} catch {
    # Fixed test event only; never emit production exceptions or caller paths.
    Send-Event 'worker-failed'
    exit 2
}
