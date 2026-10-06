<#
.SYNOPSIS
    Explicit native workspace candidate wrapper (IMPLEMENTED_NOT_TESTED).
.DESCRIPTION
    Default invocation refuses mutations. NativeSpec supplies a reviewed private
    specification; NativePreview saves a new private approval capsule. Installation
    requires NativeApproval, Approved and WritersClosed. ApproveProtocol is separate.
    Legacy profile/path switches cannot be combined with this native branch.
    No dependency installation, login/restart or official package removal.
    Qualify on isolated fixtures before separately authorized real-profile use.
#>
[CmdletBinding()]
param(
    [string[]]$Profile = @('Work', 'Personal'),
    [string]$DefaultProfile = 'None',
    [switch]$ReuseDefaultForWork,
    [string]$InstallDir = (Join-Path $env:USERPROFILE 'ClaudeProfiles'),
    [hashtable]$ConfigDir = @{},
    [hashtable]$DataDir = @{},
    [switch]$NoProtocolRouting,
    [switch]$LoginShortcuts,
    [string]$NativeSpec,
    [string]$NativePreview,
    [string]$NativeApproval,
    [switch]$Approved,
    [switch]$WritersClosed,
    [switch]$ApproveProtocol
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($NativeSpec) {
    foreach ($legacy in @('Profile', 'DefaultProfile', 'ReuseDefaultForWork', 'InstallDir', 'ConfigDir', 'DataDir', 'NoProtocolRouting', 'LoginShortcuts')) {
        if ($PSBoundParameters.ContainsKey($legacy)) { throw 'NATIVE_SPEC_CONTROLS_PATHS' }
    }
    $python = Get-Command python -CommandType Application -ErrorAction Stop
    if ($python.Source -like '*\Microsoft\WindowsApps\*') { throw 'PYTHON_RUNTIME_REQUIRED' }
    $entry = Join-Path $scriptRoot 'SharedWorkspace.py'
    if ($NativePreview) {
        if ($Approved -or $NativeApproval -or $WritersClosed -or $ApproveProtocol) { throw 'NATIVE_PREVIEW_ARGUMENTS' }
        & $python.Source -B $entry native-preview --spec $NativeSpec --output $NativePreview
    } else {
        if (-not $NativeApproval -or -not $Approved -or -not $WritersClosed) {
            throw 'NATIVE_APPROVAL_AND_CLOSED_WRITERS_REQUIRED'
        }
        $arguments = @('-B', $entry, 'native-install', '--spec', $NativeSpec,
                       '--approval', $NativeApproval, '--approved', '--writers-closed')
        if ($ApproveProtocol) { $arguments += '--approve-protocol' }
        & $python.Source @arguments
    }
    if ($LASTEXITCODE -ne 0) { throw 'NATIVE_WORKSPACE_OPERATION_REFUSED' }
    return
}

# The legacy installer below force-copies assets and cannot prove additive ownership.
# Keep its fragments for regression tests, but refuse full invocation before any OS IO.
throw 'NATIVE_INSTALL_NOT_ADMITTED: use python -B scripts/SharedWorkspace.py preview --spec <private-spec.json>.'

# --- resolve the effective "default" (stock-paths) profile -----------------
# -DefaultProfile wins; -ReuseDefaultForWork is a deprecated alias for 'Work'.
if (-not $PSBoundParameters.ContainsKey('DefaultProfile') -and $ReuseDefaultForWork) {
    $DefaultProfile = 'Work'
    Write-Warning "-ReuseDefaultForWork is deprecated; treating it as -DefaultProfile Work."
} elseif ($PSBoundParameters.ContainsKey('DefaultProfile') -and $ReuseDefaultForWork) {
    Write-Warning "-ReuseDefaultForWork ignored because -DefaultProfile was given explicitly."
}
if ($DefaultProfile -ne 'None' -and $Profile -notcontains $DefaultProfile) {
    # Case-insensitive tolerance: normalise to the declared spelling if it matches.
    $hit = $Profile | Where-Object { $_ -ieq $DefaultProfile } | Select-Object -First 1
    if ($hit) { $DefaultProfile = $hit }
    else { throw "-DefaultProfile '$DefaultProfile' is not in -Profile ($($Profile -join ', '))." }
}

# Extracts the highest-resolution icon out of an .exe into a standalone .ico.
# This is what makes shortcut icons survive app updates: the Claude .exe lives
# under C:\Program Files\WindowsApps\Claude_<version>__...\app\Claude.exe, and
# that <version> folder is DELETED whenever Claude auto-updates. A shortcut whose
# IconLocation points straight at that versioned path goes blank after the next
# update + icon-cache rebuild (typically noticed after a reboot). Copying the
# icon once to a stable file under bin\ and pointing every shortcut there avoids
# the dangling path entirely.
function Export-AppIcon {
    param([string]$ExePath, [string]$IcoPath, [int]$Size = 256)
    Add-Type -AssemblyName System.Drawing
    $sig = @'
[DllImport("user32.dll", CharSet=CharSet.Unicode)]
public static extern int PrivateExtractIcons(string lpszFile, int nIconIndex, int cxIcon, int cyIcon, IntPtr[] phicon, int[] piconid, int nIcons, int flags);
[DllImport("user32.dll")]
public static extern bool DestroyIcon(IntPtr hIcon);
'@
    $api = Add-Type -MemberDefinition $sig -Name 'IconExtract' -Namespace 'Win32Native' -PassThru

    # Writes a 32-bit, full-colour, PNG-compressed .ico (Vista+ format) from a
    # Bitmap. We deliberately do NOT use Icon.Save(): saving an Icon created from
    # an HICON drops the colour plane and writes only the 1-bit AND mask, which is
    # why the icon came out grey. Rendering to a Bitmap and packing the PNG
    # ourselves preserves colour and alpha.
    function Write-IcoFromBitmap {
        param([System.Drawing.Bitmap]$Bmp, [string]$Path)
        $ms = New-Object System.IO.MemoryStream
        $Bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $png = $ms.ToArray(); $ms.Dispose()
        $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Create)
        $bw = New-Object System.IO.BinaryWriter($fs)
        $bw.Write([uint16]0)            # reserved
        $bw.Write([uint16]1)            # type = icon
        $bw.Write([uint16]1)            # image count
        $dim = if ($Bmp.Width -ge 256) { 0 } else { [byte]$Bmp.Width }   # 0 means 256
        $bw.Write([byte]$dim)           # width
        $bw.Write([byte]$dim)           # height
        $bw.Write([byte]0)              # palette count
        $bw.Write([byte]0)              # reserved
        $bw.Write([uint16]1)            # colour planes
        $bw.Write([uint16]32)           # bits per pixel
        $bw.Write([uint32]$png.Length)  # image size
        $bw.Write([uint32]22)           # offset = 6 (dir) + 16 (entry)
        $bw.Write($png)
        $bw.Flush(); $bw.Close()
    }

    $h = New-Object IntPtr[] 1
    $id = New-Object int[] 1
    try {
        $n = $api::PrivateExtractIcons($ExePath, 0, $Size, $Size, $h, $id, 1, 0)
        if ($n -gt 0 -and $h[0] -ne [IntPtr]::Zero) {
            $ico = [System.Drawing.Icon]::FromHandle($h[0])
            $bmp = $ico.ToBitmap()       # full 32bpp colour + alpha
            Write-IcoFromBitmap -Bmp $bmp -Path $IcoPath
            $bmp.Dispose(); $ico.Dispose()
            return $true
        }
    } catch {
    } finally {
        if ($h[0] -ne [IntPtr]::Zero) { $api::DestroyIcon($h[0]) | Out-Null }
    }
    # Fallback: managed helper (lower-res, but still full colour and a stable file).
    try {
        $ico = [System.Drawing.Icon]::ExtractAssociatedIcon($ExePath)
        $bmp = $ico.ToBitmap()
        Write-IcoFromBitmap -Bmp $bmp -Path $IcoPath
        $bmp.Dispose(); $ico.Dispose()
        return $true
    } catch { return $false }
}

