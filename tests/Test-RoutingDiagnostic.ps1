<#
.SYNOPSIS
    Qualifies the passive diagnostic on owned fixtures without installed access.
.DESCRIPTION
    Parses/inspects OS boundaries before importing. Reads real TEMP metadata;
    package/registry queries are doubles. All streams and fixture bytes checked.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$diagnostic = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\Test-ClaudeRouting.ps1'
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($diagnostic, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'PARSER_FAILED' }
$top = @($ast.EndBlock.Statements | Where-Object {
    $_ -isnot [Management.Automation.Language.FunctionDefinitionAst]
})
if ($top.Count -ne 1 -or $top[0] -isnot [Management.Automation.Language.IfStatementAst] -or
    $top[0].Clauses[0].Item1.Extent.Text -cne '$MyInvocation.InvocationName -ne ''.''') {
    throw 'UNSAFE_DIAGNOSTIC_IMPORT'
}
# Fail before execution on any added command boundary (including a live probe).
$allowedCommands = @('Get-Item', 'Test-Path', 'Join-Path', 'Get-ItemProperty', 'Get-AppxPackage',
    'ConvertFrom-Json', 'ConvertTo-Json', 'Compare-Object', 'Test-ClaudeDiagnosticPath',
    'Read-ClaudeDiagnosticText', 'Get-ClaudeDiagnosticProtocol', 'Get-ClaudeDiagnosticPackage',
    'Set-ClaudeDiagnosticIntent', 'Invoke-ClaudeRoutingDiagnostic')
foreach ($node in @($ast.FindAll({ param($n)
    $n -is [Management.Automation.Language.CommandAst]
}, $true))) {
    if ($node.GetCommandName() -cnotin $allowedCommands -or
        $node.InvocationOperator -eq [Management.Automation.Language.TokenKind]::Dot) {
        throw 'UNSAFE_COMMAND_BOUNDARY'
    }
}
foreach ($node in @($ast.FindAll({ param($n)
    $n -is [Management.Automation.Language.InvokeMemberExpressionAst]
}, $true))) {
    if ($node.Member.Extent.Text -cnotin @('GetFullPath', 'GetDirectoryName', 'TrimEnd', 'Open',
        'new', 'ReadBlock', 'Dispose', 'IsNullOrWhiteSpace', 'Create', 'ToString',
        'ComputeHash', 'GetBytes', 'Replace', 'ToUnixTimeMilliseconds')) { throw 'UNSAFE_MEMBER_BOUNDARY' }
    if ($node.Member.Extent.Text -ceq 'Open' -and
        ($node.Extent.Text -notmatch '\[IO.FileMode\]::Open,' -or
         $node.Extent.Text -notmatch '\[IO.FileAccess\]::Read,')) { throw 'UNSAFE_FILE_OPEN' }
}
. $diagnostic
$fixtureState = @{ assertions=0; cases=0; osMode='router'; packageMode='present'
    forbiddenCalls=0; logReads=0
    sentinel='SECRET_SYNTHETIC claude://callback?code=SECRET_SYNTHETIC C:\Private\Person' }
