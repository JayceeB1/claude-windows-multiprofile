<#
.SYNOPSIS
    Launches one Claude Desktop profile and gives it its own taskbar button and icon.
.DESCRIPTION
    Starts the profile exactly as Launch-Claude.ps1 does (same executable resolution,
    --user-data-dir and CLAUDE_CONFIG_DIR handling), then keeps a hidden watcher that
    sets an AppUserModelID and the window icons on that profile's windows until it exits.
    If the profile is already running, only the watcher is started.
.PARAMETER ProfileDir
    Absolute Desktop data directory of the profile.
.PARAMETER ConfigDir
    Optional absolute Claude Code config directory for the child process.
.PARAMETER AppId
    AppUserModelID shared by the windows and by the pinned shortcut.
.PARAMETER IconPath
    .ico file shown on the taskbar button.
.NOTES
    Windows PowerShell 5.1 and PowerShell 7, no admin rights. Run it from a normal
    shell or a shortcut. Dot-sourcing defines functions only.
#>
[CmdletBinding()]
param([string]$ProfileDir, [string]$ConfigDir, [string]$AppId, [string]$IconPath)

# Dot-sourcing Launch-Claude.ps1 re-runs its own param block in this scope and would
# blank same-named variables: keep our values first.
$requested = @{ ProfileDir = $ProfileDir; ConfigDir = $ConfigDir; AppId = $AppId; IconPath = $IconPath }
$here = Split-Path -Parent $PSCommandPath
. (Join-Path $here 'Launch-Claude.ps1')
. (Join-Path $here 'Set-ClaudeWindowIdentity.ps1')

function Invoke-ClaudeIdentityLauncher {
    param([string]$ProfileDir, [string]$ConfigDir, [string]$AppId, [string]$IconPath)
    if ([string]::IsNullOrWhiteSpace($AppId) -or $AppId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$') {
        throw 'AppId must be 3-128 letters, digits, dots, dashes or underscores.'
    }
    if (-not (Test-Path -LiteralPath $IconPath -PathType Leaf)) { throw 'IconPath is missing.' }
    $dataDir = Resolve-ClaudeDirectoryPath $ProfileDir 'ProfileDir'
    if (-not (Get-ClaudeProfileProcessId -DataDir $dataDir)) {
        Invoke-ClaudeLauncher -ProfileDir $dataDir -ConfigDir $ConfigDir
    }
    Watch-ClaudeWindowIdentity -DataDir $dataDir -AppId $AppId -IconPath $IconPath
}

if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    try {
        Invoke-ClaudeIdentityLauncher -ProfileDir $requested.ProfileDir -ConfigDir $requested.ConfigDir `
            -AppId $requested.AppId -IconPath $requested.IconPath
    }
    catch {
        Show-Error $_.Exception.Message
        exit 1
    }
}