# --- Verify the Claude Desktop app is installed and find its icon ---------
$pkg = Get-AppxPackage -Name '*Claude*' -ErrorAction SilentlyContinue |
    Sort-Object Version -Descending | Select-Object -First 1
if (-not $pkg) {
    throw "Claude Desktop app not found. Install it from https://claude.ai/download (or the Microsoft Store) first."
}
$iconExe = Join-Path $pkg.InstallLocation 'app\Claude.exe'
Write-Host "Found Claude $($pkg.Version) at $($pkg.InstallLocation)" -ForegroundColor Green

# --- Copy launcher + router scripts to a stable location -------------------
$binDir = Join-Path $InstallDir 'bin'
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
foreach ($f in 'Launch-Claude.ps1', 'launch.vbs', 'ClaudeOpenShim.ps1', 'Arm-ClaudeLogin.ps1') {
    Copy-Item (Join-Path $scriptRoot $f) $binDir -Force
}
$vbs         = Join-Path $binDir 'launch.vbs'
$shimPath    = Join-Path $binDir 'ClaudeOpenShim.ps1'
$armPath     = Join-Path $binDir 'Arm-ClaudeLogin.ps1'
$profilesJson = Join-Path $binDir 'profiles.json'

# --- Extract the Claude icon to a STABLE path (survives app updates) -------
# See Export-AppIcon above for why pointing IconLocation at the versioned
# WindowsApps .exe makes icons disappear after updates/reboots.
$icoPath = Join-Path $binDir 'claude.ico'
if (Export-AppIcon -ExePath $iconExe -IcoPath $icoPath) {
    $iconLocation = "$icoPath,0"
    Write-Host "Extracted stable icon to $icoPath" -ForegroundColor Green
} else {
    # Last resort: fall back to the versioned exe (may go blank after an update).
    $iconLocation = "$iconExe,0"
    Write-Warning "Could not extract a standalone icon; falling back to the app exe (icon may break after updates)."
}