function Assert-Equal {
    param([string]$Label, $Expected, $Actual)
    if ($Expected -cne $Actual) { throw ('ASSERTION_FAILED: ' + $Label) }
    $fixtureState.assertions++
}
function Get-AppxPackage {
    [CmdletBinding()]param([string]$Name)
    Assert-Equal 'package filter' '*Claude*' $Name
    if ($fixtureState.packageMode -eq 'error') { throw $fixtureState.sentinel }
    if ($fixtureState.packageMode -eq 'missing') { return }
    if ($fixtureState.packageMode -eq 'noisy') {
        Write-Warning $fixtureState.sentinel
        Write-Host $fixtureState.sentinel
        Write-Verbose $fixtureState.sentinel -Verbose
        $DebugPreference = 'Continue'
        Write-Debug $fixtureState.sentinel
        Write-Error $fixtureState.sentinel -ErrorAction Continue
        throw $fixtureState.sentinel
    }
    [pscustomobject]@{ Version = 'SECRET_SYNTHETIC'; InstallLocation = $fixtureState.sentinel }
}
function Test-Path {
    [CmdletBinding()]param([string]$LiteralPath)
    if ($LiteralPath -like 'HKCU:*') {
        if ($fixtureState.osMode -eq 'error') { throw $fixtureState.sentinel }
        return $fixtureState.osMode -ne 'missing'
    }
    if ($LiteralPath -like '*route.log') { $fixtureState.logReads++; throw 'LOG_READ_FORBIDDEN' }
    Microsoft.PowerShell.Management\Test-Path -LiteralPath $LiteralPath -ErrorAction Stop
}
function Get-ItemProperty {
    [CmdletBinding()]param([string]$LiteralPath, [string]$Name)
    Assert-Equal 'registry scope' 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\UrlAssociations\claude\UserChoice' $LiteralPath
    Assert-Equal 'registry value' 'ProgId' $Name
    $value = if ($fixtureState.osMode -eq 'router') { 'ClaudeShim.claude' } else { $fixtureState.sentinel }
    [pscustomobject]@{ ProgId = $value }
}
function Start-Process { $fixtureState.forbiddenCalls++; throw 'ACTIVATION_FORBIDDEN' }
function Invoke-ClaudeArmer { $fixtureState.forbiddenCalls++; throw 'ARM_FORBIDDEN' }
function Invoke-ClaudeShim { $fixtureState.forbiddenCalls++; throw 'DISPATCH_FORBIDDEN' }
function Get-CimInstance { $fixtureState.forbiddenCalls++; throw 'PROCESS_QUERY_FORBIDDEN' }
function Start-Sleep { $fixtureState.forbiddenCalls++; throw 'DELAY_FORBIDDEN' }

