<#
.SYNOPSIS
    Arms one explicit profile for one callback, without changing registration.
.DESCRIPTION
    Uses the sibling shim's lock, manifest validation and versioned marker.
    Refuses to overwrite an outstanding intent, even if expired or malformed.
    -Profile default explicitly disarms; it NEVER means "route to stock A".
    Select the declared name of A to intentionally arm its recorded paths.
.PARAMETER Profile
    Declared profile name (case-insensitive), or default to disarm.
.PARAMETER Launch
    Open the selected profile using its recorded config after arming. Not valid
    with default. Never stops an existing process or changes its environment.
.NOTES
    A single browser login at a time. Arming does not verify OAuth state/PKCE or
    the account in the browser; close stale login tabs before a new attempt.
    Setup owns protocol registration; this script no longer reasserts registry
    keys. Existing session A must be inventoried before use. No credentials read.
#>
[CmdletBinding()]
param([string]$Profile, [switch]$Launch)

function Open-ClaudeArmedWindow {
    param($Plan)
    . (Join-Path $Base 'Launch-Claude.ps1')
    Invoke-ClaudeLauncher -ProfileDir $Plan.DataDir -ConfigDir $Plan.ConfigDir
}

function Invoke-ClaudeArmer {
    param([string]$Profile, [switch]$Launch)
    $ErrorActionPreference = 'Stop'
    $lock = $null; $armedHere = $false
    try {
        if ([string]::IsNullOrWhiteSpace($Profile) -or ($Profile -ieq 'default' -and $Launch)) {
            throw 'ARM_INPUT_INVALID'
        }
        $lock = Open-ClaudeRouteLock
        if ($Profile -ieq 'default') {
            Set-ClaudeRouteText '{"version":2,"status":"disarmed"}'
            Write-Host 'DISARMED: no callback will be routed without a new explicit arm.'
            return 0
        }
        $manifest = Read-ClaudeRouteText 'profiles.json'
        $plan = Get-ClaudeRoutePlan -ManifestText $manifest -Profile $Profile
        $previous = Read-ClaudeRouteText 'target.txt' -Optional
        if (-not [string]::IsNullOrEmpty($previous)) {
            $record = ConvertFrom-Json -InputObject $previous -ErrorAction Stop
            if ($record -isnot [pscustomobject] -or $record.version -ne 2 -or
                $record.status -cnotin @('consumed', 'disarmed')) { throw 'ARM_OUTSTANDING_INTENT' }
        }
        Set-ClaudeRouteText (New-ClaudeRouteIntent -Plan $plan)
        $armedHere = $true
        if ($Launch) { Open-ClaudeArmedWindow -Plan $plan }
        Write-Host 'ARMED: one callback, five minutes. Verify the account in the browser before signing in.'
        return 0
    } catch {
        # If optional launch fails, do not leave a silently armed retry behind.
        if ($armedHere) {
            try { Set-ClaudeRouteText '{"version":2,"status":"disarmed"}' } catch { }
        }
        # No manifest path, raw exception or login data in the error output.
        Write-Warning 'ARM_FAILED: busy, invalid configuration or outstanding intent. No fallback profile was chosen.'
        return 1
    } finally {
        if ($null -ne $lock) { try { $lock.Dispose() } catch { } }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        . (Join-Path $PSScriptRoot 'ClaudeOpenShim.ps1')
        exit (Invoke-ClaudeArmer -Profile $Profile -Launch:$Launch)
    } catch {
        Write-Warning 'ARM_FAILED: routing helper unavailable. No profile was launched.'
        exit 1
    }
}
