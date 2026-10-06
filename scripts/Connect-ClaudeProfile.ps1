<#
.SYNOPSIS
    Guides a (re)login of account B (or A) when Claude asks to sign in again.
.DESCRIPTION
    A claude:// login callback goes to whichever app owns those links. For B, the login
    router must own them for the length of ONE login, because only it can send the callback
    to B's window instead of A's. Windows does not let a program choose the default app, so
    that single click stays yours; everything else is automated:
      1. checks the router is registered,
      2. waits while you choose "Claude Login Router" in Default apps (opened for you),
      3. arms B for one callback (five minutes), opens B with its own icon,
      4. waits for B's stored login to change,
      5. waits while you put "Claude" back as the default app, then disarms.
    Account A needs no router: the official app already owns the links for its own data dir.
    No credential, token or cookie is read, copied or printed; only whether the stored login
    changed is observed (as a hash).
.PARAMETER Profile
    B (default) or A.
.PARAMETER InstallDir
    Parent folder of the installation (default %USERPROFILE%\ClaudeProfiles).
.PARAMETER WaitMinutes
    How long to wait for the login to complete (default 6).
.PARAMETER Pause
    Wait for Enter before closing (used by the desktop shortcut).
.NOTES
    Windows PowerShell 5.1 and PowerShell 7, no admin rights. Run it from the desktop shortcut
    or a PowerShell opened from the Start menu, not from inside Codex or Claude Desktop.
#>
[CmdletBinding()]
param(
    [ValidateSet('A', 'B')][string]$Profile = 'B',
    [string]$InstallDir = (Join-Path $env:USERPROFILE 'ClaudeProfiles'),
    [int]$WaitMinutes = 6,
    [switch]$Pause
)

$script:ScriptsDir = Split-Path -Parent $PSCommandPath
$requested = @{ Profile = $Profile; InstallDir = $InstallDir; WaitMinutes = $WaitMinutes; Pause = $Pause }
. (Join-Path $script:ScriptsDir 'Repair-ClaudeProfiles.ps1')

function Get-ClaudeLoginFingerprint {
    <# Hash of the stored login entry (not its value): changes when a login completes. #>
    param([string]$DataDir)
    $file = Join-Path $DataDir 'config.json'
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { return '' }
    try { $json = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json } catch { return '' }
    $entry = $json.PSObject.Properties['oauth:tokenCacheV2']
    if (-not $entry) { return '' }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes([string]$entry.Value))) } finally { $sha.Dispose() }
}

function Wait-ClaudeCondition {
    param([scriptblock]$Condition, [int]$TimeoutSeconds, [int]$PollSeconds = 2)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return $true }
        Start-Sleep -Seconds $PollSeconds
    }
    return $false
}

function Get-ClaudeRouteIntentStatus {
    param([string]$InstallDir)
    $file = Join-Path $InstallDir 'bin\target.txt'
    if (-not (Test-Path -LiteralPath $file)) { return 'none' }
    try { return [string](Get-Content -LiteralPath $file -Raw | ConvertFrom-Json).status } catch { return 'unknown' }
}

