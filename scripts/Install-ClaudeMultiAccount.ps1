<#
.SYNOPSIS
    Single entry point: takes a machine from "Claude Desktop installed" to two accounts side by side.
.DESCRIPTION
    Runs the installation steps in order, each one idempotent and preview-first. Without -Apply nothing
    is written: every step reports what it would do. With -Apply each step runs its own script with that
    script's own approvals; none of them logs anybody in or out, touches credentials, or uninstalls Claude.

      1. Checks     : Windows, Python 3.12+ (a real runtime), the Claude package, Developer Mode (file
                      symlinks), an unpackaged shell, and Claude closed (with -Apply).
      2. Base       : the preview-first native install (launcher, login router, ownership receipt) from a
                      private specification. If none is given, -WriteSpecTemplate writes one for you to
                      complete. The saved approval capsule is shown and you confirm it by typing INSTALL.
      3. Identity   : account B's own taskbar button and icon (Install-ClaudeIdentity.ps1; needs -IconPath).
      4. Tools      : the "Claude multi-comptes" desktop shortcuts (Install-ClaudeTools.ps1).
      5. Sharing    : links between A's and B's configuration (Link-SharedConfig.py), never credentials.
      6. Verify     : the read-only repair check.

    Run it from a shortcut or a PowerShell opened from the Start menu, never from inside Codex or Claude
    Desktop: their registry and AppData writes are redirected and the tools refuse to run there.
    After it succeeds: pin the "Claude (B)" shortcut, then run "Reconnecter B" to sign B in.
.PARAMETER InstallDir
    Parent folder of the installation (default %USERPROFILE%\ClaudeProfiles).
.PARAMETER Spec
    Private specification file, named *.workspace.local.json, completed by you (see -WriteSpecTemplate).
.PARAMETER WriteSpecTemplate
    Write <InstallDir>\setup\claude.workspace.local.json with the detected paths and placeholders, then stop.
.PARAMETER IconPath
    Your own .ico for account B (no Claude artwork is shipped). Required by the identity step with -Apply.
.PARAMETER BDataDir
    Account B's Desktop data folder (default %APPDATA%\Claude-B).
.PARAMETER BConfigDir
    Account B's Claude Code config folder (default %USERPROFILE%\.claude-b).
.PARAMETER ApproveProtocol
    Separate consent to register the login router namespaces (the spec must also say so).
.PARAMETER Apply
    Perform the installation. Without it everything is a preview.
.PARAMETER Yes
    Do not ask for the typed confirmation of the base approval capsule (for unattended runs you reviewed).
.PARAMETER Pause
    Wait for Enter before closing (used by a desktop shortcut).
.NOTES
    Windows PowerShell 5.1 and PowerShell 7, no admin rights, no dependency installed.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:USERPROFILE 'ClaudeProfiles'),
    [string]$Spec,
    [switch]$WriteSpecTemplate,
    [string]$IconPath,
    [string]$BDataDir = (Join-Path $env:APPDATA 'Claude-B'),
    [string]$BConfigDir = (Join-Path $env:USERPROFILE '.claude-b'),
    [switch]$ApproveProtocol,
    [switch]$Apply,
    [switch]$Yes,
    [switch]$Pause
)

$script:ScriptsDir = Split-Path -Parent $PSCommandPath
$script:StepOrder = @('Checks', 'Base', 'Identity', 'Tools', 'Sharing', 'Verify')

function New-InstallResult {
    param([string]$Step, [ValidateSet('OK', 'WOULD', 'TODO', 'BLOCKED', 'INFO')][string]$State, [string]$Detail, [string]$Hint = '')
    [pscustomobject]@{ Step = $Step; State = $State; Detail = $Detail; Hint = $Hint }
}

function Get-ClaudeSetupPython {
    <# A real Python 3.12+ (not the Microsoft Store alias), or $null. #>
    $ErrorActionPreference = 'Continue'
    foreach ($candidate in @(Get-Command python -All -ErrorAction SilentlyContinue)) {
        if ($candidate.Source -match '\\WindowsApps\\') { continue }
        $ok = & $candidate.Source -c 'import sys; print(sys.version_info >= (3, 12))' 2>$null
        if ($ok -eq 'True') { return $candidate.Source }
    }
    return $null
}

