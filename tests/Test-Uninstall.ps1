<#
.SYNOPSIS
    Verifies native cleanup refuses before mutation under PS5.1 or PS7.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$path = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\Uninstall.ps1'
$tokens = $null; $parseErrors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
$refused = $false
try { & $path -Profile A,B -RemoveData } catch {
    if ($_.Exception.Message -notlike 'NATIVE_REMOVE_NOT_ADMITTED:*') { throw }
    $refused = $true
}
if (-not $refused) { throw 'Native uninstall did not refuse.' }
Write-Host 'PASS: native Uninstall parsed and refused before mutation; no actual cleanup performed.'
