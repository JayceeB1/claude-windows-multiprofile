<#
.SYNOPSIS
    Tests the repair, reconnect and tools-installer scripts on synthetic data.
.DESCRIPTION
    Pure functions with fixtures plus the tools installer in an owned TEMP folder. No Claude
    process, no login, no registry write, no real shortcut folder. Windows PowerShell 5.1 or 7.
.EXAMPLE
    .\tests\Test-ClaudeRepair.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'These tests require Windows.' }
$scripts = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts'
$script:assertions = 0
function Assert-Equal {
    param([string]$Name, $Expected, $Actual)
    if ($Expected -cne $Actual) { throw "$Name -- expected <$Expected>, got <$Actual>" }
    $script:assertions++
}
function Assert-Failure {
    param([string]$Name, [scriptblock]$Action, [string]$Pattern)
    $caught = $null
    try { & $Action | Out-Null } catch { $caught = $_ }
    if (-not $caught -or $caught.Exception.Message -notmatch $Pattern) { throw "$Name did not fail for the expected reason ($Pattern)." }
    $script:assertions++
}

foreach ($name in 'Repair-ClaudeProfiles.ps1', 'Connect-ClaudeProfile.ps1', 'Install-ClaudeTools.ps1') {
    $tokens = $null; $errors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $scripts $name), [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
}
. (Join-Path $scripts 'Connect-ClaudeProfile.ps1')   # also loads Repair-ClaudeProfiles.ps1; functions only