function Test-ClaudeSymlinkCapability {
    <# True when this user can create file symlinks (Windows Developer Mode); probed in a throwaway folder. #>
    $probe = Join-Path ([IO.Path]::GetTempPath()) ('claude-symlink-probe-' + [guid]::NewGuid().ToString('N'))
    $ok = $false
    try {
        [void](New-Item -ItemType Directory -Path $probe)
        Set-Content -LiteralPath (Join-Path $probe 'target.txt') -Value 'x'
        [void](New-Item -ItemType SymbolicLink -Path (Join-Path $probe 'link.txt') -Target (Join-Path $probe 'target.txt') -ErrorAction Stop)
        $ok = $true
    } catch { $ok = $false } finally {
        if (Test-Path -LiteralPath $probe) { Remove-Item -LiteralPath $probe -Recurse -Force -ErrorAction SilentlyContinue }
    }
    return $ok
}

function Get-ClaudeRunningCount {
    $ErrorActionPreference = 'Continue'
    return @(Get-Process -Name 'Claude' -ErrorAction SilentlyContinue).Count
}

function Get-ClaudePackageVersion {
    $ErrorActionPreference = 'Continue'
    $package = @(Get-AppxPackage -Name '*Claude*' -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^Claude' }) | Select-Object -First 1
    if ($package) { return [string]$package.Version }
    return $null
}

function New-ClaudeSpecObject {
    <# The private specification with detected paths and REPLACE_WITH placeholders for what only you can attest. #>
    param([string]$InstallDir, [string]$BDataDir, [string]$BConfigDir, [string]$Version)
    $appData = $env:APPDATA
    $home_ = $env:USERPROFILE
    [ordered]@{
        schema       = 1
        profiles     = [ordered]@{
            A = [ordered]@{ dataDir = (Join-Path $appData 'Claude'); configDir = (Join-Path $home_ '.claude') }
            B = [ordered]@{ dataDir = $BDataDir; configDir = $BConfigDir }
        }
        projects     = @([ordered]@{
            project  = 'REPLACE_WITH_AN_EXISTING_PROJECT_FOLDER'
            memory   = 'REPLACE_WITH_THAT_PROJECTS_MEMORY_FOLDER_UNDER_A_CONFIG\projects'
            evidence = [ordered]@{
                config_provenance        = $false
                memory_provenance        = $false
                trust_confirmed          = $false
                external_policy_reviewed = $false
                version                  = $(if ($Version) { $Version } else { 'REPLACE_WITH_CLAUDE_VERSION' })
                surface                  = 'desktop_user_report'
            }
        })
        install_dir  = $InstallDir
        desktop_dir  = [Environment]::GetFolderPath('Desktop')
        protocol     = [ordered]@{ change = $true; consent = $false; expected_before = $null }
    }
}

function Test-ClaudeSpecReady {
    <# $null when the specification is complete, otherwise the closed reason it cannot be used yet. #>
    param([string]$Path)
    if (-not $Path) { return 'SPEC_NOT_GIVEN' }
    if ($Path -notlike '*.workspace.local.json') { return 'SPEC_NAME_MUST_END_WITH_.workspace.local.json' }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return 'SPEC_FILE_MISSING' }
    $text = Get-Content -LiteralPath $Path -Raw
    if ($text -match 'REPLACE_WITH') { return 'SPEC_HAS_PLACEHOLDERS' }
    try { $parsed = $text | ConvertFrom-Json } catch { return 'SPEC_NOT_JSON' }
    foreach ($project in @($parsed.projects)) {
        foreach ($flag in 'config_provenance', 'memory_provenance', 'trust_confirmed', 'external_policy_reviewed') {
            if ($project.evidence.$flag -ne $true) { return "SPEC_EVIDENCE_NOT_CONFIRMED:$flag" }
        }
    }
    return $null
}

function Invoke-ClaudeSetupTool {
    <# Runs a Python tool, returns its stdout+stderr as text and the exit code in $script:LastToolExit. #>
    param([string]$Python, [string]$Script, [string[]]$Arguments)
    $ErrorActionPreference = 'Continue'   # native stderr must not become a terminating error in PS 5.1
    $text = & $Python -B (Join-Path $script:ScriptsDir $Script) @Arguments 2>&1 | Out-String
    $script:LastToolExit = $LASTEXITCODE
    return $text
}