# --- Create a profile + desktop shortcut for each name --------------------
$desktop = [Environment]::GetFolderPath('Desktop')
$wsh = New-Object -ComObject WScript.Shell
$profileMap = [ordered]@{}

foreach ($name in $Profile) {
    $isDefault = ($DefaultProfile -ne 'None' -and $name -ieq $DefaultProfile)

    if ($isDefault) {
        $profileDataDir   = Join-Path $env:APPDATA 'Claude'
        $profileConfigDir = ''   # stock ~\.claude; do NOT set CLAUDE_CONFIG_DIR
        Write-Host "  [$name] reuses the stock login at $profileDataDir"
    } else {
        # IMPORTANT: isolated profiles must live directly under %APPDATA% (NOT an
        # arbitrary folder such as -InstallDir). Claude Desktop's "Cowork" feature
        # runs its agent inside a Hyper-V VM, and the native VM service resolves
        # the VM image (rootfs.vhdx) at %APPDATA%\<dir-name>\vm_bundles -- it
        # ignores --user-data-dir. If the data dir lives elsewhere, Electron
        # provisions the VM under the data dir but the VM service looks under
        # %APPDATA% and dies with "VHDX file not found". Deriving
        # %APPDATA%\Claude-<name> satisfies this by construction.
        $profileDataDir   = Join-Path $env:APPDATA "Claude-$name"
        $profileConfigDir = Join-Path $env:USERPROFILE (".claude-" + $name.ToLower())
        Write-Host "  [$name] isolated profile at $profileDataDir"
    }

    # Keep per-profile paths distinct from the hashtable parameters: PowerShell
    # variable names are case-insensitive ($DataDir and $dataDir are the same).
    # Per-profile overrides; never overwrite the caller-supplied maps.
    if ($DataDir.ContainsKey($name))   { $profileDataDir   = $DataDir[$name] }
    if ($ConfigDir.ContainsKey($name)) { $profileConfigDir = $ConfigDir[$name] }

    New-Item -ItemType Directory -Force -Path $profileDataDir | Out-Null
    if ($profileConfigDir) {
        New-Item -ItemType Directory -Force -Path $profileConfigDir | Out-Null
        Write-Host "      memory/config dir: $profileConfigDir"
    }

    $profileMap[$name] = [ordered]@{
        dataDir   = $profileDataDir
        configDir = $profileConfigDir
        isDefault = [bool]$isDefault
    }

    # Main launch shortcut.
    $lnkPath = Join-Path $desktop "Claude ($name).lnk"
    $sc = $wsh.CreateShortcut($lnkPath)
    $sc.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
    if ($profileConfigDir) {
        $sc.Arguments = '"{0}" "{1}" "{2}"' -f $vbs, $profileDataDir, $profileConfigDir
    } else {
        $sc.Arguments = '"{0}" "{1}"' -f $vbs, $profileDataDir
    }
    $sc.IconLocation = $iconLocation
    $sc.Description = "Claude Desktop - $name profile"
    $sc.WorkingDirectory = $binDir
    $sc.Save()
    Write-Host "  -> created shortcut: $lnkPath" -ForegroundColor Cyan

    # Optional "Sign in" shortcut: arm the router for this profile, then launch.
    if ($LoginShortcuts -and -not $NoProtocolRouting) {
        $signLnk = Join-Path $desktop "Claude ($name) - Sign in.lnk"
        $ssc = $wsh.CreateShortcut($signLnk)
        $ssc.TargetPath = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $ssc.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Profile "{1}" -Launch' -f $armPath, $name
        $ssc.IconLocation = $iconLocation
        $ssc.Description = "Arm the claude:// router for the $name profile, then open it to sign in"
        $ssc.WorkingDirectory = $binDir
        $ssc.Save()
        Write-Host "  -> created sign-in shortcut: $signLnk" -ForegroundColor Cyan
    }
}

# --- Write profiles.json (shared contract for Arm/Test scripts) ------------
$profilesObj = [ordered]@{
    defaultProfile = $DefaultProfile
    generated      = (Get-Date -Format s)
    profiles       = $profileMap
}
$profilesObj | ConvertTo-Json -Depth 5 | Set-Content $profilesJson -Encoding UTF8
Write-Host "Wrote profile map: $profilesJson"

