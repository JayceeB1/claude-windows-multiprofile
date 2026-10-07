<#
.SYNOPSIS
    Checks the two-account setup and, with -Fix, restores it after a Claude update or a mishap.
.DESCRIPTION
    Read-only by default: prints one line per check (OK / A FAIRE / INFO) and a summary.
    With -Fix it repairs only what this fork owns, in this order, each step idempotent:
      1. the taskbar identity launcher and its shortcut (Install-ClaudeIdentity.ps1),
      2. the router registration in the real registry (Apply-RouterRegistration.py),
      3. the shared config links (Link-SharedConfig.py, B must be closed; differing files are
         backed up before being replaced).
    It never touches logins, profile data, project memory contents, the official package or
    the default-app choice, and it never signs anybody out. A Claude update is detected by
    the package version recorded in <InstallDir>\repair-state.json. If an account asks to log
    in again, use Connect-ClaudeProfile.ps1.
.PARAMETER InstallDir
    Parent folder of the installation (default %USERPROFILE%\ClaudeProfiles).
.PARAMETER RepoDir
    Folder of this repository (default: the parent of this script's folder).
.PARAMETER Fix
    Repair what the checks flag instead of only reporting it.
.PARAMETER Pause
    Wait for Enter before closing (used by the desktop shortcut).
.NOTES
    Windows PowerShell 5.1 and PowerShell 7, no admin rights. Run it from a shortcut or a
    PowerShell opened from the Start menu: the Python helpers refuse to run from inside
    Codex or Claude Desktop, whose registry and AppData writes are redirected.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:USERPROFILE 'ClaudeProfiles'),
    [string]$RepoDir,
    [switch]$Fix,
    [switch]$Pause
)

$script:ScriptsDir = Split-Path -Parent $PSCommandPath
if (-not $RepoDir) { $RepoDir = Split-Path -Parent $script:ScriptsDir }
. (Join-Path $script:ScriptsDir 'Set-ClaudeWindowIdentity.ps1')

function New-Check {
    param([string]$Name, [ValidateSet('OK', 'TODO', 'INFO', 'FIXED', 'BLOCKED')][string]$State, [string]$Detail, [string]$Hint = '')
    [pscustomobject]@{ Name = $Name; State = $State; Detail = $Detail; Hint = $Hint }
}

function Test-ClaudeSessionPresent {
    <# True when the Desktop data dir holds a stored login. Presence only: no token is read or printed. #>
    param([string]$DataDir)
    $file = Join-Path $DataDir 'config.json'
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { return $false }
    try { $json = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json } catch { return $false }
    $entry = $json.PSObject.Properties['oauth:tokenCacheV2']
    return [bool]($entry -and ([string]$entry.Value).Length -gt 40)
}

function Get-ClaudeLinkHandlerState {
    <# Which app currently owns claude:// links, from the UserChoice ProgId. Returns official|router|other|none. #>
    param([string]$ProgId, [string]$AppUserModelIdOfProgId)
    if ([string]::IsNullOrEmpty($ProgId)) { return 'none' }
    if ($ProgId -ceq 'ClaudeShim.claude') { return 'router' }
    if ($AppUserModelIdOfProgId -like 'Claude_*') { return 'official' }
    return 'other'
}

function Read-ClaudeLinkHandler {
    $key = 'HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\claude\UserChoice'
    $progId = $null
    if (Test-Path -LiteralPath $key) { $progId = (Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue).ProgId }
    $aumid = $null
    if ($progId) {
        $app = "HKCU:\Software\Classes\$progId\Application"
        if (Test-Path -LiteralPath $app) { $aumid = (Get-ItemProperty -LiteralPath $app -ErrorAction SilentlyContinue).AppUserModelID }
    }
    return Get-ClaudeLinkHandlerState -ProgId $progId -AppUserModelIdOfProgId $aumid
}

function Get-ClaudeJsonField {
    <# Optional JSON field: $null when absent (safe under Set-StrictMode). #>
    param($Object, [string]$Name)
    $property = $Object.PSObject.Properties[$Name]
    if ($property) { return $property.Value }
    return $null
}

