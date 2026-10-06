<#
.SYNOPSIS
    Installs (or removes) the taskbar identity launcher for one extra Claude profile.
.DESCRIPTION
    Copies the identity scripts and the supplied icon to <InstallDir>\identity (a new
    folder, never the receipt-owned bin folder) and creates one shortcut that launches the
    profile with its own taskbar button and icon. Pin that shortcut to the taskbar once.
    Preview by default: nothing is written without -Apply. Existing files and shortcuts
    that this tool does not own are refused, never overwritten. -Remove deletes only what
    this tool created, as recorded in identity.json. Profile data, config, the official
    package, registry and the receipt-owned launcher are never touched.
.PARAMETER Name
    Profile label used in names and the AppUserModelID (default B).
.PARAMETER ProfileDir
    Absolute Desktop data directory of the profile.
.PARAMETER ConfigDir
    Optional absolute Claude Code config directory of the profile.
.PARAMETER IconPath
    The .ico to show (required unless -Remove).
.PARAMETER InstallDir
    Parent folder; the tool writes only to its identity subfolder (default %USERPROFILE%\ClaudeProfiles).
.PARAMETER ShortcutFolder
    Folder of the shortcut (default: Desktop).
.PARAMETER ShortcutName
    Shortcut name without extension (default "Claude (<Name>)").
.PARAMETER AppId
    AppUserModelID (default ClaudeMultiprofile.<Name>).
.PARAMETER Apply
    Perform the installation or removal.
.PARAMETER Remove
    Remove what a previous -Apply created.
.NOTES
    Windows PowerShell 5.1 and PowerShell 7, no admin rights. A pinned taskbar copy of
    the shortcut is the user's: unpin it by hand after -Remove.
.EXAMPLE
    .\Install-ClaudeIdentity.ps1 -ProfileDir "$env:APPDATA\Claude-B" -ConfigDir "$env:USERPROFILE\.claude-b" -IconPath C:\icons\claude-b.ico -Apply