function Get-ClaudeBaseState {
    <# installed | absent | refused:<code>, from the ownership receipt through the installed validator. #>
    param([string]$Python, [string]$InstallDir)
    if (-not (Test-Path -LiteralPath (Join-Path $InstallDir 'native-ownership.json') -PathType Leaf)) { return 'absent' }
    $ErrorActionPreference = 'Continue'
    $code = "import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path; import NativeWorkspace as n, SharedMemoryPlan as b`n" +
            "try:`n    n.load(Path(sys.argv[2])); print('OK')`nexcept b.BridgeError as e:`n    print(str(e))`nexcept Exception:`n    print('UNREADABLE')"
    $state = ((& $Python -B -c $code $script:ScriptsDir $InstallDir 2>$null | Out-String).Trim())
    if ($state -eq 'OK') { return 'installed' }
    return "refused:$state"
}

function Invoke-ClaudeInstallChecks {
    param([string]$InstallDir, [bool]$ApplyMode)
    $results = New-Object System.Collections.Generic.List[object]
    $python = Get-ClaudeSetupPython
    if (-not $python) { $results.Add((New-InstallResult 'Checks' 'BLOCKED' 'Python 3.12+ not found (the Store alias does not count)' 'Install Python from python.org, then rerun.')) }
    else { $results.Add((New-InstallResult 'Checks' 'OK' "Python: $python")) }
    $version = Get-ClaudePackageVersion
    if (-not $version) { $results.Add((New-InstallResult 'Checks' 'BLOCKED' 'The Claude Desktop package is not installed' 'Install Claude Desktop from the Microsoft Store, sign in to account A, then rerun.')) }
    else { $results.Add((New-InstallResult 'Checks' 'OK' "Claude package $version")) }
    if (Test-ClaudeSymlinkCapability) { $results.Add((New-InstallResult 'Checks' 'OK' 'File symlinks allowed (Developer Mode)')) }
    else { $results.Add((New-InstallResult 'Checks' 'BLOCKED' 'File symlinks are not allowed' 'Turn on Developer Mode: Settings > System > For developers.')) }
    if ($python) {
        $ErrorActionPreference = 'Continue'
        & $python -B -c "import sys; sys.path.insert(0, sys.argv[1]); import NativeWindowsIO as n; n.require_unpackaged_process()" $script:ScriptsDir 2>$null
        if ($LASTEXITCODE -eq 0) { $results.Add((New-InstallResult 'Checks' 'OK' 'Not inside Codex or Claude Desktop')) }
        else { $results.Add((New-InstallResult 'Checks' 'BLOCKED' 'Started from inside a packaged app (Codex or Claude Desktop)' 'Run it from a shortcut or a PowerShell opened from the Start menu.')) }
    }
    $aDir = Join-Path $env:APPDATA 'Claude'
    if (Test-Path -LiteralPath $aDir) { $results.Add((New-InstallResult 'Checks' 'OK' 'Account A data folder found')) }
    else { $results.Add((New-InstallResult 'Checks' 'BLOCKED' 'Account A has never been started (no data folder)' 'Start Claude once and sign in to account A, then rerun.')) }
    $running = Get-ClaudeRunningCount
    if ($running -eq 0) { $results.Add((New-InstallResult 'Checks' 'OK' 'Claude is closed')) }
    elseif ($ApplyMode) { $results.Add((New-InstallResult 'Checks' 'BLOCKED' "$running Claude process(es) running" 'Close every Claude window, then rerun with -Apply.')) }
    else { $results.Add((New-InstallResult 'Checks' 'INFO' "$running Claude process(es) running" 'They must be closed before -Apply.')) }
    return $results
}

