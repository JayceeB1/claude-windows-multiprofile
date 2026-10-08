<#
.SYNOPSIS
    Dispatches only explicitly armed Claude profiles; never guesses a target.
.DESCRIPTION
    target.txt is now a versioned, expiring one-shot intent, bound to the exact
    profiles.json text. Legacy path/default markers are rejected. The armer and
    dispatcher share a nonblocking exclusive file lock. The intent is consumed
    BEFORE discovery/launch, so a retry cannot reuse it or silently fall back.
    Only fixed event codes reach route.log. Full callbacks remain in launch args.
.PARAMETER Url
    Absolute claude:// link from Windows. No prompt on missing/invalid input.
.NOTES
    Requires the sibling Launch-Claude.ps1 installed by Setup. Windows PS 5.1/7.
    This is local routing intent, NOT OAuth state/PKCE verification. Initiate
    only one browser login at a time; delayed callbacks from an older login can
    still consume a newly armed intent. Actual authentication belongs to Claude.
    No credentials, existing profile contents or protocol registrations are read
    or modified. New routing metadata only; no forced restart of an existing app.
#>
param([string]$Url)
$Base = $PSScriptRoot
$TargetFile = Join-Path $Base 'target.txt'
$LogFile = Join-Path $Base 'route.log'

# Kept for the existing argument tests; production never selects 'default'.
function Get-ClaudeLaunchArgString {
    param([string]$Target, [string]$Url)
    if ($Target -eq 'default') { return "`"$Url`"" }
    $quoted = $Target -replace '(\\+)$', '$1$1'
    return "--user-data-dir=`"$quoted`" `"$Url`""
}

function Write-ClaudeRouteEvent {
    param(
        [ValidateSet('MISSING_URL', 'INVALID_URL', 'ROUTE_BUSY', 'TARGET_READ_FAILED',
            'APP_DISCOVERY_FAILED', 'APP_NOT_FOUND', 'ARGUMENT_BUILD_FAILED',
            'LAUNCH_REQUESTED', 'LAUNCH_FAILED', 'RESET_FAILED', 'DISPATCH_COMPLETE')]
        [string]$Event,
        [ValidateSet('unknown', 'stock', 'profile')][string]$TargetKind = 'unknown'
    )
    try {
        Add-Content -LiteralPath $LogFile -ErrorAction Stop -Value (
            '{0} event={1} target={2}' -f (Get-Date -Format s), $Event, $TargetKind)
        return $true
    } catch { return $false }
}

function Open-ClaudeRouteLock {
    # Same directory and same lock for arming, disarming and dispatching. Do not
    # delete the lock file on release: a replacement would create two locks.
    return [IO.File]::Open((Join-Path $Base 'route.lock'),
        [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
}

function Read-ClaudeRouteText {
    param([ValidateSet('target.txt', 'profiles.json')][string]$Name, [switch]$Optional)
    $path = Join-Path $Base $Name
    if (-not (Test-Path -LiteralPath $path -ErrorAction Stop)) {
        if ($Optional) { return '' }
        throw 'ROUTE_METADATA_MISSING'
    }
    $file = Get-Item -LiteralPath $path -Force -ErrorAction Stop
    if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        $file.Length -gt 65536) { throw 'ROUTE_METADATA_INVALID' }
    return [IO.File]::ReadAllText($path)
}

function Set-ClaudeRouteText {
    param([string]$Text)
    # Write/flush a new file first; replace only the known routing marker.
    # A crash before replacement leaves the previous intent; a crash after
    # consumption leaves a tombstone, never a reusable pre-launch marker.
    $temp = $TargetFile + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    $stream = $null
    try {
        $stream = [IO.File]::Open($temp, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
        $stream.Dispose(); $stream = $null
        if ([IO.File]::Exists($TargetFile)) {
            $existing = Get-Item -LiteralPath $TargetFile -Force -ErrorAction Stop
            if ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'ROUTE_MARKER_ALIAS' }
            # PowerShell coerces $null to an empty string for this .NET string
            # parameter. NullString sends an actual null (no backup filename).
            [IO.File]::Replace($temp, $TargetFile, [System.Management.Automation.Language.NullString]::Value)
        } else { [IO.File]::Move($temp, $TargetFile) }
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
        if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) }
    }
}

function Get-ClaudeRouteHash {
    param([string]$Text)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-', '') }
    finally { $sha.Dispose() }
}

