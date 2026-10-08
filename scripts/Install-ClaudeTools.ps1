<#
.SYNOPSIS
    Creates (or removes) the desktop folder with the repair, reconnect and manual shortcuts.
.DESCRIPTION
    Makes <Desktop>\Claude multi-comptes with three shortcuts that run this repository's
    scripts directly (no copy, so a repository update is picked up at once):
      - Réparer Claude (A+B)   : Repair-ClaudeProfiles.ps1 -Fix -Pause
      - Reconnecter B          : Connect-ClaudeProfile.ps1 -Profile B -Pause
      - Mode opératoire        : docs\fr\MODE-OPERATOIRE.md
    Preview by default; nothing is written without -Apply. Shortcuts it did not create are
    refused, never overwritten; -Remove deletes only its own. If you move the repository,
    run this again with -Apply.
.PARAMETER RepoDir
    Folder of this repository (default: the parent of this script's folder).
.PARAMETER InstallDir
    Parent folder of the installation (default %USERPROFILE%\ClaudeProfiles).
.PARAMETER ShortcutFolder
    Folder that receives the shortcuts (default <Desktop>\Claude multi-comptes).
.PARAMETER IconPath
    Optional .ico for the reconnect shortcut (default: the identity icon when installed).
.PARAMETER Apply
    Perform the installation or removal.
.PARAMETER Remove
    Remove what a previous -Apply created.
.NOTES
    Windows PowerShell 5.1 and PowerShell 7, no admin rights.
#>
[CmdletBinding()]
param(
    [string]$RepoDir,
    [string]$InstallDir = (Join-Path $env:USERPROFILE 'ClaudeProfiles'),
    [string]$ShortcutFolder = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Claude multi-comptes'),
    [string]$IconPath,
    [switch]$Apply,
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $PSCommandPath
if (-not $RepoDir) { $RepoDir = Split-Path -Parent $scriptRoot }
$marker = 'claude-windows-multiprofile tools'
. (Join-Path $scriptRoot 'Set-ClaudeWindowIdentity.ps1')

$powershell = Join-Path ([Environment]::GetFolderPath('System')) 'WindowsPowerShell\v1.0\powershell.exe'
$common = '-NoProfile -ExecutionPolicy Bypass -File'
if (-not $IconPath) {
    $candidate = Join-Path $InstallDir 'identity\claude-b.ico'
    $IconPath = if (Test-Path -LiteralPath $candidate) { $candidate } else { "$powershell,0" }
}
$items = @(
    @{ Name = 'Réparer Claude (A+B)'; Target = $powershell; Icon = "$powershell,0"
       Arguments = "$common `"$(Join-Path $RepoDir 'scripts\Repair-ClaudeProfiles.ps1')`" -InstallDir `"$InstallDir`" -Fix -Pause" },
    @{ Name = 'Reconnecter B'; Target = $powershell; Icon = $IconPath
       Arguments = "$common `"$(Join-Path $RepoDir 'scripts\Connect-ClaudeProfile.ps1')`" -Profile B -InstallDir `"$InstallDir`" -Pause" },
    @{ Name = 'Mode opératoire'; Target = (Join-Path $RepoDir 'docs\fr\MODE-OPERATOIRE.md'); Icon = ''; Arguments = '' }
)

function Get-ShortcutState {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return 'absent' }
    $wsh = New-Object -ComObject WScript.Shell
    if ($wsh.CreateShortcut($Path).Description -like "$marker*") { return 'owned' }
    return 'foreign'
}

$plan = foreach ($item in $items) {
    $path = Join-Path $ShortcutFolder ($item.Name + '.lnk')
    [pscustomobject]@{ Item = $item; Path = $path; State = Get-ShortcutState $path }
}

if ($Remove) {
    $plan | ForEach-Object { Write-Host ("  remove {0} ({1})" -f $_.Path, $_.State) }
    if (-not $Apply) { Write-Host 'Preview only. Re-run with -Apply to remove.'; return }
    foreach ($p in $plan) {
        if ($p.State -eq 'owned') { Remove-Item -LiteralPath $p.Path -Force }
        elseif ($p.State -eq 'foreign') { Write-Warning "$($p.Path) is not owned by this tool: left in place." }
    }
    if ((Test-Path -LiteralPath $ShortcutFolder) -and -not (Get-ChildItem -LiteralPath $ShortcutFolder -Force)) { Remove-Item -LiteralPath $ShortcutFolder -Force }
    Write-Host 'Removed.'
    return
}

foreach ($p in $plan) { if ($p.State -eq 'foreign') { throw "'$($p.Path)' already exists and is not owned by this tool." } }
foreach ($p in $plan) {
    $needed = if ($p.Item.Name -eq 'Mode opératoire') { $p.Item.Target } else { Join-Path $RepoDir 'scripts' }
    if (-not (Test-Path -LiteralPath $needed)) { throw "Missing in the repository: $needed" }
}
Write-Host "Install plan (repository '$RepoDir'):"
$plan | ForEach-Object { Write-Host ("  {0} -> {1} ({2})" -f $_.Item.Name, $_.Path, $_.State) }
if (-not $Apply) { Write-Host 'Preview only. Re-run with -Apply to install.'; return }

New-Item -ItemType Directory -Force -Path $ShortcutFolder | Out-Null
foreach ($p in $plan) {
    $icon = if ($p.Item.Icon) { $p.Item.Icon } else { $p.Item.Target }
    New-ClaudeIdentityShortcut -Path $p.Path -Target $p.Item.Target -Arguments $p.Item.Arguments -WorkingDirectory $RepoDir `
        -IconPath $icon -Description "$marker ($($p.Item.Name))"
}
Write-Host "Installed in '$ShortcutFolder'."