function Invoke-ClaudeInstall {
    param([string]$InstallDir, [string]$Spec, [string]$IconPath, [string]$BDataDir, [string]$BConfigDir,
          [bool]$ApproveProtocol, [bool]$ApplyMode, [bool]$AutoYes)
    $out = New-Object System.Collections.Generic.List[object]
    $checks = Invoke-ClaudeInstallChecks -InstallDir $InstallDir -ApplyMode $ApplyMode
    foreach ($c in $checks) { $out.Add($c) }
    if (@($checks | Where-Object { $_.State -eq 'BLOCKED' }).Count) { return $out }
    $python = Get-ClaudeSetupPython

    # 2. Base.
    $base = Get-ClaudeBaseState -Python $python -InstallDir $InstallDir
    if ($base -eq 'installed') { $out.Add((New-InstallResult 'Base' 'OK' 'Base installation present and valid')) }
    elseif ($base -like 'refused:*') {
        $out.Add((New-InstallResult 'Base' 'INFO' ("Receipt needs attention ({0})" -f $base.Substring(8)) 'Run "Reparer Claude (A+B)" (Repair-ClaudeProfiles.ps1 -Fix) with B closed.'))
    } else {
        $problem = Test-ClaudeSpecReady -Path $Spec
        if ($problem) {
            $hint = if ($problem -eq 'SPEC_NOT_GIVEN') { 'Run again with -WriteSpecTemplate, complete the file, then pass it with -Spec.' } else { "Fix the specification and pass it with -Spec ($problem)." }
            $out.Add((New-InstallResult 'Base' 'TODO' "No usable specification: $problem" $hint))
        } elseif (-not $ApplyMode) {
            $out.Add((New-InstallResult 'Base' 'WOULD' 'Would save an approval capsule, ask you to confirm it, then install the launcher and the login router'))
        } else {
            $setup = Join-Path $InstallDir 'setup'
            [void](New-Item -ItemType Directory -Path $setup -Force)
            $capsule = Join-Path $setup ('claude.native.{0}.local.json' -f (Get-Date -Format 'yyyyMMddHHmmss'))
            $text = Invoke-ClaudeSetupTool -Python $python -Script 'SharedWorkspace.py' -Arguments @('native-preview', '--spec', $Spec, '--output', $capsule)
            if ($script:LastToolExit -ne 0) { $out.Add((New-InstallResult 'Base' 'BLOCKED' 'The approval capsule was refused' ($text.Trim()))); return $out }
            Write-Host ''
            Write-Host 'Approval capsule saved. Review it before confirming:' -ForegroundColor White
            Write-Host "  $capsule"
            $confirmed = $AutoYes
            if (-not $confirmed) { $confirmed = ((Read-Host 'Type INSTALL to install the base (anything else stops here)') -ceq 'INSTALL') }
            if (-not $confirmed) { $out.Add((New-InstallResult 'Base' 'TODO' 'Not confirmed; nothing was installed' 'Rerun and type INSTALL after reviewing the capsule.')); return $out }
            $args_ = @('native-install', '--spec', $Spec, '--approval', $capsule, '--approved', '--writers-closed')
            if ($ApproveProtocol) { $args_ += '--approve-protocol' }
            $text = Invoke-ClaudeSetupTool -Python $python -Script 'SharedWorkspace.py' -Arguments $args_
            if ($script:LastToolExit -ne 0) { $out.Add((New-InstallResult 'Base' 'BLOCKED' 'The base installation was refused' ($text.Trim()))); return $out }
            $out.Add((New-InstallResult 'Base' 'OK' 'Base installed'))
        }
    }
    if (@($out | Where-Object { $_.Step -eq 'Base' -and $_.State -in 'TODO', 'BLOCKED' }).Count) { return $out }

    # 3. Identity.
    $identity = Join-Path $script:ScriptsDir 'Install-ClaudeIdentity.ps1'
    if (-not $IconPath) {
        $out.Add((New-InstallResult 'Identity' 'TODO' 'No icon given for account B' 'Pass your own .ico with -IconPath (none is shipped).'))
    } elseif (-not (Test-Path -LiteralPath $IconPath -PathType Leaf)) {
        $out.Add((New-InstallResult 'Identity' 'TODO' 'The icon file does not exist' 'Pass an existing .ico with -IconPath.'))
    } elseif (-not $ApplyMode) {
        $out.Add((New-InstallResult 'Identity' 'WOULD' "Would install B's taskbar identity and 'Claude (B)' shortcut"))
    } else {
        try {
            & $identity -Name 'B' -ProfileDir $BDataDir -ConfigDir $BConfigDir -IconPath $IconPath -InstallDir $InstallDir -Apply | Out-Host
            $out.Add((New-InstallResult 'Identity' 'OK' "B's taskbar identity installed"))
        } catch { $out.Add((New-InstallResult 'Identity' 'BLOCKED' $_.Exception.Message)) }
    }

    # 4. Tools.
    $tools = Join-Path $script:ScriptsDir 'Install-ClaudeTools.ps1'
    if (-not $ApplyMode) { $out.Add((New-InstallResult 'Tools' 'WOULD' "Would create the 'Claude multi-comptes' desktop shortcuts")) }
    else {
        try { & $tools -InstallDir $InstallDir -Apply | Out-Host; $out.Add((New-InstallResult 'Tools' 'OK' 'Desktop shortcuts installed')) }
        catch { $out.Add((New-InstallResult 'Tools' 'BLOCKED' $_.Exception.Message)) }
    }

    # 5. Sharing.
    if (-not $ApplyMode) { $out.Add((New-InstallResult 'Sharing' 'WOULD' "Would link B's configuration to A's (never credentials)")) }
    else {
        $text = Invoke-ClaudeSetupTool -Python $python -Script 'Link-SharedConfig.py' -Arguments @('--install-dir', $InstallDir, '--apply', '--approved', '--replace-files')
        if ($script:LastToolExit -eq 0) { $out.Add((New-InstallResult 'Sharing' 'OK' 'Shared configuration linked')) }
        else { $out.Add((New-InstallResult 'Sharing' 'BLOCKED' 'Linking was refused' ($text.Trim()))) }
    }

    # 6. Verify (read-only).
    if ($ApplyMode) {
        $repair = Join-Path $script:ScriptsDir 'Repair-ClaudeProfiles.ps1'
        Write-Host ''
        & $repair -InstallDir $InstallDir | Out-Host
        $out.Add((New-InstallResult 'Verify' 'INFO' 'Read-only check printed above' 'Pin "Claude (B)", then run "Reconnecter B" to sign account B in.'))
    } else {
        $out.Add((New-InstallResult 'Verify' 'WOULD' 'Would run the read-only repair check'))
    }
    return $out
}