$root = Join-Path ([IO.Path]::GetTempPath()) ('claude-repair-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
$null = New-Item -ItemType Directory -Path $root
try {
    # --- Stored-login detection: presence only, tolerant of damage.
    $dataDir = Join-Path $root 'data'; $null = New-Item -ItemType Directory -Path $dataDir
    $long = 'x' * 120
    Assert-Equal 'no config.json -> no session' $false (Test-ClaudeSessionPresent -DataDir $dataDir)
    Set-Content -LiteralPath (Join-Path $dataDir 'config.json') -Value ('{"oauth:tokenCacheV2":"' + $long + '"}')
    Assert-Equal 'stored token -> session' $true (Test-ClaudeSessionPresent -DataDir $dataDir)
    Set-Content -LiteralPath (Join-Path $dataDir 'config.json') -Value '{"oauth:tokenCacheV2":"short"}'
    Assert-Equal 'tiny token entry -> no session' $false (Test-ClaudeSessionPresent -DataDir $dataDir)
    Set-Content -LiteralPath (Join-Path $dataDir 'config.json') -Value '{"darkMode":"auto"}'
    Assert-Equal 'no token key -> no session' $false (Test-ClaudeSessionPresent -DataDir $dataDir)
    Set-Content -LiteralPath (Join-Path $dataDir 'config.json') -Value '{ not json'
    Assert-Equal 'damaged config -> no session, no crash' $false (Test-ClaudeSessionPresent -DataDir $dataDir)

    # --- Fingerprint changes with the login, never contains it.
    Set-Content -LiteralPath (Join-Path $dataDir 'config.json') -Value ('{"oauth:tokenCacheV2":"SECRET_ONE_' + $long + '"}')
    $one = Get-ClaudeLoginFingerprint -DataDir $dataDir
    Set-Content -LiteralPath (Join-Path $dataDir 'config.json') -Value ('{"oauth:tokenCacheV2":"SECRET_TWO_' + $long + '"}')
    $two = Get-ClaudeLoginFingerprint -DataDir $dataDir
    Assert-Equal 'fingerprint differs when the login changes' $true ($one -ne $two -and $one -ne '' -and $two -ne '')
    Assert-Equal 'fingerprint leaks no token text' $false ($one -match 'SECRET')
    Assert-Equal 'fingerprint is stable' $two (Get-ClaudeLoginFingerprint -DataDir $dataDir)
    Assert-Equal 'missing file fingerprint is empty' '' (Get-ClaudeLoginFingerprint -DataDir (Join-Path $root 'nowhere'))

    # --- Who owns claude:// links.
    Assert-Equal 'router progid' 'router' (Get-ClaudeLinkHandlerState -ProgId 'ClaudeShim.claude' -AppUserModelIdOfProgId $null)
    Assert-Equal 'official packaged app' 'official' (Get-ClaudeLinkHandlerState -ProgId 'AppXabc' -AppUserModelIdOfProgId 'Claude_pzs8sxrjxfjjc!Claude')
    Assert-Equal 'another app' 'other' (Get-ClaudeLinkHandlerState -ProgId 'Brave' -AppUserModelIdOfProgId $null)
    Assert-Equal 'no choice recorded' 'none' (Get-ClaudeLinkHandlerState -ProgId '' -AppUserModelIdOfProgId $null)

    # --- Link tool summaries (the JSON the Python tool prints).
    $refused = ConvertFrom-ClaudeLinkPreview -Json '{"status":"REFUSED","reason":"PACKAGED_PROCESS_REFUSED"}'
    Assert-Equal 'refusal is carried' 'PACKAGED_PROCESS_REFUSED' $refused.Reason
    Assert-Equal 'refusal is not ok' $false $refused.Ok
    $steady = ConvertFrom-ClaudeLinkPreview -Json '{"status":"PREVIEW","plan":[{"name":"agents","action":"already"},{"name":"skills","action":"already"},{"name":"keybindings.json","action":"skip"}],"mcp_servers":{"action":"already","servers":["a"]}}'
    Assert-Equal 'steady state has nothing pending' 0 $steady.Pending
    Assert-Equal 'steady state counts links in place' 2 $steady.Already
    $needs = ConvertFrom-ClaudeLinkPreview -Json '{"status":"PREVIEW","plan":[{"name":"agents","action":"link"},{"name":"CLAUDE.md","action":"refuse:TARGET_FILE_EXISTS_USE_REPLACE_FILES"}],"mcp_servers":{"action":"copy","servers":["a"]}}'
    Assert-Equal 'pending counts links and the MCP copy' 2 $needs.Pending
    Assert-Equal 'refusals are listed with their code' 'CLAUDE.md:TARGET_FILE_EXISTS_USE_REPLACE_FILES' $needs.Refused[0]
    $mcpRefused = ConvertFrom-ClaudeLinkPreview -Json '{"status":"PREVIEW","plan":[],"mcp_servers":{"action":"refuse:TARGET_MCP_SERVERS_DIFFER_USE_REPLACE_MCP","servers":["a"]}}'
    Assert-Equal 'MCP refusal is surfaced' 1 @($mcpRefused.Refused).Count
    $applied = ConvertFrom-ClaudeLinkApply -Json '{"status":"APPLIED","linked":9,"problems":[],"mcp_copied":true}'
    Assert-Equal 'apply ok' $true $applied.Ok
    Assert-Equal 'apply linked count' 9 $applied.Linked
    Assert-Equal 'apply with problems is not ok' $false (ConvertFrom-ClaudeLinkApply -Json '{"status":"APPLIED","linked":9,"problems":["x"]}').Ok
    Assert-Equal 'apply refusal reason' 'TARGET_PROFILE_RUNNING_CLOSE_IT_FIRST' (ConvertFrom-ClaudeLinkApply -Json '{"status":"REFUSED","reason":"TARGET_PROFILE_RUNNING_CLOSE_IT_FIRST"}').Reason

    # --- Intent status and the wait helper.
    $install = Join-Path $root 'ClaudeProfiles'; $null = New-Item -ItemType Directory -Path (Join-Path $install 'bin') -Force
    Assert-Equal 'no intent file' 'none' (Get-ClaudeRouteIntentStatus -InstallDir $install)
    Set-Content -LiteralPath (Join-Path $install 'bin\target.txt') -Value '{"version":2,"status":"armed"}'
    Assert-Equal 'armed intent' 'armed' (Get-ClaudeRouteIntentStatus -InstallDir $install)
    Set-Content -LiteralPath (Join-Path $install 'bin\target.txt') -Value 'garbage'
    Assert-Equal 'damaged intent is unknown' 'unknown' (Get-ClaudeRouteIntentStatus -InstallDir $install)
    Assert-Equal 'wait returns true at once' $true (Wait-ClaudeCondition -Condition { $true } -TimeoutSeconds 5 -PollSeconds 1)
    $started = Get-Date
    Assert-Equal 'wait times out' $false (Wait-ClaudeCondition -Condition { $false } -TimeoutSeconds 1 -PollSeconds 1)
    Assert-Equal 'wait honours its timeout' $true (((Get-Date) - $started).TotalSeconds -lt 4)

    # --- Whole repair orchestration on a fixture install, with the OS/Python edges replaced by doubles.
    $fx = Join-Path $root 'fx'; $fxBin = Join-Path $fx 'bin'; $null = New-Item -ItemType Directory -Path $fxBin -Force
    $aData = Join-Path $root 'fxA'; $bData = Join-Path $root 'fxB'
    foreach ($d in $aData, $bData) {
        $null = New-Item -ItemType Directory -Path $d
        Set-Content -LiteralPath (Join-Path $d 'config.json') -Value ('{"oauth:tokenCacheV2":"' + $long + '"}')
    }
    Set-Content -LiteralPath (Join-Path $fxBin 'profiles.json') -Value (@{ profiles = @{ A = @{ dataDir = $aData }; B = @{ dataDir = $bData } } } | ConvertTo-Json -Depth 4)
    $ico = Join-Path $root 'fx.ico'
    Add-Type -AssemblyName System.Drawing
    $bmp = New-Object System.Drawing.Bitmap 64, 64; $ms = New-Object IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png); $png = $ms.ToArray(); $bmp.Dispose()
    $ib = New-Object System.Collections.Generic.List[byte]; $ib.AddRange([byte[]](0, 0, 1, 0, 1, 0, 64, 64, 0, 0, 1, 0, 32, 0))
    $ib.AddRange([BitConverter]::GetBytes([uint32]$png.Length)); $ib.AddRange([BitConverter]::GetBytes([uint32]22)); $ib.AddRange($png)
    [IO.File]::WriteAllBytes($ico, $ib.ToArray())
    $fxDesktop = Join-Path $root 'fxDesktop'
    & (Join-Path $scripts 'Install-ClaudeIdentity.ps1') -Name B -ProfileDir $bData -ConfigDir (Join-Path $root 'fxcfg') -IconPath $ico -InstallDir $fx -ShortcutFolder $fxDesktop -Apply | Out-Null

    $repo = Split-Path -Parent $scripts
    $steadyLinks = '{"status":"PREVIEW","plan":[{"name":"agents","action":"already"}],"mcp_servers":{"action":"already","servers":["a"]}}'
    $pendingLinks = '{"status":"PREVIEW","plan":[{"name":"agents","action":"link"}],"mcp_servers":{"action":"skip","servers":[]}}'
    $routerOk = '{"real_registry_matches_desired":true,"real_registry_empty":false,"receipt_matches_desired":true}'
    $script:python = @{ link = $steadyLinks; router = $routerOk; calls = @() }
    function Test-ClaudeUnpackagedContext { param($Python) return $true }
    function Get-ClaudePython { return 'python.exe' }
    function Get-AppxPackage { param($Name) [pscustomobject]@{ Version = [version]'9.9.1.0' } }
    function Read-ClaudeLinkHandler { return 'official' }
    function Invoke-ClaudePython {
        param([string]$Python, [string]$Script, [string[]]$Arguments)
        $script:python.calls += ($Script + ' ' + ($Arguments -join ' '))
        if ($Script -eq 'Apply-RouterRegistration.py') { return $script:python.router }
        if ($Arguments -contains '--apply') { return '{"status":"APPLIED","linked":9,"problems":[]}' }
        return $script:python.link
    }
    function Pick { param($Checks, [string]$Name) ($Checks | Where-Object { $_.Name -eq $Name }).State }

    $checks = Invoke-ClaudeRepair -InstallDir $fx -RepoDir $repo
    Assert-Equal 'healthy fixture has nothing to do' 0 @($checks | Where-Object { $_.State -in 'TODO', 'BLOCKED' }).Count
    Assert-Equal 'healthy run records the version' '9.9.1.0' (Get-Content -LiteralPath (Join-Path $fx 'repair-state.json') -Raw | ConvertFrom-Json).packageVersion
    Assert-Equal 'read-only run never applies anything' 0 @($script:python.calls | Where-Object { $_ -match '--apply' }).Count
    Assert-Equal 'identity is reported in place' 'OK' (Pick $checks 'Icône et bouton de B')

    function Get-AppxPackage { param($Name) [pscustomobject]@{ Version = [version]'9.9.2.0' } }
    $checks = Invoke-ClaudeRepair -InstallDir $fx -RepoDir $repo
    Assert-Equal 'an update is detected from the recorded version' $true (($checks | Where-Object { $_.Name -eq 'Application Claude' }).Detail -match '9\.9\.1\.0 -> 9\.9\.2\.0')

    $script:python.link = $pendingLinks; $script:python.calls = @()
    $checks = Invoke-ClaudeRepair -InstallDir $fx -RepoDir $repo
    Assert-Equal 'pending links without -Fix are only reported' 'TODO' (Pick $checks 'Partage de la config')
    Assert-Equal 'report-only run applies nothing' 0 @($script:python.calls | Where-Object { $_ -match '--apply' }).Count
    $checks = Invoke-ClaudeRepair -InstallDir $fx -RepoDir $repo -Fix
    Assert-Equal '-Fix applies the pending links' 'FIXED' (Pick $checks 'Partage de la config')
    Assert-Equal 'links are applied with the file-backup flag' 1 @($script:python.calls | Where-Object { $_ -match '--apply --approved --replace-files' }).Count

    # B running blocks the link repair (the Python tool would refuse anyway).
    function Get-ClaudeProfileProcessId { param($DataDir) if ($DataDir -eq $bData) { return [uint32]4242 } return $null }
    $script:python.calls = @()
    $checks = Invoke-ClaudeRepair -InstallDir $fx -RepoDir $repo -Fix
    Assert-Equal 'running B blocks the link repair' 'BLOCKED' (Pick $checks 'Partage de la config')
    Assert-Equal 'nothing was applied while B runs' 0 @($script:python.calls | Where-Object { $_ -match '--apply' }).Count

    # Router missing from the real registry: re-registered with -Fix only when the receipt agrees and the registry is empty.
    function Get-ClaudeProfileProcessId { param($DataDir) return $null }
    $script:python.link = $steadyLinks
    $script:python.router = '{"real_registry_matches_desired":false,"real_registry_empty":true,"receipt_matches_desired":true}'
    $script:python.calls = @()
    $checks = Invoke-ClaudeRepair -InstallDir $fx -RepoDir $repo
    Assert-Equal 'missing router is reported' 'TODO' (Pick $checks 'Routeur de connexion')
    $script:python.router = '{"real_registry_matches_desired":false,"real_registry_empty":false,"receipt_matches_desired":true}'
    $checks = Invoke-ClaudeRepair -InstallDir $fx -RepoDir $repo -Fix
    Assert-Equal 'a foreign registry state is never overwritten' 'TODO' (Pick $checks 'Routeur de connexion')
    Assert-Equal 'no registry apply on a foreign state' 0 @($script:python.calls | Where-Object { $_ -match 'Apply-RouterRegistration.py .*--apply' }).Count

    # Missing login and a broken identity shortcut are detected; -Fix reinstalls the shortcut.
    Remove-Item -LiteralPath (Join-Path $bData 'config.json') -Force
    Remove-Item -LiteralPath (Join-Path $fxDesktop 'Claude (B).lnk') -Force
    $script:python.router = $routerOk
    $checks = Invoke-ClaudeRepair -InstallDir $fx -RepoDir $repo
    Assert-Equal 'missing B login is reported' 'TODO' (Pick $checks 'Connexion B')
    Assert-Equal 'broken shortcut is reported' 'TODO' (Pick $checks 'Icône et bouton de B')
    $checks = Invoke-ClaudeRepair -InstallDir $fx -RepoDir $repo -Fix
    Assert-Equal 'shortcut is reinstalled by -Fix' 'FIXED' (Pick $checks 'Icône et bouton de B')
    Assert-Equal 'reinstalled shortcut carries the app id' 'ClaudeMultiprofile.B' ([ClaudeIdentityNative]::ShortcutAppId((Join-Path $fxDesktop 'Claude (B).lnk')))

    # A packaged context stops everything before any helper runs.
    function Test-ClaudeUnpackagedContext { param($Python) return $false }
    $script:python.calls = @()
    $checks = Invoke-ClaudeRepair -InstallDir $fx -RepoDir $repo -Fix
    Assert-Equal 'packaged context blocks everything' 'BLOCKED' $checks[-1].State
    Assert-Equal 'nothing was run in a packaged context' 0 @($script:python.calls).Count

    # --- Tools installer: preview writes nothing, apply makes three owned shortcuts, remove is exact.
    $folder = Join-Path $root 'Desktop\Claude multi-comptes'
    $repo = Split-Path -Parent $scripts
    $toolArgs = @{ RepoDir = $repo; InstallDir = $install; ShortcutFolder = $folder }
    & (Join-Path $scripts 'Install-ClaudeTools.ps1') @toolArgs | Out-Null
    Assert-Equal 'preview creates nothing' $false (Test-Path -LiteralPath $folder)
    & (Join-Path $scripts 'Install-ClaudeTools.ps1') @toolArgs -Apply | Out-Null
    $wsh = New-Object -ComObject WScript.Shell
    $repair = $wsh.CreateShortcut((Join-Path $folder 'Réparer Claude (A+B).lnk'))
    Assert-Equal 'repair shortcut runs the repo script with -Fix' $true ($repair.Arguments.Contains('Repair-ClaudeProfiles.ps1') -and $repair.Arguments.Contains('-Fix') -and $repair.Arguments.Contains('-Pause'))
    $reconnect = $wsh.CreateShortcut((Join-Path $folder 'Reconnecter B.lnk'))
    Assert-Equal 'reconnect shortcut targets profile B' $true ($reconnect.Arguments.Contains('Connect-ClaudeProfile.ps1') -and $reconnect.Arguments.Contains('-Profile B'))
    $manual = $wsh.CreateShortcut((Join-Path $folder 'Mode opératoire.lnk'))
    Assert-Equal 'manual shortcut opens the French manual' 'MODE-OPERATOIRE.md' (Split-Path -Leaf $manual.TargetPath)
    & (Join-Path $scripts 'Install-ClaudeTools.ps1') @toolArgs -Apply | Out-Null   # idempotent
    Assert-Equal 'rerun keeps three shortcuts' 3 @(Get-ChildItem -LiteralPath $folder -Filter *.lnk).Count
    $foreign = $wsh.CreateShortcut((Join-Path $folder 'Reconnecter B.lnk')); $foreign.TargetPath = (Join-Path $env:SystemRoot 'System32\notepad.exe'); $foreign.Description = 'mine'; $foreign.Save()
    Assert-Failure 'foreign shortcut is refused' { & (Join-Path $scripts 'Install-ClaudeTools.ps1') @toolArgs -Apply } 'not owned by this tool'
    Assert-Equal 'foreign shortcut untouched' 'mine' $wsh.CreateShortcut((Join-Path $folder 'Reconnecter B.lnk')).Description
    Remove-Item -LiteralPath (Join-Path $folder 'Reconnecter B.lnk') -Force
    & (Join-Path $scripts 'Install-ClaudeTools.ps1') @toolArgs -Apply | Out-Null
    & (Join-Path $scripts 'Install-ClaudeTools.ps1') @toolArgs -Remove | Out-Null
    Assert-Equal 'remove preview keeps files' 3 @(Get-ChildItem -LiteralPath $folder -Filter *.lnk).Count
    & (Join-Path $scripts 'Install-ClaudeTools.ps1') @toolArgs -Remove -Apply | Out-Null
    Assert-Equal 'remove deletes the folder' $false (Test-Path -LiteralPath $folder)
    Write-Host "PASS: $script:assertions repair/reconnect assertions; no Claude process, login, registry or real shortcut folder touched."
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
