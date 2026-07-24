<#
.SYNOPSIS
    Unit test for ClaudeOpenShim.ps1's Get-ClaudeLaunchArgString.

.DESCRIPTION
    Guards the PowerShell 5.1 quoting fix (see ClaudeOpenShim.ps1): a profile
    path containing spaces must survive as a SINGLE pre-quoted --user-data-dir
    token, or Chromium truncates it at the first space and the login lands in a
    profile nobody intended.

    Dot-sources the shim (which only defines its functions when dot-sourced) and
    asserts the builder output. No Pester dependency; runs on Windows PowerShell
    5.1. Exits non-zero if any case fails.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tests\Test-ArgBuilder.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$shim = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\ClaudeOpenShim.ps1'
if (-not (Test-Path $shim)) { throw "Shim not found at $shim" }

# Dot-source: InvocationName '.' inside the shim skips its main body and just
# defines Get-ClaudeLaunchArgString in this scope.
. $shim

$failures = 0
function Assert-Equal {
    param([string]$Name, [string]$Expected, [string]$Actual)
    if ($Expected -ceq $Actual) {
        Write-Host "  PASS  $Name" -ForegroundColor Green
    } else {
        $script:failures++
        Write-Host "  FAIL  $Name" -ForegroundColor Red
        Write-Host "        expected: $Expected"
        Write-Host "        actual:   $Actual"
    }
}

$url = 'claude://oauth/callback?code=abc123'

Assert-Equal 'default target -> only the quoted URL' `
    ('"' + $url + '"') `
    (Get-ClaudeLaunchArgString -Target 'default' -Url $url)

Assert-Equal 'path without spaces stays one quoted token' `
    ('--user-data-dir="C:\Users\me\AppData\Roaming\Claude-Work" "' + $url + '"') `
    (Get-ClaudeLaunchArgString -Target 'C:\Users\me\AppData\Roaming\Claude-Work' -Url $url)

# The critical case: spaces in the path must NOT splinter the argument.
$spacey = 'C:\Users\John Doe\AppData\Roaming\Claude-Client A'
Assert-Equal 'path WITH spaces survives as one quoted token' `
    ('--user-data-dir="' + $spacey + '" "' + $url + '"') `
    (Get-ClaudeLaunchArgString -Target $spacey -Url $url)

Write-Host ""
if ($failures -gt 0) {
    Write-Error "$failures test(s) failed."
    exit 1
}
Write-Host "All argument-builder tests passed." -ForegroundColor Green