function ConvertFrom-ClaudeLinkPreview {
    <# Summarises the JSON printed by Link-SharedConfig.py (preview or apply). #>
    param([string]$Json)
    $o = $Json | ConvertFrom-Json
    if ($o.status -eq 'REFUSED' -or $o.status -eq 'FAILED') {
        return [pscustomobject]@{ Ok = $false; Reason = [string]((Get-ClaudeJsonField $o 'reason') + (Get-ClaudeJsonField $o 'error')); Pending = 0; Already = 0; Refused = @(); Problems = @() }
    }
    $plan = @($o.plan)
    $mcp = if ($o.PSObject.Properties['mcp_servers']) { [string]$o.mcp_servers.action } else { 'skip' }
    $refused = @($plan | Where-Object { $_.action -like 'refuse:*' } | ForEach-Object { '{0}:{1}' -f $_.name, ($_.action -replace '^refuse:', '') })
    if ($mcp -like 'refuse:*') { $refused += ('serveurs MCP:' + ($mcp -replace '^refuse:', '')) }
    return [pscustomobject]@{
        Ok = $true; Reason = ''
        Pending = @($plan | Where-Object { $_.action -eq 'link' }).Count + $(if ($mcp -eq 'copy') { 1 } else { 0 })
        Already = @($plan | Where-Object { $_.action -eq 'already' }).Count
        Refused = $refused
        Problems = @()
    }
}

function ConvertFrom-ClaudeToolJson {
    <# The Python helpers print one JSON document; anything else (a crash, a warning) becomes $null. #>
    param([string]$Text)
    $start = $Text.IndexOf('{')
    if ($start -lt 0) { return $null }
    try { return $Text.Substring($start) | ConvertFrom-Json } catch { return $null }
}

function Get-ClaudeScheduledTaskCount {
    <# Number of scheduled Code tasks in a scheduled-tasks.json (0 when absent or unreadable). #>
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return 0 }
    try { $json = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json } catch { return 0 }
    $property = $json.PSObject.Properties['scheduledTasks']
    if (-not $property -or $null -eq $property.Value) { return 0 }
    return @($property.Value).Count
}

function Get-ClaudeReceiptState {
    <# OK, or the closed reason code the base installation's ownership receipt is refused with. #>
    param([string]$Python, [string]$InstallDir)
    $ErrorActionPreference = 'Continue'
    $code = "import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path; import NativeWorkspace as n, SharedMemoryPlan as b`n" +
            "try:`n    n.load(Path(sys.argv[2])); print('OK')`nexcept b.BridgeError as e:`n    print(str(e))`nexcept Exception as e:`n    print('UNREADABLE')"
    $out = & $Python -B -c $code $script:ScriptsDir $InstallDir 2>$null | Out-String
    $state = $out.Trim()
    if ($state -match '^[A-Z_]+$') { return $state }
    return 'UNREADABLE'
}

function Get-ClaudePython {
    $ErrorActionPreference = 'Continue'
    foreach ($candidate in @(Get-Command python -All -ErrorAction SilentlyContinue)) {
        if ($candidate.Source -match '\\WindowsApps\\') { continue }   # Store alias, not a runtime
        $ok = & $candidate.Source -c 'import sys; print(sys.version_info >= (3, 12))' 2>$null
        if ($ok -eq 'True') { return $candidate.Source }
    }
    return $null
}