function Show-ClaudeInstallResults {
    param($Results)
    $labels = @{ OK = '  OK  '; WOULD = ' PLAN '; TODO = ' TODO '; BLOCKED = 'BLOCK '; INFO = ' info ' }
    $colors = @{ OK = 'Green'; WOULD = 'Cyan'; TODO = 'Yellow'; BLOCKED = 'Red'; INFO = 'Gray' }
    foreach ($r in $Results) {
        Write-Host ('[{0}] {1,-9} {2}' -f $labels[$r.State], $r.Step, $r.Detail) -ForegroundColor $colors[$r.State]
        if ($r.Hint -and $r.State -in 'TODO', 'BLOCKED', 'INFO') { Write-Host ('           -> ' + $r.Hint) -ForegroundColor DarkGray }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    $exit = 0
    try {
        Write-Host ''
        Write-Host ($(if ($Apply) { 'Claude multi-account: installation' } else { 'Claude multi-account: preview (nothing is written; add -Apply to install)' })) -ForegroundColor White
        if ($WriteSpecTemplate) {
            $dir = Join-Path $InstallDir 'setup'
            $path = Join-Path $dir 'claude.workspace.local.json'
            if (Test-Path -LiteralPath $path) { throw "SPEC_TEMPLATE_EXISTS: $path already exists; it is never overwritten." }
            [void](New-Item -ItemType Directory -Path $dir -Force)
            $template = New-ClaudeSpecObject -InstallDir $InstallDir -BDataDir $BDataDir -BConfigDir $BConfigDir -Version (Get-ClaudePackageVersion)
            ($template | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $path -Encoding UTF8
            Write-Host "Specification template written: $path" -ForegroundColor Green
            Write-Host 'Complete every REPLACE_WITH value. The four evidence flags are your own confirmations:'
            Write-Host '  set each to true only once you have checked it. Set protocol.consent to true to allow the login router.'
            Write-Host 'Then run again with -Spec <that file>.'
        } else {
            $results = Invoke-ClaudeInstall -InstallDir $InstallDir -Spec $Spec -IconPath $IconPath -BDataDir $BDataDir -BConfigDir $BConfigDir `
                -ApproveProtocol ([bool]$ApproveProtocol) -ApplyMode ([bool]$Apply) -AutoYes ([bool]$Yes)
            Write-Host ''
            Show-ClaudeInstallResults -Results $results
            $open = @($results | Where-Object { $_.State -in 'TODO', 'BLOCKED' }).Count
            Write-Host ''
            if ($open) { Write-Host "$open step(s) need your attention." -ForegroundColor Yellow; $exit = 1 }
            elseif ($Apply) { Write-Host 'Installed.' -ForegroundColor Green }
            else { Write-Host 'Preview complete. Rerun with -Apply to install.' -ForegroundColor Green }
        }
    } catch {
        Write-Host ('Error: ' + $_.Exception.Message) -ForegroundColor Red
        $exit = 1
    }
    if ($Pause) { Write-Host ''; [void](Read-Host 'Press Enter to close') }
    exit $exit
}