# --- Register the claude:// login router (unless opted out) ----------------
if ($NoProtocolRouting) {
    Write-Host ""
    Write-Host "Protocol routing skipped (-NoProtocolRouting). Sequence logins manually:" -ForegroundColor Yellow
    Write-Host "  log into one account at a time with the other profiles closed."
} else {
    # Command that Windows will run for a claude:// activation. It MUST embed a
    # LITERAL expanded path -- Set-ItemProperty writes REG_SZ, which does not
    # expand %USERPROFILE%-style variables.
    $cmd = "conhost --headless powershell -NoProfile -ExecutionPolicy Bypass -File `"$shimPath`" -Url `"%1`""

    # Back up any pre-existing classic-key command ONCE, before it can be
    # overwritten by a later Setup run. This preserves (e.g.) a leftover
    # Squirrel registration so Uninstall.ps1 can restore it. Idempotent: only
    # writes 'backup' if it isn't already present.
    $classicCmdKey = 'HKCU:\Software\Classes\claude\shell\open\command'
    if (Test-Path $classicCmdKey) {
        # '' names the key's default value; 'backup' is our named backup slot.
        $existing  = (Get-Item $classicCmdKey).GetValue('', $null)
        $hasBackup = (Get-Item $classicCmdKey).GetValue('backup', $null)
        if ($existing -and -not $hasBackup -and $existing -ne $cmd) {
            Set-ItemProperty $classicCmdKey 'backup' $existing
            Write-Host "Backed up existing claude:// classic-key command to its 'backup' value."
        }
    }

    # ProgId the chooser will point at.
    New-Item 'HKCU:\Software\Classes\ClaudeShim.claude\shell\open\command' -Force | Out-Null
    Set-ItemProperty 'HKCU:\Software\Classes\ClaudeShim.claude' '(Default)' 'URL:Claude Protocol'
    Set-ItemProperty 'HKCU:\Software\Classes\ClaudeShim.claude' 'URL Protocol' ''
    Set-ItemProperty 'HKCU:\Software\Classes\ClaudeShim.claude\shell\open\command' '(Default)' $cmd

    # Register an "application" exposing the claude protocol (Default Apps eligibility).
    New-Item 'HKCU:\Software\ClaudeShim\Capabilities\URLAssociations' -Force | Out-Null
    Set-ItemProperty 'HKCU:\Software\ClaudeShim\Capabilities' 'ApplicationName' 'Claude Login Router'
    Set-ItemProperty 'HKCU:\Software\ClaudeShim\Capabilities' 'ApplicationDescription' 'Routes claude:// logins to the chosen profile'
    Set-ItemProperty 'HKCU:\Software\ClaudeShim\Capabilities\URLAssociations' 'claude' 'ClaudeShim.claude'
    New-Item 'HKCU:\Software\RegisteredApplications' -Force -ErrorAction SilentlyContinue | Out-Null
    Set-ItemProperty 'HKCU:\Software\RegisteredApplications' 'ClaudeShim' 'Software\ClaudeShim\Capabilities'

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host " ONE MANUAL STEP to activate claude:// login routing" -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host " Windows only lets a user (not a script) pick the default"
    Write-Host " handler for a protocol. Do this once:"
    Write-Host ""
    Write-Host "   Settings > Apps > Default apps >"
    Write-Host "     'Choose defaults by link type' > search 'claude' >"
    Write-Host "     select 'Console Window Host'."
    Write-Host ""
    Write-Host " Why 'Console Window Host'? Settings labels a handler after the"
    Write-Host " first exe in its command (here 'conhost'), not our app name."
    Write-Host " This is cosmetic -- it is still the Claude login router."
    Write-Host ""
    Write-Host " If 'claude' doesn't appear, close and reopen Settings"
    Write-Host " (it caches the registered-applications list)."
    Write-Host ""
    Write-Host " Passive observations only: scripts\Test-ClaudeRouting.ps1" -ForegroundColor Cyan
    Write-Host " It does not activate a link or prove Desktop delivery/login."
    Write-Host " Missing/busy metadata remains unknown; do not publish old logs."
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host " To route a login:  bin\Arm-ClaudeLogin.ps1 -Profile <name> -Launch"
    Write-Host " Choose the explicit A/B name for one login; verify the browser account."
    Write-Host " Five-minute intent; consumed before launch; no fallback account."
    Write-Host " -Profile default disarms only. Arming does not change registration."
}

Write-Host ""
Write-Host "Done. Open each shortcut and sign in to the matching account." -ForegroundColor Green
Write-Host "Tip: clicking a shortcut again just focuses that profile's window (single instance per profile)."