function Test-ClaudeUnpackagedContext {
    param([string]$Python)
    $ErrorActionPreference = 'Continue'
    & $Python -B -c "import sys; sys.path.insert(0, sys.argv[1]); import NativeWindowsIO as n; n.require_unpackaged_process()" $script:ScriptsDir 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Invoke-ClaudePython {
    param([string]$Python, [string]$Script, [string[]]$Arguments)
    $ErrorActionPreference = 'Continue'   # native stderr must not become a terminating error in PS 5.1
    $text = & $Python -B (Join-Path $script:ScriptsDir $Script) @Arguments 2>&1 | Out-String
    return $text
}

function Get-ClaudeRepairState {
    param([string]$InstallDir)
    $path = Join-Path $InstallDir 'repair-state.json'
    if (Test-Path -LiteralPath $path) { try { return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json } catch { } }
    return $null
}

function Invoke-ClaudeRepair {
    param([string]$InstallDir, [string]$RepoDir, [switch]$Fix)
    $ErrorActionPreference = 'Continue'   # python/reg refusals go to stderr; results come from exit codes and JSON
    $checks = New-Object System.Collections.Generic.List[object]
    $py = Get-ClaudePython
    if (-not $py) { $checks.Add((New-Check 'Python 3.12+' 'TODO' 'introuvable' 'Installe Python 3.12 ou plus (python.org), pas l''alias du Store.')); return $checks }

    # 0. The helpers (and registry/AppData writes) are only valid outside a packaged process tree.
    if (-not (Test-ClaudeUnpackagedContext -Python $py)) {
        $checks.Add((New-Check 'Contexte' 'BLOCKED' 'lancé depuis Codex ou Claude Desktop' 'Relance depuis le raccourci du bureau ou un PowerShell ouvert depuis le menu Démarrer.'))
        return $checks
    }
    $checks.Add((New-Check 'Contexte' 'OK' 'hors des applications empaquetées'))

    # 1. Package version and update detection.
    $pkg = Get-AppxPackage -Name '*Claude*' -ErrorAction SilentlyContinue | Sort-Object Version -Descending | Select-Object -First 1
    $state = Get-ClaudeRepairState -InstallDir $InstallDir
    if (-not $pkg) { $checks.Add((New-Check 'Application Claude' 'TODO' 'non installée' 'Installe Claude Desktop (claude.ai/download).')); return $checks }
    $version = [string]$pkg.Version
    if ($state -and $state.packageVersion -and $state.packageVersion -ne $version) {
        $checks.Add((New-Check 'Application Claude' 'INFO' "mise à jour détectée : $($state.packageVersion) -> $version" 'Les fenêtres déjà ouvertes gardent l''ancienne version : ferme-les puis relance-les.'))
    } else {
        $checks.Add((New-Check 'Application Claude' 'OK' "version $version"))
    }

    # 2. Profiles and stored logins.
    $manifestPath = Join-Path $InstallDir 'bin\profiles.json'
    if (-not (Test-Path -LiteralPath $manifestPath)) { $checks.Add((New-Check 'Profils' 'TODO' 'profiles.json introuvable' 'L''installation de base est absente ou a été déplacée.')); return $checks }
    $profiles = (Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json).profiles
    foreach ($name in 'A', 'B') {
        $entry = $profiles.PSObject.Properties[$name]
        if (-not $entry) { $checks.Add((New-Check "Profil $name" 'TODO' 'absent de profiles.json')); continue }
        $dir = $entry.Value.dataDir
        if (-not (Test-Path -LiteralPath $dir)) { $checks.Add((New-Check "Profil $name" 'TODO' 'dossier de données introuvable' 'Lance le profil une fois et connecte-toi.')); continue }
        if (Test-ClaudeSessionPresent -DataDir $dir) {
            $checks.Add((New-Check "Connexion $name" 'OK' 'session enregistrée'))
        } else {
            $checks.Add((New-Check "Connexion $name" 'TODO' 'aucune session enregistrée' $(if ($name -eq 'B') { 'Utilise « Reconnecter B ».' } else { 'Ouvre A avec Claude par défaut pour les liens claude:// et connecte-toi.' })))
        }
    }
    $bData = $profiles.PSObject.Properties['B'].Value.dataDir
    $bRunning = [bool](Get-ClaudeProfileProcessId -DataDir $bData)
    $checks.Add((New-Check 'Fenêtre B' 'INFO' $(if ($bRunning) { 'ouverte' } else { 'fermée' })))

    # 3. Taskbar identity launcher.
    $identityDir = Join-Path $InstallDir 'identity'
    $identityJson = Join-Path $identityDir 'identity.json'
    $identityOk = $false
    if (Test-Path -LiteralPath $identityJson) {
        $m = Get-Content -LiteralPath $identityJson -Raw | ConvertFrom-Json
        $broken = @()
        foreach ($f in $m.files.PSObject.Properties) {
            $p = Join-Path $identityDir $f.Name
            if (-not (Test-Path -LiteralPath $p) -or (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash -ne $f.Value) { $broken += $f.Name }
        }
        $lnk = $m.shortcut
        if (-not (Test-Path -LiteralPath $lnk)) { $broken += 'raccourci' }
        elseif ([ClaudeIdentityNative]::ShortcutAppId($lnk) -cne $m.appId) { $broken += 'identité du raccourci' }
        if ($broken.Count -eq 0) { $identityOk = $true; $checks.Add((New-Check 'Icône et bouton de B' 'OK' "raccourci « $($m.shortcutName) » en place")) }
        elseif ($Fix -and $m.PSObject.Properties['profileDir']) {
            & (Join-Path $script:ScriptsDir 'Install-ClaudeIdentity.ps1') -Name $m.name -ProfileDir $m.profileDir -ConfigDir $m.configDir `
                -IconPath $m.icon -InstallDir $InstallDir -ShortcutFolder (Split-Path -Parent $m.shortcut) -ShortcutName $m.shortcutName -AppId $m.appId -Apply | Out-Null
            $checks.Add((New-Check 'Icône et bouton de B' 'FIXED' ('réinstallé : ' + ($broken -join ', '))))
        } else {
            $checks.Add((New-Check 'Icône et bouton de B' 'TODO' ('à refaire : ' + ($broken -join ', ')) 'Relance avec -Fix.'))
        }
    } else {
        $checks.Add((New-Check 'Icône et bouton de B' 'TODO' 'non installé' 'Voir le mode opératoire (Install-ClaudeIdentity.ps1).'))
    }

    # 4. Router registration in the REAL registry (login routing for B).
    $reg = ConvertFrom-ClaudeToolJson (Invoke-ClaudePython -Python $py -Script 'Apply-RouterRegistration.py' -Arguments @('--install-dir', $InstallDir))
    if (-not $reg) {
        $checks.Add((New-Check 'Routeur de connexion' 'TODO' 'contrôle impossible' 'Relance depuis le raccourci du bureau.'))
    } elseif ($reg.real_registry_matches_desired) {
        $checks.Add((New-Check 'Routeur de connexion' 'OK' 'enregistré'))
    } elseif ($Fix -and $reg.real_registry_empty -and $reg.receipt_matches_desired) {
        $res = ConvertFrom-ClaudeToolJson (Invoke-ClaudePython -Python $py -Script 'Apply-RouterRegistration.py' -Arguments @('--install-dir', $InstallDir, '--apply', '--approved'))
        $done = $res -and (Get-ClaudeJsonField $res 'applied')
        $checks.Add((New-Check 'Routeur de connexion' $(if ($done) { 'FIXED' } else { 'TODO' }) $(if ($done) { 'réenregistré' } else { 'refusé : ' + [string](Get-ClaudeJsonField $res 'result') })))
    } else {
        $checks.Add((New-Check 'Routeur de connexion' 'TODO' 'absent du registre' 'Relance avec -Fix.'))
    }

    # 5. Shared config links.
    $previewText = Invoke-ClaudePython -Python $py -Script 'Link-SharedConfig.py' -Arguments @('--install-dir', $InstallDir)
    $preview = if (ConvertFrom-ClaudeToolJson $previewText) { ConvertFrom-ClaudeLinkPreview -Json $previewText.Substring($previewText.IndexOf('{')) } else { [pscustomobject]@{ Ok = $false; Reason = 'sortie illisible'; Pending = 0; Already = 0; Refused = @() } }
    if (-not $preview.Ok) {
        $checks.Add((New-Check 'Partage de la config' 'TODO' ('contrôle impossible : ' + $preview.Reason)))
    } elseif ($preview.Pending -eq 0 -and $preview.Refused.Count -eq 0) {
        $checks.Add((New-Check 'Partage de la config' 'OK' "$($preview.Already) liens en place"))
    } elseif ($Fix -and -not $bRunning) {
        $applyText = Invoke-ClaudePython -Python $py -Script 'Link-SharedConfig.py' -Arguments @('--install-dir', $InstallDir, '--apply', '--approved', '--replace-files')
        $apply = if (ConvertFrom-ClaudeToolJson $applyText) { ConvertFrom-ClaudeLinkApply -Json $applyText.Substring($applyText.IndexOf('{')) } else { [pscustomobject]@{ Ok = $false; Linked = 0; Reason = 'sortie illisible' } }
        $checks.Add((New-Check 'Partage de la config' $(if ($apply.Ok) { 'FIXED' } else { 'TODO' }) $(if ($apply.Ok) { "$($apply.Linked) liens (re)posés" } else { 'refusé : ' + $apply.Reason })))
    } elseif ($Fix -and $bRunning) {
        $checks.Add((New-Check 'Partage de la config' 'BLOCKED' 'B est ouvert' 'Ferme B, puis relance la réparation.'))
    } else {
        $checks.Add((New-Check 'Partage de la config' 'TODO' ("$($preview.Pending) à poser" + $(if ($preview.Refused.Count) { ', refusés : ' + ($preview.Refused -join ', ') } else { '' })) 'Ferme B puis relance avec -Fix.'))
    }

    # 6. Which app owns claude:// links right now.
    switch (Read-ClaudeLinkHandler) {
        'official' { $checks.Add((New-Check 'Liens claude://' 'OK' 'application Claude officielle (état normal)')) }
        'router'   { $checks.Add((New-Check 'Liens claude://' 'INFO' 'routeur actif' 'Normal pendant une connexion de B ; ensuite remets « Claude » par défaut.')) }
        'none'     { $checks.Add((New-Check 'Liens claude://' 'INFO' 'aucun choix enregistré' 'Windows te le demandera à la prochaine connexion.')) }
        default    { $checks.Add((New-Check 'Liens claude://' 'TODO' 'une autre application les reçoit' 'Choisis « Claude » dans Paramètres > Applications par défaut.')) }
    }

    # 6b. Scheduled Code tasks live in the shared sessions folder: with tasks, both apps would fire them.
    $taskFile = @(Get-ChildItem -Path (Join-Path $bData 'claude-code-sessions\*\*\scheduled-tasks.json') -ErrorAction SilentlyContinue) | Select-Object -First 1
    if ($taskFile) {
        $tasks = Get-ClaudeScheduledTaskCount -Path $taskFile.FullName
        if ($tasks -gt 0) {
            $checks.Add((New-Check 'Tâches planifiées' 'INFO' "$tasks tâche(s), communes à A et B" 'Si A et B sont ouvertes à l''heure prévue, la tâche peut se lancer deux fois : ferme l''une des deux.'))
        } else {
            $checks.Add((New-Check 'Tâches planifiées' 'OK' 'aucune tâche planifiée partagée'))
        }
    }

    # 6c. The base installation's ownership receipt (needed only by the native removal/rollback of B).
    $receipt = Get-ClaudeReceiptState -Python $py -InstallDir $InstallDir
    if ($receipt -eq 'OK') {
        $checks.Add((New-Check 'Reçu d''installation' 'OK' 'valide'))
    } else {
        $checks.Add((New-Check 'Reçu d''installation' 'INFO' "à réconcilier ($receipt)" 'Sans effet au quotidien. Le retrait et la restauration natifs de B restent indisponibles tant qu''il ne l''est pas.'))
    }

    # 7. Remember the package version we last saw healthy.
    $unresolved = @($checks | Where-Object { $_.State -in 'TODO', 'BLOCKED' }).Count
    if ($unresolved -eq 0) {
        [ordered]@{ schema = 1; packageVersion = $version; checkedAt = (Get-Date).ToString('s') } |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $InstallDir 'repair-state.json') -Encoding UTF8
    }
    return $checks
}

function ConvertFrom-ClaudeLinkApply {
    param([string]$Json)
    $o = $Json | ConvertFrom-Json
    if ($o.status -eq 'APPLIED') { return [pscustomobject]@{ Ok = (@(Get-ClaudeJsonField $o 'problems').Count -eq 0); Linked = $o.linked; Reason = '' } }
    return [pscustomobject]@{ Ok = $false; Linked = 0; Reason = [string]((Get-ClaudeJsonField $o 'reason') + (Get-ClaudeJsonField $o 'error')) }
}

function Show-ClaudeChecks {
    param($Checks)
    $labels = @{ OK = '  OK    '; TODO = ' A FAIRE '; INFO = '  info  '; FIXED = ' RÉPARÉ '; BLOCKED = ' BLOQUÉ  ' }
    $colors = @{ OK = 'Green'; TODO = 'Yellow'; INFO = 'Gray'; FIXED = 'Cyan'; BLOCKED = 'Red' }
    foreach ($c in $Checks) {
        Write-Host ('[{0}] {1,-24} {2}' -f $labels[$c.State], $c.Name, $c.Detail) -ForegroundColor $colors[$c.State]
        if ($c.Hint -and $c.State -in 'TODO', 'BLOCKED', 'INFO') { Write-Host ('           -> ' + $c.Hint) -ForegroundColor DarkGray }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    $exit = 0
    try {
        Write-Host ''
        Write-Host ($(if ($Fix) { 'Contrôle et réparation des comptes Claude A et B' } else { 'Contrôle des comptes Claude A et B (lecture seule)' })) -ForegroundColor White
        $result = Invoke-ClaudeRepair -InstallDir $InstallDir -RepoDir $RepoDir -Fix:$Fix
        Show-ClaudeChecks -Checks $result
        $todo = @($result | Where-Object { $_.State -in 'TODO', 'BLOCKED' }).Count
        Write-Host ''
        if ($todo -eq 0) { Write-Host 'Tout est en ordre.' -ForegroundColor Green }
        else {
            $exit = if (@($result | Where-Object { $_.Name -eq 'Contexte' -and $_.State -eq 'BLOCKED' }).Count) { 2 } else { 1 }
            $blocked = [bool](@($result | Where-Object { $_.Name -eq 'Contexte' -and $_.State -eq 'BLOCKED' }).Count)
            Write-Host $(if ($blocked) { 'Rien n''a été contrôlé : relance depuis le raccourci du bureau.' } else { "$todo point(s) à traiter$(if (-not $Fix) { ' : relance avec -Fix (ou le raccourci « Réparer »)' })." }) -ForegroundColor Yellow
        }
    } catch {
        Write-Host ('Erreur : ' + $_.Exception.Message) -ForegroundColor Red
        $exit = 1
    }
    if ($Pause) { Write-Host ''; [void](Read-Host 'Appuie sur Entrée pour fermer') }
    exit $exit
}