$root = Join-Path ([IO.Path]::GetTempPath()) ('ClaudeDiagnostic-' + [guid]::NewGuid().ToString('N'))
$owner = [guid]::NewGuid().ToString('N')
$bin = Join-Path $root 'bin'
$encoding = [Text.UTF8Encoding]::new($false)
function Set-FixtureText {
    param([string]$Name, [string]$Text)
    [IO.File]::WriteAllText((Join-Path $bin $Name), $Text, $encoding)
}
function Get-FixtureSnapshot {
    $snapshot = @{}
    foreach ($file in @(Get-ChildItem -LiteralPath $root -File -Recurse -Force)) {
        try { $bytes = [Convert]::ToBase64String([IO.File]::ReadAllBytes($file.FullName)) }
        catch {
            if ($file.Name -cnotin @('route.lock', 'target.txt')) { throw 'SNAPSHOT_READ_FAILED' }
            $bytes = 'held'
        }
        $snapshot[$file.FullName] = $bytes + '|' + $file.Length + '|' + $file.LastWriteTimeUtc.Ticks
    }
    return $snapshot
}
function Assert-Report {
    param([string]$Intent, [string]$Expiration = 'unknown', [string]$Binding = 'unknown',
        [string]$Manifest = 'readable', [string]$Snapshot = 'locked', [string]$Reason = 'none',
        [switch]$NoPing, [string]$Directory = $root, [switch]$UseDefault)
    $before = Get-FixtureSnapshot
    $output = @(if ($UseDefault) { & $diagnostic *>&1 }
        else { & $diagnostic -InstallDir $Directory -NoPing:$NoPing *>&1 })
    Assert-Equal 'one all-stream event' 1 $output.Count
    $text = [string]$output[0]
    if ($text -match 'SECRET_SYNTHETIC|claude://|Private|CommandLine' -or $text.Contains($root)) {
        throw 'OUTPUT_LEAK'
    }
    $report = ConvertFrom-Json $text
    $expected = [ordered]@{ version = 1; event = 'DIAGNOSTIC_PASSIVE'; mode = 'passive'
        snapshot = $Snapshot; reason = $Reason; manifest = $Manifest
        intent = $Intent; expiration = $Expiration; binding = $Binding
        protocolChoice = $(switch ($fixtureState.osMode) { 'router' {'router'} 'missing' {'missing'} 'error' {'unknown'} default {'other'} })
        package = $(switch ($fixtureState.packageMode) { 'present' {'present'} 'missing' {'missing'} default {'unknown'} })
        dispatch = 'not_probed' }
    Assert-Equal 'closed schema count' $expected.Count @($report.PSObject.Properties).Count
    foreach ($key in $expected.Keys) { Assert-Equal ('schema ' + $key) $expected[$key] $report.$key }
    $after = Get-FixtureSnapshot
    Assert-Equal 'file count preserved' $before.Count $after.Count
    foreach ($key in $before.Keys) { Assert-Equal 'file bytes/write time preserved' $before[$key] $after[$key] }
    Assert-Equal 'no activation/arming/process query/delay' 0 $fixtureState.forbiddenCalls
    Assert-Equal 'no old log read' 0 $fixtureState.logReads
    $fixtureState.cases++
}
try {
    $null = [IO.Directory]::CreateDirectory($bin)
    [IO.File]::WriteAllText((Join-Path $root 'owner.txt'), $owner, $encoding)
    Set-FixtureText 'route.lock' ''
    Set-FixtureText 'route.log' $fixtureState.sentinel
    # Import bombs prove no installed routing source is executed.
    foreach ($name in @('ClaudeOpenShim.ps1', 'Arm-ClaudeLogin.ps1', 'Launch-Claude.ps1')) {
        Set-FixtureText $name 'throw "SECRET_SYNTHETIC INSTALLED_IMPORT"'
    }
    $manifest = '{"profiles":{"SECRET_SYNTHETIC":{"dataDir":"C:\\Private\\Person","configDir":"SECRET_SYNTHETIC","isDefault":false}}}'
    Set-FixtureText 'profiles.json' $manifest
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = ([BitConverter]::ToString($sha.ComputeHash($encoding.GetBytes($manifest)))).Replace('-', '') }
    finally { $sha.Dispose() }
    $now = [datetimeoffset]::UtcNow.ToUnixTimeMilliseconds()
    $intent = [ordered]@{version=2; status='armed'; profile='SECRET_SYNTHETIC'; manifestHash=$hash
        createdMs=$now; expiresMs=$now+300000}
    Assert-Report 'missing'
    foreach ($status in @('consumed','disarmed')) {
        Set-FixtureText 'target.txt' ('{"version":2,"status":"' + $status + '"}')
        Assert-Report $status 'not_applicable' 'not_applicable'
    }
    Set-FixtureText 'target.txt' ($intent | ConvertTo-Json -Compress)
    Assert-Report 'armed' 'active' 'match'
    Assert-Report 'armed' 'active' 'match' -NoPing
    $intent.createdMs = $now-360000; $intent.expiresMs = $now-60000
    Set-FixtureText 'target.txt' ($intent | ConvertTo-Json -Compress)
    Assert-Report 'armed' 'expired' 'match'
    $intent.createdMs = $now; $intent.expiresMs = $now+300001
    Set-FixtureText 'target.txt' ($intent | ConvertTo-Json -Compress)
    Assert-Report 'armed' 'invalid' 'match'
    $intent.createdMs = $now+600000; $intent.expiresMs = $now+900000
    Set-FixtureText 'target.txt' ($intent | ConvertTo-Json -Compress)
    Assert-Report 'armed' 'invalid' 'match'
    $intent.createdMs = $now; $intent.expiresMs = $now+300000
    Set-FixtureText 'target.txt' ($intent | ConvertTo-Json -Compress)
    Set-FixtureText 'profiles.json' ($manifest + ' ')
    Assert-Report 'armed' 'active' 'mismatch'
    $intent.createdMs = 'SECRET_SYNTHETIC'
    Set-FixtureText 'target.txt' ($intent | ConvertTo-Json -Compress)
    Assert-Report 'invalid'
    $intent.createdMs = $now; $intent.manifestHash = 'SECRET_SYNTHETIC'
    Set-FixtureText 'target.txt' ($intent | ConvertTo-Json -Compress)
    Assert-Report 'invalid'
    foreach ($text in @('default', $fixtureState.sentinel, '{', '{"version":1,"status":"armed"}',
        '{"version":2,"status":"armed"}', '{"version":2,"status":"consumed","leak":"SECRET_SYNTHETIC"}',
        ('x' * 65537))) {
        Set-FixtureText 'target.txt' $text
        Assert-Report 'invalid'
    }
    Set-FixtureText 'target.txt' '{"version":2,"status":"consumed"}'
    Set-FixtureText 'profiles.json' '{'
    Assert-Report 'consumed' 'not_applicable' 'not_applicable' 'invalid'
    [IO.File]::Delete((Join-Path $bin 'profiles.json'))
    Assert-Report 'consumed' 'not_applicable' 'not_applicable' 'missing'
    Set-FixtureText 'profiles.json' $manifest
    $aliasRoot = $root + '-alias'
    $null = New-Item -ItemType Junction -Path $aliasRoot -Target $root
    try {
        Assert-Report 'unknown' -Manifest 'unknown' -Snapshot 'unavailable' -Reason 'path_unavailable' -Directory $aliasRoot
    } finally { [IO.Directory]::Delete($aliasRoot, $false) }
    Set-FixtureText 'profiles.json' ('x' * 65537)
    Assert-Report 'consumed' 'not_applicable' 'not_applicable' 'invalid'
    Set-FixtureText 'profiles.json' $manifest
    foreach ($mode in @('other','missing','error')) {
        $fixtureState.osMode=$mode; $fixtureState.packageMode='error'
        Assert-Report 'consumed' 'not_applicable' 'not_applicable'
    }
    $fixtureState.osMode='router'; $fixtureState.packageMode='missing'
    Assert-Report 'consumed' 'not_applicable' 'not_applicable'
    $fixtureState.packageMode='noisy'
    Assert-Report 'consumed' 'not_applicable' 'not_applicable'
    $fixtureState.packageMode='missing'
    $defaultUser = Join-Path $root 'default-user'
    $defaultBin = Join-Path $defaultUser 'ClaudeProfiles\bin'
    $null = [IO.Directory]::CreateDirectory($defaultBin)
    foreach ($file in @(Get-ChildItem -LiteralPath $bin -File)) {
        [IO.File]::Copy($file.FullName, (Join-Path $defaultBin $file.Name))
    }
    $previousUser = $env:USERPROFILE
    try {
        $env:USERPROFILE = $defaultUser
        Assert-Report 'consumed' 'not_applicable' 'not_applicable' -UseDefault
    } finally { $env:USERPROFILE = $previousUser }
    $held = [IO.File]::Open((Join-Path $bin 'route.lock'), 'Open', 'ReadWrite', 'None')
    try { Assert-Report 'unknown' -Manifest 'unknown' -Snapshot 'unavailable' -Reason 'lock_unavailable' }
    finally { $held.Dispose() }
    Assert-Equal 'held lock bytes preserved' '' ([IO.File]::ReadAllText((Join-Path $bin 'route.lock')))
    $held = [IO.File]::Open((Join-Path $bin 'target.txt'), 'Open', 'ReadWrite', 'None')
    try { Assert-Report 'unknown' }
    finally { $held.Dispose() }
    Assert-Equal 'held marker bytes preserved' '{"version":2,"status":"consumed"}' ([IO.File]::ReadAllText((Join-Path $bin 'target.txt')))
    [IO.File]::Delete((Join-Path $bin 'route.lock'))
    Assert-Report 'unknown' -Manifest 'unknown' -Snapshot 'unavailable' -Reason 'lock_missing'
    Assert-Report 'unknown' -Manifest 'unknown' -Snapshot 'unavailable' -Reason 'path_unavailable' -Directory (Join-Path $root 'missing')
    Assert-Report 'unknown' -Manifest 'unknown' -Snapshot 'unavailable' -Reason 'path_unavailable' -Directory ($root + [char]0)
    Write-Host "PASS diagnostic: $($fixtureState.cases) cases; $($fixtureState.assertions) assertions; fixtures only."
} finally {
    if ([IO.Directory]::Exists($root)) {
        if ([IO.Path]::GetDirectoryName($root) -ne [IO.Path]::GetTempPath().TrimEnd([char[]]'\/') -or
            ((Get-Item -LiteralPath $root -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            [IO.File]::ReadAllText((Join-Path $root 'owner.txt')) -cne $owner) { throw 'CLEANUP_OWNERSHIP' }
        foreach ($item in @(Get-ChildItem -LiteralPath $root -Recurse -Force)) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'CLEANUP_ALIAS' }
        }
        $lockPath = Join-Path $bin 'route.lock'
        if ([IO.File]::Exists($lockPath)) {
            $probe = [IO.File]::Open($lockPath, 'Open', 'ReadWrite', 'None'); $probe.Dispose()
        }
        Remove-Item -LiteralPath $root -Recurse -Force
    }
}
