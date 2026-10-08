<#
.SYNOPSIS
    Launches the installed Claude Desktop app with an explicit profile.
.DESCRIPTION
    Resolves the MSIX executable dynamically. A separate --user-data-dir keeps
    Desktop profiles apart. The child receives its own CLAUDE_CONFIG_DIR value;
    the caller's process, user and machine environments are never changed.
    No cookies, credentials, history or memory files are copied or inspected.
.PARAMETER ProfileDir
    Required when launching: an absolute Windows directory. Paths with spaces
    are quoted as a single argument, including a trailing backslash.
.PARAMETER ConfigDir
    Absolute Claude Code config directory. Omitted or empty means the stock
    config: remove CLAUDE_CONFIG_DIR from the CHILD environment, even if the
    caller has it set. To use a custom config, always pass it explicitly.
.NOTES
    Windows PowerShell 5.1 and PowerShell 7. Dot-sourcing defines functions only.
    An already-running Desktop keeps its original environment; quit/reopen that
    profile after changing its config. OAuth callback routing is a separate path
    and is not qualified by this launcher alone.
.EXAMPLE
    .\Launch-Claude.ps1 -ProfileDir "$env:APPDATA\Claude-Work" -ConfigDir "$env:USERPROFILE\.claude-work"
#>
[CmdletBinding()]
param([string]$ProfileDir, [string]$ConfigDir)

function Resolve-ClaudeDirectoryPath {
    param([string]$Value, [string]$ParameterName)
    # Reject relative/provider/device paths and argument-breaking characters.
    # Only drive-absolute and ordinary UNC paths are accepted; no filesystem IO.
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -match '[\x00-\x1f"*?<>|]' -or
        $Value -match '^\\\\[.?]\\' -or
        $Value -notmatch '^(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$))') {
        throw "$ParameterName must be an absolute Windows directory without invalid characters."
    }
    return [IO.Path]::GetFullPath($Value)
}

function New-ClaudeStartInfo {
    param([string]$ExecutablePath, [string]$ProfileDir, [string]$ConfigDir)
    $profilePath = Resolve-ClaudeDirectoryPath $ProfileDir 'ProfileDir'
    $configPath = $null
    if (-not [string]::IsNullOrEmpty($ConfigDir)) {
        $configPath = Resolve-ClaudeDirectoryPath $ConfigDir 'ConfigDir'
    }
    if ([string]::IsNullOrWhiteSpace($ExecutablePath)) { throw 'Claude executable is missing.' }

    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $ExecutablePath
    $info.UseShellExecute = $false
    # Use .Arguments for .NET Framework / PowerShell 5.1 compatibility. Quotes
    # cannot occur in a validated path; double trailing backslashes before the
    # closing quote so Windows does not parse it as an escaped literal quote.
    $quotedPath = $profilePath -replace '(\\+)$', '$1$1'
    $info.Arguments = '--user-data-dir="{0}"' -f $quotedPath
    # Materialize the inherited environment, but edit only the child's copy.
    $childEnvironment = $info.EnvironmentVariables
    $childEnvironment.Remove('CLAUDE_CONFIG_DIR')
    if ($configPath) { $childEnvironment['CLAUDE_CONFIG_DIR'] = $configPath }
    return $info
}

function Get-ClaudeExecutable {
    $exe = $null
    try {
        $pkg = Get-AppxPackage -Name '*Claude*' -ErrorAction Stop |
            Sort-Object Version -Descending | Select-Object -First 1
        if ($pkg) {
            $candidate = Join-Path $pkg.InstallLocation 'app\Claude.exe'
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { $exe = $candidate }
        }
    } catch { }
    # Retain the upstream MSIX-only fallback. Never use a stale Squirrel exe.
    if (-not $exe) {
        $exe = Get-ChildItem 'C:\Program Files\WindowsApps\Claude_*__*\app\Claude.exe' -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $exe -or -not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw 'Claude Desktop app was not found. Install the official app, then run again.'
    }
    return $exe
}

function Initialize-ClaudeDirectory {
    param([string]$Path)
    # Literal .NET path handling: brackets are not treated as wildcard syntax.
    $null = [IO.Directory]::CreateDirectory($Path)
}

function Start-ClaudeDesktopProcess {
    param([System.Diagnostics.ProcessStartInfo]$StartInfo)
    $process = [System.Diagnostics.Process]::Start($StartInfo)
    if ($null -eq $process) { throw 'Windows did not return a Claude process.' }
    # Release our handle, not the running application; do not wait or kill it.
    $process.Dispose()
}

function Invoke-ClaudeLauncher {
    param([string]$ProfileDir, [string]$ConfigDir)
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'This launcher requires Windows.'
    }
    # Validate both inputs before discovery or writes. The builder repeats this
    # validation so callers using it independently receive the same safeguards.
    $profilePath = Resolve-ClaudeDirectoryPath $ProfileDir 'ProfileDir'
    $configPath = ''
    if (-not [string]::IsNullOrEmpty($ConfigDir)) {
        $configPath = Resolve-ClaudeDirectoryPath $ConfigDir 'ConfigDir'
    }
    $exe = Get-ClaudeExecutable
    $info = New-ClaudeStartInfo -ExecutablePath $exe -ProfileDir $profilePath -ConfigDir $configPath
    Initialize-ClaudeDirectory -Path $profilePath
    if ($configPath) { Initialize-ClaudeDirectory -Path $configPath }
    Start-ClaudeDesktopProcess -StartInfo $info
}

function Show-Error {
    param([string]$Message)
    try {
        Add-Type -AssemblyName PresentationFramework -ErrorAction Stop
        [System.Windows.MessageBox]::Show($Message, 'claude-desktop-clone', 'OK', 'Error') | Out-Null
    } catch {
        Write-Error $Message
    }
}

# Test imports must not resolve MSIX, create directories, launch or show a dialog.
if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    try { Invoke-ClaudeLauncher -ProfileDir $ProfileDir -ConfigDir $ConfigDir }
    catch {
        Show-Error $_.Exception.Message
        exit 1
    }
}