#>
[CmdletBinding()]
param(
    [string]$Name = 'B',
    [string]$ProfileDir,
    [string]$ConfigDir = '',
    [string]$IconPath,
    [string]$InstallDir = (Join-Path $env:USERPROFILE 'ClaudeProfiles'),
    [string]$ShortcutFolder = [Environment]::GetFolderPath('Desktop'),
    [string]$ShortcutName,
    [string]$AppId,
    [switch]$Apply,
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $PSCommandPath
$marker = 'claude-windows-multiprofile identity'
$files = 'Launch-Claude.ps1', 'Set-ClaudeWindowIdentity.ps1', 'Launch-ClaudeIdentity.ps1', 'launch-identity.vbs'

if ($Name -notmatch '^[A-Za-z0-9]{1,16}$') { throw 'Name must be 1-16 letters or digits.' }
if (-not $ShortcutName) { $ShortcutName = "Claude ($Name)" }
if ($ShortcutName -match '[\\/:*?"<>|]') { throw 'ShortcutName contains invalid characters.' }
if (-not $AppId) { $AppId = "ClaudeMultiprofile.$Name" }
if ($AppId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$') { throw 'AppId is invalid.' }

$identityDir = Join-Path $InstallDir 'identity'
$manifestPath = Join-Path $identityDir 'identity.json'
$shortcutPath = Join-Path $ShortcutFolder ($ShortcutName + '.lnk')
$iconTarget = Join-Path $identityDir ("claude-{0}.ico" -f $Name.ToLowerInvariant())
$wscript = Join-Path ([Environment]::GetFolderPath('System')) 'wscript.exe'

function Get-Sha256 { param([string]$Path) (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
function Get-OwnedShortcutState {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return 'absent' }
    $wsh = New-Object -ComObject WScript.Shell
    if ($wsh.CreateShortcut($Path).Description -like "$marker*") { return 'owned' }
    return 'foreign'
}
function Read-Manifest {
    if (-not (Test-Path -LiteralPath $manifestPath)) { return $null }
    return Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
}

$manifest = Read-Manifest
$shortcutState = Get-OwnedShortcutState $shortcutPath

if ($Remove) {
    Write-Host "Remove plan: shortcut '$shortcutPath' ($shortcutState); files in '$identityDir' recorded in identity.json."
    if (-not $Apply) { Write-Host 'Preview only. Re-run with -Apply to remove.'; return }
    if ($shortcutState -eq 'owned') { Remove-Item -LiteralPath $shortcutPath -Force }
    elseif ($shortcutState -eq 'foreign') { Write-Warning 'Shortcut is not owned by this tool: left in place.' }
    if ($manifest) {
        foreach ($entry in $manifest.files.PSObject.Properties) {
            $path = Join-Path $identityDir $entry.Name
            if ((Test-Path -LiteralPath $path) -and (Get-Sha256 $path) -eq $entry.Value) { Remove-Item -LiteralPath $path -Force }
            elseif (Test-Path -LiteralPath $path) { Write-Warning "$($entry.Name) was modified: left in place." }
        }
        Remove-Item -LiteralPath $manifestPath -Force
        if (-not (Get-ChildItem -LiteralPath $identityDir -Force)) { Remove-Item -LiteralPath $identityDir -Force }
    }
    Write-Host 'Removed. Unpin the taskbar copy by hand if you pinned one.'
    return
}

if (-not $ProfileDir -or $ProfileDir -notmatch '^[A-Za-z]:[\\/]') { throw 'ProfileDir must be an absolute Windows path.' }
if ($ConfigDir -and $ConfigDir -notmatch '^[A-Za-z]:[\\/]') { throw 'ConfigDir must be an absolute Windows path.' }
if (-not $IconPath -or -not (Test-Path -LiteralPath $IconPath -PathType Leaf) -or [IO.Path]::GetExtension($IconPath) -ne '.ico') {
    throw 'IconPath must be an existing .ico file.'
}
if ($shortcutState -eq 'foreign') { throw "A shortcut named '$ShortcutName' already exists and is not owned by this tool." }

# Plan every destination before writing anything; refuse anything we do not own.
$plan = @()
foreach ($f in $files) {
    $dest = Join-Path $identityDir $f
    $source = Join-Path $scriptRoot $f
    $hash = Get-Sha256 $source
    if (Test-Path -LiteralPath $dest) {
        $current = Get-Sha256 $dest
        $owned = $manifest -and $manifest.files.PSObject.Properties.Name -contains $f -and $manifest.files.$f -eq $current
        if ($current -ne $hash -and -not $owned) { throw "'$dest' exists and is not owned by this tool." }
    }
    $plan += [pscustomobject]@{ Source = $source; Dest = $dest; Hash = $hash }
}
if (Test-Path -LiteralPath $iconTarget) {
    $iconOwned = $manifest -and $manifest.files.PSObject.Properties.Name -contains (Split-Path -Leaf $iconTarget) -and
        $manifest.files.(Split-Path -Leaf $iconTarget) -eq (Get-Sha256 $iconTarget)
    if ((Get-Sha256 $iconTarget) -ne (Get-Sha256 $IconPath) -and -not $iconOwned) { throw "'$iconTarget' exists and is not owned by this tool." }
}
$plan += [pscustomobject]@{ Source = $IconPath; Dest = $iconTarget; Hash = (Get-Sha256 $IconPath) }

$arguments = '"{0}" "{1}" "{2}" "{3}" "{4}"' -f (Join-Path $identityDir 'launch-identity.vbs'),
    ($ProfileDir.TrimEnd('\', '/')), $ConfigDir.TrimEnd('\', '/'), $AppId, $iconTarget
# wscript.exe's own arguments are the .vbs first, then its parameters.
Write-Host "Install plan (profile '$Name', AppUserModelID '$AppId'):"
$plan | ForEach-Object { Write-Host ("  copy {0} -> {1}" -f (Split-Path -Leaf $_.Source), $_.Dest) }
Write-Host "  shortcut '$shortcutPath' ($shortcutState): $wscript $arguments"
if (-not $Apply) { Write-Host 'Preview only. Re-run with -Apply to install.'; return }

New-Item -ItemType Directory -Force -Path $identityDir | Out-Null
$recorded = [ordered]@{}
foreach ($item in $plan) {
    Copy-Item -LiteralPath $item.Source -Destination $item.Dest -Force
    $recorded[(Split-Path -Leaf $item.Dest)] = $item.Hash
}
[ordered]@{ schema = 1; appId = $AppId; name = $Name; shortcut = $shortcutPath; files = $recorded } |
    ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

. (Join-Path $identityDir 'Set-ClaudeWindowIdentity.ps1')
New-Item -ItemType Directory -Force -Path $ShortcutFolder | Out-Null
New-ClaudeIdentityShortcut -Path $shortcutPath -Target $wscript -Arguments $arguments `
    -WorkingDirectory $identityDir -IconPath $iconTarget -AppId $AppId -Description "$marker ($Name)"
Write-Host "Installed. Pin '$ShortcutName' to the taskbar once (right-click > Pin to taskbar); launching it from there needs no script."
