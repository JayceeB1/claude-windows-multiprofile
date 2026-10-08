<#
.SYNOPSIS
    Tests the taskbar identity module, launcher and installer on owned TEMP fixtures.
.DESCRIPTION
    No Claude process, profile, registry write or real shortcut folder. Real Windows
    pieces are exercised: COM shortcut with AppUserModelID read-back, and a throwaway
    WinForms window in a child PowerShell that receives the identity. Everything lives
    under a unique TEMP folder removed at the end. Windows PowerShell 5.1 or PowerShell 7.
.EXAMPLE
    .\tests\Test-ClaudeIdentity.ps1
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
    if (-not $caught -or $caught.Exception.Message -notmatch $Pattern) {
        throw "$Name did not fail for the expected reason ($Pattern)."
    }
    $script:assertions++
}

# Parse every new script before anything runs.
foreach ($name in 'Set-ClaudeWindowIdentity.ps1', 'Launch-ClaudeIdentity.ps1', 'Install-ClaudeIdentity.ps1') {
    $tokens = $null; $errors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $scripts $name), [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
}
. (Join-Path $scripts 'Set-ClaudeWindowIdentity.ps1')

# --- Command-line matching: only the MAIN process of the right profile.
$exe = 'C:\Program Files\WindowsApps\Claude_1\app\Claude.exe'
Assert-Equal 'quoted data dir matches' $true (Test-ClaudeCommandLine "`"$exe`" --user-data-dir=`"C:\Users\x\AppData\Roaming\Claude-B`"" 'C:\Users\x\AppData\Roaming\Claude-B')
Assert-Equal 'trailing slash and case are ignored' $true (Test-ClaudeCommandLine "$exe --user-data-dir=c:\users\x\appdata\roaming\claude-b\" 'C:\Users\x\AppData\Roaming\Claude-B')
Assert-Equal 'other profile does not match' $false (Test-ClaudeCommandLine "$exe --user-data-dir=`"C:\Users\x\AppData\Roaming\Claude`"" 'C:\Users\x\AppData\Roaming\Claude-B')
Assert-Equal 'prefix of another dir does not match' $false (Test-ClaudeCommandLine "$exe --user-data-dir=`"C:\Users\x\AppData\Roaming\Claude-B2`"" 'C:\Users\x\AppData\Roaming\Claude-B')
Assert-Equal 'child process is ignored' $false (Test-ClaudeCommandLine "$exe --type=gpu-process --user-data-dir=`"C:\Users\x\AppData\Roaming\Claude-B`"" 'C:\Users\x\AppData\Roaming\Claude-B')
Assert-Equal 'no data dir argument' $false (Test-ClaudeCommandLine "`"$exe`"" 'C:\Users\x\AppData\Roaming\Claude-B')
Assert-Equal 'empty inputs are false' $false (Test-ClaudeCommandLine '' 'C:\x')

$root = Join-Path ([IO.Path]::GetTempPath()) ('claude-identity-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
$null = New-Item -ItemType Directory -Path $root
$child = $null
try {
    # A genuine multi-size .ico built from a bitmap (no Claude artwork involved).
    Add-Type -AssemblyName System.Drawing
    $icon = Join-Path $root 'test.ico'
    $bmp = New-Object System.Drawing.Bitmap 64, 64
    $g = [System.Drawing.Graphics]::FromImage($bmp); $g.Clear([System.Drawing.Color]::MidnightBlue); $g.Dispose()
    $ms = New-Object IO.MemoryStream; $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png); $png = $ms.ToArray(); $bmp.Dispose()
    $bytes = New-Object System.Collections.Generic.List[byte]
    $bytes.AddRange([byte[]](0, 0, 1, 0, 1, 0, 64, 64, 0, 0, 1, 0, 32, 0))
    $bytes.AddRange([BitConverter]::GetBytes([uint32]$png.Length)); $bytes.AddRange([BitConverter]::GetBytes([uint32]22)); $bytes.AddRange($png)
    [IO.File]::WriteAllBytes($icon, $bytes.ToArray())

    # --- Shortcut with an AppUserModelID round-trips through the real COM object.
    $lnk = Join-Path $root 'probe.lnk'
    New-ClaudeIdentityShortcut -Path $lnk -Target (Join-Path $env:SystemRoot 'System32\wscript.exe') -Arguments '"x.vbs" "a b"' `
        -WorkingDirectory $root -IconPath $icon -AppId 'Test.Probe.B' -Description 'probe'
    Assert-Equal 'shortcut AppUserModelID reads back' 'Test.Probe.B' ([ClaudeIdentityNative]::ShortcutAppId($lnk))
    $wsh = New-Object -ComObject WScript.Shell
    $read = $wsh.CreateShortcut($lnk)
    Assert-Equal 'shortcut arguments preserved' '"x.vbs" "a b"' $read.Arguments
    Assert-Equal 'shortcut description preserved' 'probe' $read.Description

    # --- A real window in a child process receives the identity, and re-applies idempotently.
    $formScript = Join-Path $root 'form.ps1'
    Set-Content -LiteralPath $formScript -Encoding UTF8 -Value @'
Add-Type -AssemblyName System.Windows.Forms
$f = New-Object System.Windows.Forms.Form
$f.Text = 'ClaudeIdentityFixture'; $f.ShowInTaskbar = $true
$t = New-Object System.Windows.Forms.Timer; $t.Interval = 60000; $t.Add_Tick({ $f.Close() }); $t.Start()
[System.Windows.Forms.Application]::Run($f)
'@
    $exeName = if ($PSVersionTable.PSEdition -eq 'Core') { 'pwsh.exe' } else { 'powershell.exe' }
    $child = Start-Process $exeName -ArgumentList '-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass', '-File', "`"$formScript`"" -PassThru
    $seen = @{}
    $applied = 0
    $all = $false
    for ($i = 0; $i -lt 80 -and -not $all; $i++) {
        Start-Sleep -Milliseconds 250
        $applied += Set-ClaudeWindowIdentity -ProcessId $child.Id -AppId 'Test.Window.B' -IconPath $icon -Seen $seen
        $windows = @([ClaudeIdentityNative]::Windows([uint32]$child.Id))
        $all = $windows.Count -gt 0 -and @($windows | Where-Object { [ClaudeIdentityNative]::WindowAppId($_) -ceq 'Test.Window.B' }).Count -eq $windows.Count
    }
    Assert-Equal 'identity applied to at least one fixture window' $true ($applied -ge 1)
    Assert-Equal 'every eligible window of the process has the id' $true $all
    Assert-Equal 'second pass changes nothing' 0 (Set-ClaudeWindowIdentity -ProcessId $child.Id -AppId 'Test.Window.B' -IconPath $icon -Seen $seen)
    Assert-Failure 'missing icon is refused' { Set-ClaudeWindowIdentity -ProcessId $child.Id -AppId 'x' -IconPath (Join-Path $root 'none.ico') } 'IconPath'
    Stop-Process -Id $child.Id -Force; $child = $null

    # --- Installer: preview writes nothing; apply installs; foreign things are refused; remove is exact.
    $install = Join-Path $root 'ClaudeProfiles'
    $folder = Join-Path $root 'Desktop'
    $common = @{ Name = 'B'; ProfileDir = 'C:\Fixture\Claude-B'; ConfigDir = 'C:\Fixture\.claude-b'; IconPath = $icon
                InstallDir = $install; ShortcutFolder = $folder }
    & (Join-Path $scripts 'Install-ClaudeIdentity.ps1') @common | Out-Null
    Assert-Equal 'preview creates no install folder' $false (Test-Path -LiteralPath $install)
    Assert-Equal 'preview creates no shortcut folder' $false (Test-Path -LiteralPath $folder)

    & (Join-Path $scripts 'Install-ClaudeIdentity.ps1') @common -Apply | Out-Null
    $shortcut = Join-Path $folder 'Claude (B).lnk'
    Assert-Equal 'shortcut created' $true (Test-Path -LiteralPath $shortcut)
    Assert-Equal 'shortcut carries the app id' 'ClaudeMultiprofile.B' ([ClaudeIdentityNative]::ShortcutAppId($shortcut))
    $made = $wsh.CreateShortcut($shortcut)
    Assert-Equal 'shortcut runs wscript' 'wscript.exe' (Split-Path -Leaf $made.TargetPath).ToLowerInvariant()
    Assert-Equal 'shortcut icon is the installed copy' (Join-Path $install 'identity\claude-b.ico') ($made.IconLocation -replace ',\d+$', '')
    Assert-Equal 'arguments name the data dir, app id and icon' $true (
        $made.Arguments.Contains('"C:\Fixture\Claude-B"') -and $made.Arguments.Contains('"ClaudeMultiprofile.B"') -and
        $made.Arguments.Contains('claude-b.ico"') -and $made.Arguments.Contains('launch-identity.vbs"'))
    foreach ($f in 'Launch-Claude.ps1', 'Set-ClaudeWindowIdentity.ps1', 'Launch-ClaudeIdentity.ps1', 'launch-identity.vbs', 'claude-b.ico', 'identity.json') {
        Assert-Equal "installed $f" $true (Test-Path -LiteralPath (Join-Path $install "identity\$f"))
    }
    Assert-Equal 'receipt-owned bin folder is never created' $false (Test-Path -LiteralPath (Join-Path $install 'bin'))

    $recordedParams = Get-Content -LiteralPath (Join-Path $install 'identity\identity.json') -Raw | ConvertFrom-Json
    Assert-Equal 'manifest records the profile dir for repair' 'C:\Fixture\Claude-B' $recordedParams.profileDir
    Assert-Equal 'manifest records the config dir for repair' 'C:\Fixture\.claude-b' $recordedParams.configDir
    Assert-Equal 'manifest records the shortcut name for repair' 'Claude (B)' $recordedParams.shortcutName
    & (Join-Path $scripts 'Install-ClaudeIdentity.ps1') @common -Apply | Out-Null   # idempotent
    Assert-Equal 'rerun keeps the shortcut' $true (Test-Path -LiteralPath $shortcut)
    # A repair reinstalls from the already installed icon: it must not copy the file onto itself.
    $fromInstalled = $common.Clone(); $fromInstalled.IconPath = Join-Path $install 'identity\claude-b.ico'
    & (Join-Path $scripts 'Install-ClaudeIdentity.ps1') @fromInstalled -Apply | Out-Null
    Assert-Equal 'reinstall from the installed icon works' $true (Test-Path -LiteralPath $shortcut)

    # A user-edited installed file is not silently overwritten.
    $edited = Join-Path $install 'identity\Launch-Claude.ps1'
    Add-Content -LiteralPath $edited -Value '# user edit'
    $manifestText = Get-Content -LiteralPath (Join-Path $install 'identity\identity.json') -Raw
    Assert-Equal 'manifest records the original hash, not the edit' $false ($manifestText -match (Get-FileHash -LiteralPath $edited -Algorithm SHA256).Hash)
    Assert-Failure 'user-edited installed file is refused' {
        & (Join-Path $scripts 'Install-ClaudeIdentity.ps1') @common -Apply
    } 'is not owned by this tool'
} finally {
    if ($child) { Stop-Process -Id $child.Id -Force -ErrorAction SilentlyContinue }
}

try {
    # Foreign shortcut with the same name is refused.
    $folder2 = Join-Path $root 'Desktop2'; $null = New-Item -ItemType Directory -Path $folder2
    $wsh = New-Object -ComObject WScript.Shell
    $foreign = $wsh.CreateShortcut((Join-Path $folder2 'Claude (B).lnk')); $foreign.TargetPath = (Join-Path $env:SystemRoot 'System32\notepad.exe'); $foreign.Description = 'mine'; $foreign.Save()
    Assert-Failure 'foreign shortcut is refused' {
        & (Join-Path $scripts 'Install-ClaudeIdentity.ps1') -ProfileDir 'C:\Fixture\Claude-B' -IconPath (Join-Path $root 'test.ico') `
            -InstallDir (Join-Path $root 'Other') -ShortcutFolder $folder2 -Apply
    } 'not owned by this tool'
    Assert-Equal 'foreign shortcut untouched' 'mine' $wsh.CreateShortcut((Join-Path $folder2 'Claude (B).lnk')).Description
    Assert-Failure 'relative profile dir is refused' {
        & (Join-Path $scripts 'Install-ClaudeIdentity.ps1') -ProfileDir 'Claude-B' -IconPath (Join-Path $root 'test.ico') -InstallDir (Join-Path $root 'Other')
    } 'absolute'
    Assert-Failure 'non-ico is refused' {
        & (Join-Path $scripts 'Install-ClaudeIdentity.ps1') -ProfileDir 'C:\Fixture\Claude-B' -IconPath (Join-Path $scripts 'launch-identity.vbs') -InstallDir (Join-Path $root 'Other')
    } '\.ico'

    # Remove deletes exactly what was created.
    $install = Join-Path $root 'ClaudeProfiles'; $folder = Join-Path $root 'Desktop'
    $removeArgs = @{ Name = 'B'; InstallDir = $install; ShortcutFolder = $folder }
    $cleanInstall = Join-Path $root 'Clean'; $cleanDesktop = Join-Path $root 'CleanDesktop'
    $clean = @{ Name = 'B'; ProfileDir = 'C:\Fixture\Claude-B'; IconPath = (Join-Path $root 'test.ico'); InstallDir = $cleanInstall; ShortcutFolder = $cleanDesktop }
    & (Join-Path $scripts 'Install-ClaudeIdentity.ps1') @clean -Apply | Out-Null
    & (Join-Path $scripts 'Install-ClaudeIdentity.ps1') -Name B -InstallDir $cleanInstall -ShortcutFolder $cleanDesktop -Remove | Out-Null
    Assert-Equal 'remove preview keeps files' $true (Test-Path -LiteralPath (Join-Path $cleanDesktop 'Claude (B).lnk'))
    & (Join-Path $scripts 'Install-ClaudeIdentity.ps1') -Name B -InstallDir $cleanInstall -ShortcutFolder $cleanDesktop -Remove -Apply | Out-Null
    Assert-Equal 'remove deletes the shortcut' $false (Test-Path -LiteralPath (Join-Path $cleanDesktop 'Claude (B).lnk'))
    Assert-Equal 'remove deletes the identity folder' $false (Test-Path -LiteralPath (Join-Path $cleanInstall 'identity'))
    Assert-Equal 'remove keeps the parent folder' $true (Test-Path -LiteralPath $cleanInstall)
    Write-Host "PASS: $script:assertions identity assertions; no Claude process, profile or real shortcut folder touched."
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
