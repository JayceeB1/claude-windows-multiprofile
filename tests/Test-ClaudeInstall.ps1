<#
.SYNOPSIS
    Tests the single-entry installer on synthetic data (no Claude process, no login, no registry write).
.DESCRIPTION
    Pure functions, the specification template and a write-free preview, all in an owned TEMP folder.
    Windows PowerShell 5.1 or 7.
.EXAMPLE
    .\tests\Test-ClaudeInstall.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'These tests require Windows.' }
$scripts = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts'
$installer = Join-Path $scripts 'Install-ClaudeMultiAccount.ps1'
$script:assertions = 0
function Assert-Equal {
    param([string]$Name, $Expected, $Actual)
    if ($Expected -cne $Actual) { throw "$Name -- expected <$Expected>, got <$Actual>" }
    $script:assertions++
}
function Assert-True {
    param([string]$Name, $Condition)
    if (-not $Condition) { throw "$Name -- expected true" }
    $script:assertions++
}

$tokens = $null; $parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($installer, [ref]$tokens, [ref]$parseErrors)
Assert-Equal 'installer parses' 0 @($parseErrors).Count
Assert-True 'installer is ASCII only (PS 5.1 reads it as ANSI)' (-not ([IO.File]::ReadAllBytes($installer) | Where-Object { $_ -gt 127 }))

. $installer -InstallDir (Join-Path ([IO.Path]::GetTempPath()) 'unused')
Assert-Equal 'step order' 'Checks,Base,Identity,Tools,Sharing,Verify' ($script:StepOrder -join ',')

$root = Join-Path ([IO.Path]::GetTempPath()) ('claude-install-test-' + [guid]::NewGuid().ToString('N'))
try {
    [void](New-Item -ItemType Directory -Path $root)

    # The template carries exactly the keys the native specification schema accepts.
    $specObject = New-ClaudeSpecObject -InstallDir (Join-Path $root 'ClaudeProfiles') -BDataDir 'B:\data' -BConfigDir 'B:\cfg' -Version '9.9.9'
    Assert-Equal 'spec keys' 'desktop_dir,install_dir,profiles,projects,protocol,schema' ((@($specObject.Keys) | Sort-Object) -join ',')
    Assert-Equal 'profile keys' 'A,B' ((@($specObject.profiles.Keys) | Sort-Object) -join ',')
    Assert-Equal 'project keys' 'evidence,memory,project' ((@($specObject.projects[0].Keys) | Sort-Object) -join ',')
    Assert-Equal 'evidence keys' 'config_provenance,external_policy_reviewed,memory_provenance,surface,trust_confirmed,version' ((@($specObject.projects[0].evidence.Keys) | Sort-Object) -join ',')
    Assert-Equal 'protocol keys' 'change,consent,expected_before' ((@($specObject.protocol.Keys) | Sort-Object) -join ',')
    Assert-Equal 'A data dir is the stock one' (Join-Path $env:APPDATA 'Claude') $specObject.profiles.A.dataDir
    Assert-Equal 'B data dir is the requested one' 'B:\data' $specObject.profiles.B.dataDir
    Assert-Equal 'evidence is never pre-confirmed' $false $specObject.projects[0].evidence.trust_confirmed
    Assert-Equal 'consent is never pre-given' $false $specObject.protocol.consent

    # Readiness: placeholders, evidence and naming are refused with closed reasons.
    Assert-Equal 'no spec' 'SPEC_NOT_GIVEN' (Test-ClaudeSpecReady -Path '')
    Assert-Equal 'bad name' 'SPEC_NAME_MUST_END_WITH_.workspace.local.json' (Test-ClaudeSpecReady -Path (Join-Path $root 'spec.json'))
    Assert-Equal 'missing file' 'SPEC_FILE_MISSING' (Test-ClaudeSpecReady -Path (Join-Path $root 'none.workspace.local.json'))
    $file = Join-Path $root 'claude.workspace.local.json'
    ($specObject | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $file -Encoding UTF8
    Assert-Equal 'placeholders' 'SPEC_HAS_PLACEHOLDERS' (Test-ClaudeSpecReady -Path $file)
    $specObject.projects[0].project = 'C:\p'; $specObject.projects[0].memory = 'C:\m'
    ($specObject | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $file -Encoding UTF8
    Assert-Equal 'evidence not confirmed' 'SPEC_EVIDENCE_NOT_CONFIRMED:config_provenance' (Test-ClaudeSpecReady -Path $file)
    foreach ($flag in 'config_provenance', 'memory_provenance', 'trust_confirmed', 'external_policy_reviewed') { $specObject.projects[0].evidence[$flag] = $true }
    ($specObject | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $file -Encoding UTF8
    Assert-Equal 'complete spec' $null (Test-ClaudeSpecReady -Path $file)
    Set-Content -LiteralPath $file -Value '{not json' -Encoding UTF8
    Assert-Equal 'not json' 'SPEC_NOT_JSON' (Test-ClaudeSpecReady -Path $file)

    # Preview writes nothing (the checks may block on a machine without Claude: that is a closed answer, not an error).
    $install = Join-Path $root 'ClaudeProfiles'
    $shell = (Get-Process -Id $PID).Path
    $before = @(Get-ChildItem -LiteralPath $root -Recurse -Force | ForEach-Object FullName).Count
    $text = & $shell -NoProfile -File $installer -InstallDir $install 2>&1 | Out-String
    Assert-True 'preview announces itself' ($text -match 'preview')
    Assert-True 'preview created no install folder' (-not (Test-Path -LiteralPath $install))
    Assert-Equal 'preview wrote nothing under the test root' $before (@(Get-ChildItem -LiteralPath $root -Recurse -Force | ForEach-Object FullName).Count)

    # The template writer creates one file and never overwrites it.
    $text = & $shell -NoProfile -File $installer -InstallDir $install -WriteSpecTemplate 2>&1 | Out-String
    $written = Join-Path $install 'setup\claude.workspace.local.json'
    Assert-True 'template written' (Test-Path -LiteralPath $written -PathType Leaf)
    Assert-Equal 'template is incomplete by design' 'SPEC_HAS_PLACEHOLDERS' (Test-ClaudeSpecReady -Path $written)
    $stamp = (Get-Item -LiteralPath $written).LastWriteTimeUtc.Ticks
    $text = & $shell -NoProfile -File $installer -InstallDir $install -WriteSpecTemplate 2>&1 | Out-String
    Assert-True 'second run refuses to overwrite' ($text -match 'SPEC_TEMPLATE_EXISTS')
    Assert-Equal 'template untouched' $stamp (Get-Item -LiteralPath $written).LastWriteTimeUtc.Ticks
    Assert-Equal 'only the setup folder was created' 'setup' ((Get-ChildItem -LiteralPath $install -Force | ForEach-Object Name) -join ',')
} finally {
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue }
}
Write-Host "PASS: $script:assertions installer assertions; no Claude process, login, registry or real shortcut touched."