function Connect-ClaudeProfile {
    param([string]$Profile, [string]$InstallDir, [int]$WaitMinutes)
    $ErrorActionPreference = 'Continue'   # reg.exe prints to stderr when a key is absent
    $profiles = (Get-Content -LiteralPath (Join-Path $InstallDir 'bin\profiles.json') -Raw | ConvertFrom-Json).profiles
    $dataDir = $profiles.PSObject.Properties[$Profile].Value.dataDir

    if ($Profile -eq 'A') {
        Write-Host 'Compte A : le routeur n''est pas nécessaire.' -ForegroundColor White
        if ((Read-ClaudeLinkHandler) -ne 'official') {
            Write-Host 'Choisis d''abord « Claude » pour les liens claude:// (Paramètres > Applications par défaut).' -ForegroundColor Yellow
            Start-Process 'ms-settings:defaultapps'
        }
        Write-Host 'Ouvre « Claude (A existing) », clique sur la connexion et termine dans le navigateur.'
        return 0
    }

    # 1. Router registered?
    & reg.exe query 'HKCU\Software\RegisteredApplications' /v ClaudeShim 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Le routeur de connexion n''est pas enregistré. Lance d''abord « Réparer Claude (A+B) ».' -ForegroundColor Red
        return 1
    }
    $before = Get-ClaudeLoginFingerprint -DataDir $dataDir

    # 2. The one click Windows keeps for you.
    if ((Read-ClaudeLinkHandler) -ne 'router') {
        Write-Host ''
        Write-Host 'ÉTAPE 1 sur 3 : choisis le routeur pour les liens « claude »' -ForegroundColor White
        Write-Host '  Paramètres s''ouvre : tape « claude » dans la recherche de « Choisir les valeurs par défaut selon le type de lien »,'
        Write-Host '  clique sur « CLAUDE », sélectionne « Claude Login Router », puis « Définir par défaut ».'
        Start-Process 'ms-settings:defaultapps'
        if (-not (Wait-ClaudeCondition -Condition { (Read-ClaudeLinkHandler) -eq 'router' } -TimeoutSeconds 240)) {
            Write-Host 'Choix non détecté après 4 minutes : rien n''a été armé. Relance quand c''est fait.' -ForegroundColor Yellow
            return 1
        }
        Write-Host '  Routeur choisi.' -ForegroundColor Green
    }

    # 3. Arm B for one callback and open it with its own icon.
    Write-Host ''
    Write-Host 'ÉTAPE 2 sur 3 : connexion de B (5 minutes pour la faire)' -ForegroundColor White
    $arm = Join-Path $InstallDir 'bin\Arm-ClaudeLogin.ps1'
    & $arm -Profile B
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Armement refusé (une intention est déjà en attente ?). Désarme avec : Arm-ClaudeLogin.ps1 -Profile default, puis relance.' -ForegroundColor Red
        return 1
    }
    $identity = Join-Path $InstallDir 'identity\identity.json'
    if (Test-Path -LiteralPath $identity) { Start-Process -FilePath (Get-Content -LiteralPath $identity -Raw | ConvertFrom-Json).shortcut }
    else { Write-Host '  Ouvre « Claude (B) » toi-même.' }
    Write-Host '  Dans la fenêtre B : clique sur la connexion, vérifie dans le navigateur que c''est bien le compte B, autorise.'
    Write-Host '  (Si c''est la fenêtre A qui réagit, arrête là : ne relance pas de connexion.)'

    $done = Wait-ClaudeCondition -Condition { (Get-ClaudeLoginFingerprint -DataDir $dataDir) -ne $before -and (Get-ClaudeLoginFingerprint -DataDir $dataDir) -ne '' } -TimeoutSeconds ($WaitMinutes * 60) -PollSeconds 3
    $status = Get-ClaudeRouteIntentStatus -InstallDir $InstallDir
    if ($done) { Write-Host '  Connexion de B enregistrée.' -ForegroundColor Green }
    else {
        Write-Host "  Pas de nouvelle connexion détectée (intention : $status). Ferme les onglets de connexion et relance si besoin." -ForegroundColor Yellow
    }
    # Never leave an intent armed behind us.
    if ((Get-ClaudeRouteIntentStatus -InstallDir $InstallDir) -eq 'armed') { & $arm -Profile default | Out-Null }

    # 4. Give the links back to the official app.
    Write-Host ''
    Write-Host 'ÉTAPE 3 sur 3 : remets « Claude » pour les liens claude://' -ForegroundColor White
    Write-Host '  Même fenêtre Paramètres : « CLAUDE » > « Claude » > « Définir par défaut ».'
    Start-Process 'ms-settings:defaultapps'
    if (Wait-ClaudeCondition -Condition { (Read-ClaudeLinkHandler) -eq 'official' } -TimeoutSeconds 240) {
        Write-Host '  Terminé : A et B sont connectés, les liens sont rendus à Claude.' -ForegroundColor Green
        return $(if ($done) { 0 } else { 1 })
    }
    Write-Host '  Le routeur reste par défaut : pense à remettre « Claude », sinon une future connexion de A serait refusée.' -ForegroundColor Yellow
    return 1
}

if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    $exit = 0
    try { $exit = Connect-ClaudeProfile -Profile $requested.Profile -InstallDir $requested.InstallDir -WaitMinutes $requested.WaitMinutes }
    catch { Write-Host ('Erreur : ' + $_.Exception.Message) -ForegroundColor Red; $exit = 1 }
    if ($requested.Pause) { Write-Host ''; [void](Read-Host 'Appuie sur Entrée pour fermer') }
    exit $exit
}
