<#
.SYNOPSIS
    Routes claude:// links to a Desktop profile without logging callback data.
.DESCRIPTION
    Reads the one-shot target.txt marker, resolves the installed MSIX app and
    forwards the full link unchanged. route.log contains only a timestamp,
    fixed event code and target kind (unknown/stock/profile), never a URL,
    query, fragment, target path, process arguments or raw exception message.
    Launch/routing completion is NOT proof that authentication succeeded.
.PARAMETER Url
    The claude:// URL supplied by Windows. Not mandatory: missing input must
    fail without a hidden interactive prompt. The script exits nonzero on
    failure; Invoke-ClaudeShim returns that status to allow isolated tests.
.NOTES
    Windows PowerShell 5.1; self-contained. Dot-sourcing does not dispatch.
    This protects NEW shim log entries and explicit output, not old logs,
    PowerShell transcription/debugging, OS process telemetry, or Claude's logs.
    The URL necessarily remains in the child command line. Do not export old
    route.log files; this change neither reads nor deletes their contents.
    Profile-config propagation and ambiguous callback routing remain separate
    qualification gates. Do not test against the user's existing session.
#>
param([string]$Url)

$Base       = $PSScriptRoot
$TargetFile = Join-Path $Base 'target.txt'
$LogFile    = Join-Path $Base 'route.log'

# Preserve the existing argument contract; do not redact the dispatched link.
function Get-ClaudeLaunchArgString {
    param(
        [string]$Target,
        [string]$Url
    )
    if ($Target -eq 'default') {
        return "`"$Url`""
    }
    return "--user-data-dir=`"$Target`" `"$Url`""
}

function Write-ClaudeRouteEvent {
    param(
        [ValidateSet('MISSING_URL', 'TARGET_READ_FAILED', 'APP_DISCOVERY_FAILED',
            'APP_NOT_FOUND', 'ARGUMENT_BUILD_FAILED', 'LAUNCH_REQUESTED',
            'LAUNCH_FAILED', 'RESET_FAILED', 'DISPATCH_COMPLETE')]
        [string]$Event,
        [ValidateSet('unknown', 'stock', 'profile')]
        [string]$TargetKind = 'unknown'
    )
    try {
        # Allowlist fields only. Never accept a free-form error/URL/target here.
        Add-Content -LiteralPath $LogFile -ErrorAction Stop -Value (
            '{0} event={1} target={2}' -f (Get-Date -Format s), $Event, $TargetKind)
        return $true
    } catch {
        # A log-write exception can itself contain sensitive paths/arguments.
        # Do not print/rethrow it or recursively try to log it elsewhere.
        return $false
    }
}

function Invoke-ClaudeShim {
    param([string]$Url)
    $ErrorActionPreference = 'Stop'
    $targetKind = 'unknown'
    $failureEvent = 'TARGET_READ_FAILED'
    try {
        if ([string]::IsNullOrWhiteSpace($Url)) {
            $null = Write-ClaudeRouteEvent -Event MISSING_URL
            return 1
        }

        # Preserve the current marker/default behavior in this logging slice.
        # It is NOT yet safe for ambiguous real-account callback tests (S2c2).
        $target = 'default'
        if (Test-Path -LiteralPath $TargetFile -ErrorAction Stop) {
            $t = (Get-Content -LiteralPath $TargetFile -First 1 -ErrorAction Stop).Trim()
            if ($t) { $target = $t }
        }
        $targetKind = if ($target -eq 'default') { 'stock' } else { 'profile' }

        $failureEvent = 'APP_DISCOVERY_FAILED'
        # MSIX only: never fall back to a stale Squirrel installation.
        $pkg = Get-AppxPackage -Name '*Claude*' -ErrorAction Stop |
            Sort-Object Version -Descending | Select-Object -First 1
        $exe = if ($pkg) { Join-Path $pkg.InstallLocation 'app\Claude.exe' }
        if (-not $exe -or -not (Test-Path -LiteralPath $exe -ErrorAction Stop)) {
            $null = Write-ClaudeRouteEvent -Event APP_NOT_FOUND -TargetKind $targetKind
            return 1
        }

        $failureEvent = 'ARGUMENT_BUILD_FAILED'
        $argStr = Get-ClaudeLaunchArgString -Target $target -Url $Url
        # Fail closed if even a safe pre-dispatch event cannot be recorded.
        if (-not (Write-ClaudeRouteEvent -Event LAUNCH_REQUESTED -TargetKind $targetKind)) {
            return 1
        }
        $failureEvent = 'LAUNCH_FAILED'
        $null = Start-Process -FilePath $exe -ArgumentList $argStr -ErrorAction Stop

        $failureEvent = 'RESET_FAILED'
        Set-Content -LiteralPath $TargetFile -Value 'default' -Encoding ASCII -ErrorAction Stop
        if (-not (Write-ClaudeRouteEvent -Event DISPATCH_COMPLETE -TargetKind $targetKind)) {
            return 1
        }
        return 0
    } catch {
        # Do not render $_, ErrorRecord, exception messages, URLs or arguments.
        # Prerequisite failures cannot continue into a launch or report success.
        $null = Write-ClaudeRouteEvent -Event $failureEvent -TargetKind $targetKind
        return 1
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    exit (Invoke-ClaudeShim -Url $Url)
}
