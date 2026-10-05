<#
.SYNOPSIS
    Emits one fixed-schema, passive routing diagnostic JSON event.
.DESCRIPTION
    Reads bounded metadata under an EXISTING read-only lock. Never creates a lock,
    arms/disarms, activates links, launches processes, imports installed scripts or
    reads old logs, profile contents or command lines. Unavailable state is unknown.
    Observations do not prove routing, Desktop identity or authentication. No live probe.
.PARAMETER InstallDir
    Metadata parent containing bin; defaults to USERPROFILE/ClaudeProfiles.
    No input paths, profile names, manifest values or raw errors are printed.
.PARAMETER NoPing
    Compatibility switch. Every invocation is passive, with or without this flag.
.EXAMPLE
    .\scripts\Test-ClaudeRouting.ps1
#>
[CmdletBinding()]
param([string]$InstallDir = '', [switch]$NoPing)

function Test-ClaudeDiagnosticPath {
    param([string]$Path)
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'ALIAS' }
        $parent = [IO.Path]::GetDirectoryName($current.TrimEnd([char[]]'\/'))
        if ($parent -eq $current) { break }
        $current = $parent
    }
}

function Read-ClaudeDiagnosticText {
    param([string]$Path)
    $stream = $null; $reader = $null
    try {
        if (-not (Test-Path -LiteralPath $Path -ErrorAction Stop)) {
            return @{ state = 'missing'; text = '' }
        }
        Test-ClaudeDiagnosticPath $Path
        $stream = [IO.File]::Open($Path, [IO.FileMode]::Open,
            [IO.FileAccess]::Read, [IO.FileShare]::Read)
        if ($stream.Length -gt 65536) { return @{ state = 'invalid'; text = '' } }
        $reader = [IO.StreamReader]::new($stream, [Text.UTF8Encoding]::new($false, $true), $true)
        $buffer = [char[]]::new(65537)
        $count = $reader.ReadBlock($buffer, 0, $buffer.Length)
        if ($count -gt 65536) { return @{ state = 'invalid'; text = '' } }
        return @{ state = 'present'; text = [string]::new($buffer, 0, $count) }
    } catch { return @{ state = 'unknown'; text = '' } }
    finally {
        if ($null -ne $reader) { $reader.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
}

function Get-ClaudeDiagnosticProtocol {
    try {
        $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\UrlAssociations\claude\UserChoice'
        if (-not (Test-Path -LiteralPath $key -ErrorAction Stop)) { return 'missing' }
        $value = (Get-ItemProperty -LiteralPath $key -Name ProgId -ErrorAction Stop).ProgId
        if ($value -isnot [string] -or [string]::IsNullOrWhiteSpace($value)) { return 'unknown' }
        if ($value -ieq 'ClaudeShim.claude') { return 'router' }
        return 'other'
    } catch { return 'unknown' }
}

function Get-ClaudeDiagnosticPackage {
    try {
        $packages = @(Get-AppxPackage -Name '*Claude*' -ErrorAction Stop)
        if ($packages.Count) { return 'present' }
        return 'missing'
    } catch { return 'unknown' }
}

function Set-ClaudeDiagnosticIntent {
    param($Report, $Marker, $Manifest, [long]$NowMs)
    if ($Marker.state -ne 'present') { $Report.intent = $Marker.state; return }
    $Report.intent = 'invalid'
    try {
        $intent = ConvertFrom-Json -InputObject $Marker.text -ErrorAction Stop
        if ($intent -isnot [pscustomobject] -or $intent.version -isnot [ValueType] -or
            $intent.version -ne 2 -or $intent.status -isnot [string]) { return }
        $keys = @($intent.PSObject.Properties.Name)
        if ($intent.status -cin @('consumed', 'disarmed') -and $keys.Count -eq 2) {
            $Report.intent = $intent.status
            $Report.expiration = 'not_applicable'; $Report.binding = 'not_applicable'
            return
        }
        $wanted = @('version', 'status', 'profile', 'manifestHash', 'createdMs', 'expiresMs')
        if ($intent.status -cne 'armed' -or $keys.Count -ne 6 -or
            @(Compare-Object $wanted $keys).Count -ne 0 -or
            $intent.profile -isnot [string] -or $intent.manifestHash -isnot [string] -or
            $intent.manifestHash -cnotmatch '^[A-F0-9]{64}$' -or
            ($intent.createdMs -isnot [long] -and $intent.createdMs -isnot [int]) -or
            ($intent.expiresMs -isnot [long] -and $intent.expiresMs -isnot [int])) { return }
        $Report.intent = 'armed'
        if ($intent.createdMs -lt 0 -or $intent.createdMs -gt $NowMs -or
            ([decimal]$intent.expiresMs - [decimal]$intent.createdMs) -ne 300000) {
            $Report.expiration = 'invalid'
        } elseif ($intent.expiresMs -le $NowMs) { $Report.expiration = 'expired' }
        else { $Report.expiration = 'active' }
        if ($Manifest.state -eq 'present') {
            $sha = [Security.Cryptography.SHA256]::Create()
            try {
                $hash = ([BitConverter]::ToString($sha.ComputeHash(
                    [Text.Encoding]::UTF8.GetBytes($Manifest.text)))).Replace('-', '')
            } finally { $sha.Dispose() }
            $Report.binding = if ($intent.manifestHash -ceq $hash) { 'match' } else { 'mismatch' }
        }
    } catch { $Report.intent = 'invalid'; $Report.expiration = 'unknown'; $Report.binding = 'unknown' }
}

function Invoke-ClaudeRoutingDiagnostic {
    param([string]$InstallDir)
    $report = [ordered]@{
        version = 1; event = 'DIAGNOSTIC_PASSIVE'; mode = 'passive'
        snapshot = 'unavailable'; reason = 'path_unavailable'; manifest = 'unknown'
        intent = 'unknown'; expiration = 'unknown'; binding = 'unknown'
        protocolChoice = (Get-ClaudeDiagnosticProtocol)
        package = (Get-ClaudeDiagnosticPackage); dispatch = 'not_probed'
    }
    $lock = $null
    try {
        if ([string]::IsNullOrWhiteSpace($InstallDir)) {
            $InstallDir = Join-Path $env:USERPROFILE 'ClaudeProfiles' -ErrorAction Stop
        }
        $bin = Join-Path $InstallDir 'bin' -ErrorAction Stop
        Test-ClaudeDiagnosticPath $bin
        $lockPath = Join-Path $bin 'route.lock' -ErrorAction Stop
        $report.reason = 'lock_missing'
        if (-not (Test-Path -LiteralPath $lockPath -ErrorAction Stop)) { return $report }
        $report.reason = 'lock_unavailable'
        Test-ClaudeDiagnosticPath $lockPath
        # Open, not OpenOrCreate; read-only handle and no file writes.
        $lock = [IO.File]::Open($lockPath, [IO.FileMode]::Open,
            [IO.FileAccess]::Read, [IO.FileShare]::None)
        $manifest = Read-ClaudeDiagnosticText (Join-Path $bin 'profiles.json')
        $marker = Read-ClaudeDiagnosticText (Join-Path $bin 'target.txt')
        $report.snapshot = 'locked'; $report.reason = 'none'
        $report.manifest = $manifest.state
        if ($manifest.state -eq 'present') {
            $report.manifest = 'invalid'
            try {
                $cfg = ConvertFrom-Json -InputObject $manifest.text -ErrorAction Stop
                if ($cfg -is [pscustomobject] -and $cfg.profiles -is [pscustomobject] -and
                    @($cfg.profiles.PSObject.Properties).Count -gt 0) { $report.manifest = 'readable' }
            } catch { }
        }
        Set-ClaudeDiagnosticIntent $report $marker $manifest ([datetimeoffset]::UtcNow.ToUnixTimeMilliseconds())
    } catch {
        $report.snapshot = 'unavailable'
        $report.manifest = 'unknown'; $report.intent = 'unknown'
        $report.expiration = 'unknown'; $report.binding = 'unknown'
    } finally { if ($null -ne $lock) { $lock.Dispose() } }
    return $report
}

if ($MyInvocation.InvocationName -ne '.') {
    Invoke-ClaudeRoutingDiagnostic -InstallDir $InstallDir 2>$null 3>$null 4>$null 5>$null 6>$null |
        ConvertTo-Json -Compress
}
