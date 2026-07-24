<#
.SYNOPSIS
    claude:// protocol handler that routes deep links (e.g. browser SSO
    callbacks) to a chosen Claude Desktop profile.

.DESCRIPTION
    Windows hands every claude:// activation to a single registered handler.
    When multiple isolated Claude Desktop profiles are running (see
    Setup.ps1 / Launch-Claude.ps1), the OS would otherwise deliver the SSO
    callback to whichever profile owns the protocol -- typically the default
    one -- so a work login can silently land in the personal profile.

    This shim is registered as that handler. On each activation it reads a
    one-line marker file (target.txt) that names the profile data directory the
    NEXT login should go to, launches Claude with the matching --user-data-dir,
    logs the routing decision to route.log, then resets the marker back to
    'default' so an unrelated later login can't silently land in the wrong
    profile.

    Arm the desired target with Arm-ClaudeLogin.ps1 before starting a login.

    See docs/PROTOCOL-ROUTING.md for the full delivery-chain model and the
    route.log triage table.

.PARAMETER Url
    The claude:// URL Windows passes on activation (the handler command
    registers this as "%1"). Not marked Mandatory on purpose: the OS always
    supplies it, and a Mandatory parameter with no value would PROMPT -- which,
    under the headless conhost host this runs in, would hang the activation
    invisibly. Instead a missing URL is logged as an error and the shim exits.

.NOTES
    Runs under Windows PowerShell 5.1. Keep it self-contained: it is in the
    critical path for ALL claude:// activations, so it must not depend on
    sibling scripts being present or importable at activation time.
#>
param([string]$Url)

$Base       = $PSScriptRoot
$TargetFile = Join-Path $Base 'target.txt'
$LogFile    = Join-Path $Base 'route.log'

# Builds the single, pre-quoted argument string handed to Start-Process.
#
# CRITICAL (PowerShell 5.1): Start-Process -ArgumentList joins array elements
# with spaces but does NOT quote them. A profile path containing spaces would
# therefore splinter into several argv entries; Chromium reads --user-data-dir
# as ending at the first space and silently creates a profile at the truncated
# path -- so the token lands in a THIRD profile nobody intended. Building one
# pre-quoted string ourselves keeps the path intact. This is factored out so it
# can be unit-tested (see tests/Test-ArgBuilder.ps1).
function Get-ClaudeLaunchArgString {
    param(
        [string]$Target,
        [string]$Url
    )
    if ($Target -eq 'default') {
        # No --user-data-dir => Chromium uses the stock %APPDATA%\Claude profile.
        return "`"$Url`""
    }
    return "--user-data-dir=`"$Target`" `"$Url`""
}

function Invoke-ClaudeShim {
    param([string]$Url)

    if (-not $Url) {
        Add-Content $LogFile "$(Get-Date -Format s)  ERROR: no URL supplied on activation"
        exit 1
    }

    # --- read routing target (default = stock profile, the personal-safe rest state) ---
    $target = 'default'
    if (Test-Path $TargetFile) {
        $t = (Get-Content $TargetFile -First 1).Trim()
        if ($t) { $target = $t }
    }

    # --- resolve Claude.exe from the installed MSIX package -----------------
    # MSIX-only on purpose: there is deliberately NO fallback to an old
    # Squirrel-era claude.exe. Launching a stale exe into a current-era profile
    # is a downgrade-corruption risk, not a graceful fallback -- fail loudly.
    $pkg = Get-AppxPackage -Name '*Claude*' -ErrorAction SilentlyContinue |
        Sort-Object Version -Descending | Select-Object -First 1
    $exe = if ($pkg) { Join-Path $pkg.InstallLocation 'app\Claude.exe' }
    if (-not $exe -or -not (Test-Path $exe)) {
        Add-Content $LogFile "$(Get-Date -Format s)  ERROR: Claude.exe not found (url: $Url)"
        exit 1
    }

    # --- build a single pre-quoted argument string (see Get-ClaudeLaunchArgString) ---
    $argStr = Get-ClaudeLaunchArgString -Target $target -Url $Url

    # route.log is the primary debugging tripwire (see docs/PROTOCOL-ROUTING.md):
    #   * no new line during a login  => the handler chain failed BEFORE the shim
    #                                     (registration/UserChoice problem)
    #   * a line with the wrong target => arming-state problem
    Add-Content $LogFile "$(Get-Date -Format s)  $target <- $Url"
    Start-Process -FilePath $exe -ArgumentList $argStr

    # --- one-shot reset so a later login doesn't silently land in the wrong profile ---
    # The dangerous failure mode is a sticky marker: a personal re-auth landing
    # in the work profile weeks later "succeeds" and is therefore invisible.
    # Resetting to 'default' after every fire makes the safe profile the resting state.
    Set-Content $TargetFile 'default' -Encoding ASCII
}

# Run only when invoked normally. When dot-sourced (InvocationName '.') -- as the
# unit test does -- just define the functions above without executing, so the
# builder can be tested in isolation.
if ($MyInvocation.InvocationName -ne '.') {
    Invoke-ClaudeShim -Url $Url
}