function Resolve-ClaudeRoutePath {
    param([string]$Path)
    # Local absolute paths only for authentication/config roots. Reject root,
    # ADS, devices, trailing-dot/space aliases and argument-breaking characters.
    if ($Path -notmatch '^[A-Za-z]:[\\/]' -or $Path -match '[\x00-\x1f"*?<>|]' -or
        $Path.Substring(2).Contains(':') -or $Path -match '[. ](?:[\\/]|$)') {
        throw 'ROUTE_PATH_INVALID'
    }
    $full = [IO.Path]::GetFullPath($Path).TrimEnd([char[]]'\/')
    if ($full.Length -le 2) { throw 'ROUTE_PATH_ROOT' }
    return $full
}

function Get-ClaudeRoutePlan {
    param([string]$ManifestText, [string]$Profile)
    $cfg = ConvertFrom-Json -InputObject $ManifestText -ErrorAction Stop
    if ($cfg -isnot [pscustomobject] -or $cfg.profiles -isnot [pscustomobject]) { throw 'ROUTE_MANIFEST_INVALID' }
    $entries = @($cfg.profiles.PSObject.Properties)
    if ($entries.Count -lt 1 -or $entries.Count -gt 32) { throw 'ROUTE_MANIFEST_INVALID' }
    $names = @{}; $roots = [System.Collections.Generic.List[string]]::new(); $selected = $null
    foreach ($entry in $entries) {
        if ($entry.Name -ieq 'default' -or $names.ContainsKey($entry.Name)) { throw 'ROUTE_NAME_AMBIGUOUS' }
        $names[$entry.Name] = $true
        $value = $entry.Value
        if ($value -isnot [pscustomobject] -or $value.dataDir -isnot [string] -or
            $value.configDir -isnot [string] -or $value.isDefault -isnot [bool]) { throw 'ROUTE_PROFILE_INVALID' }
        $data = Resolve-ClaudeRoutePath $value.dataDir
        $config = ''
        if ($value.configDir -ne '') { $config = Resolve-ClaudeRoutePath $value.configDir }
        $effectiveConfig = if ($config) { $config } else { Resolve-ClaudeRoutePath (Join-Path $env:USERPROFILE '.claude') }
        foreach ($root in @($data, $effectiveConfig)) {
            foreach ($previous in $roots) {
                if ($root.Equals($previous, [StringComparison]::OrdinalIgnoreCase) -or
                    $root.StartsWith($previous + '\', [StringComparison]::OrdinalIgnoreCase) -or
                    $previous.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'ROUTE_ROOTS_OVERLAP' }
            }
            $roots.Add($root)
        }
        if ($entry.Name -ieq $Profile) {
            $selected = [pscustomobject]@{
                Profile = $entry.Name; DataDir = $data; ConfigDir = $config
                Kind = 'profile'; ManifestHash = (Get-ClaudeRouteHash $ManifestText)
            }
        }
    }
    if ($null -eq $selected) { throw 'ROUTE_PROFILE_UNKNOWN' }
    # No meaning is inferred from isDefault or defaultProfile for dispatch.
    # In particular, a custom existing A config remains explicit and intact.
    return $selected
}

function New-ClaudeRouteIntent {
    param($Plan, [datetimeoffset]$Now = [datetimeoffset]::UtcNow)
    return ([ordered]@{
        version = 2; status = 'armed'; profile = $Plan.Profile
        manifestHash = $Plan.ManifestHash; createdMs = $Now.ToUnixTimeMilliseconds()
        expiresMs = $Now.AddMinutes(5).ToUnixTimeMilliseconds()
    } | ConvertTo-Json -Compress)
}

function Resolve-ClaudeRouteIntent {
    param([string]$Text, [string]$ManifestText, [datetimeoffset]$Now = [datetimeoffset]::UtcNow)
    $intent = ConvertFrom-Json -InputObject $Text -ErrorAction Stop
    if ($intent -isnot [pscustomobject] -or $intent.version -isnot [ValueType] -or
        $intent.version -ne 2 -or $intent.status -cne 'armed') {
        throw 'ROUTE_NOT_ARMED'
    }
    $keys = @($intent.PSObject.Properties.Name)
    $wanted = @('version', 'status', 'profile', 'manifestHash', 'createdMs', 'expiresMs')
    if (@(Compare-Object $wanted $keys).Count -ne 0 -or $keys.Count -ne 6 -or
        $intent.profile -isnot [string] -or $intent.manifestHash -isnot [string]) { throw 'ROUTE_INTENT_INVALID' }
    # Numeric milliseconds stay exact in PS 5.1/7 JSON readers and avoid their
    # differing automatic conversion of ISO strings into DateTime objects.
    if (($intent.createdMs -isnot [long] -and $intent.createdMs -isnot [int]) -or
        ($intent.expiresMs -isnot [long] -and $intent.expiresMs -isnot [int])) { throw 'ROUTE_TIME_INVALID' }
    $nowMs = $Now.ToUnixTimeMilliseconds()
    if ($intent.createdMs -lt 0 -or $intent.createdMs -gt $nowMs -or
        $intent.expiresMs -le $nowMs -or ($intent.expiresMs - $intent.createdMs) -ne 300000) {
        throw 'ROUTE_INTENT_EXPIRED'
    }
    if ($intent.manifestHash -cne (Get-ClaudeRouteHash $ManifestText)) { throw 'ROUTE_MANIFEST_CHANGED' }
    return Get-ClaudeRoutePlan -ManifestText $ManifestText -Profile $intent.profile
}

function New-ClaudeCallbackStartInfo {
    param([string]$ExecutablePath, $Plan, [string]$Callback)
    # Import only functions; the launcher's dot-source guard prevents execution.
    . (Join-Path $Base 'Launch-Claude.ps1')
    $info = New-ClaudeStartInfo -ExecutablePath $ExecutablePath -ProfileDir $Plan.DataDir -ConfigDir $Plan.ConfigDir
    $info.Arguments += ' "' + $Callback + '"'
    return $info
}

function Start-ClaudeCallbackProcess {
    param([System.Diagnostics.ProcessStartInfo]$StartInfo)
    $process = [Diagnostics.Process]::Start($StartInfo)
    if ($null -eq $process) { throw 'ROUTE_PROCESS_MISSING' }
    $process.Dispose()
}

function Invoke-ClaudeShim {
    param([string]$Url)
    $ErrorActionPreference = 'Stop'
    $targetKind = 'unknown'; $failureEvent = 'INVALID_URL'; $lock = $null
    try {
        if ([string]::IsNullOrWhiteSpace($Url)) {
            $null = Write-ClaudeRouteEvent -Event MISSING_URL
            return 1
        }
        $uri = $null
        if ($Url.Length -gt 16384 -or $Url -match '[\x00-\x20"\\]' -or
            -not [uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$uri) -or
            $uri.Scheme -cne 'claude' -or [string]::IsNullOrEmpty($uri.Host) -or $uri.UserInfo) {
            throw 'ROUTE_CALLBACK_INVALID'
        }
        $failureEvent = 'ROUTE_BUSY'
        $lock = Open-ClaudeRouteLock
        $failureEvent = 'TARGET_READ_FAILED'
        $text = Read-ClaudeRouteText 'target.txt'
        $manifest = Read-ClaudeRouteText 'profiles.json'
        $plan = Resolve-ClaudeRouteIntent -Text $text -ManifestText $manifest
        $targetKind = $plan.Kind
        # Consume BEFORE discovery/launch and never reset after launch. Hold the
        # lock through dispatch so arming and another callback cannot race us.
        $failureEvent = 'RESET_FAILED'
        Set-ClaudeRouteText '{"version":2,"status":"consumed"}'
        $failureEvent = 'APP_DISCOVERY_FAILED'
        $pkg = Get-AppxPackage -Name '*Claude*' -ErrorAction Stop |
            Sort-Object Version -Descending | Select-Object -First 1
        $exe = if ($pkg) { Join-Path $pkg.InstallLocation 'app\Claude.exe' }
        if (-not $exe -or -not (Test-Path -LiteralPath $exe -ErrorAction Stop)) {
            $null = Write-ClaudeRouteEvent -Event APP_NOT_FOUND -TargetKind $targetKind
            return 1
        }
        $failureEvent = 'ARGUMENT_BUILD_FAILED'
        $info = New-ClaudeCallbackStartInfo -ExecutablePath $exe -Plan $plan -Callback $Url
        if (-not (Write-ClaudeRouteEvent -Event LAUNCH_REQUESTED -TargetKind $targetKind)) { return 1 }
        $failureEvent = 'LAUNCH_FAILED'
        $null = Start-ClaudeCallbackProcess -StartInfo $info
        if (-not (Write-ClaudeRouteEvent -Event DISPATCH_COMPLETE -TargetKind $targetKind)) { return 1 }
        return 0
    } catch {
        $null = Write-ClaudeRouteEvent -Event $failureEvent -TargetKind $targetKind
        return 1
    } finally {
        if ($null -ne $lock) { try { $lock.Dispose() } catch { } }
    }
}

if ($MyInvocation.InvocationName -ne '.') { exit (Invoke-ClaudeShim -Url $Url) }
