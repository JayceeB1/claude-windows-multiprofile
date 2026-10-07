# CLAUDE.md

Guidance for Claude Code (or any AI assistant) working in this repository.

## What this project is

**Claude Desktop multi-account (Windows)**: run several isolated instances of the official Claude Desktop app, one per
account, side by side, sharing configuration and Claude Code sessions through links. It never modifies or repackages the
Claude app: it launches the officially installed MSIX app with Chromium's `--user-data-dir`, and adds a separate taskbar
identity, shared-config links, update repair and a guided re-login around it. See [NOTICE.md](NOTICE.md) for the lineage
(vodongha, fredless, Zoltak-Dev); keep those credits and the MIT notices intact.

## Core mechanism (do not break this)

1. **Resolve the exe dynamically.** The app is an MSIX package at
   `C:\Program Files\WindowsApps\Claude_<version>_x64__<hash>\app\Claude.exe`. The version segment changes on every update
   and that folder is permission-restricted. Resolve it with `Get-AppxPackage -Name '*Claude*'` and `.InstallLocation`;
   fall back to a `WindowsApps\Claude_*__*\app\Claude.exe` glob only if the Appx query fails. **Never hard-code the
   versioned path.**
2. **Isolation = a distinct `--user-data-dir`.** Two shortcuts, two data directories. Never share one: that re-merges the
   accounts.
3. **Launch the exe directly**, not through MSIX shell activation, which does not reliably forward `--user-data-dir`.
4. **Icons point at a stable path**, never at the versioned exe (`Setup.ps1` extracts one into `bin\claude.ico`; write a
   32-bit PNG-based `.ico` by hand, never `Icon.Save()`, which drops the colour plane). The repository ships no Claude
   artwork; the user supplies B's icon.
5. **`CLAUDE_CONFIG_DIR` is optional and additive.** It isolates Claude Code's `~/.claude` store per profile; omitting it
   keeps the shared default. Do not make it mandatory or hard-code a path.

## Layout

```
scripts/
  Launch-Claude.ps1, launch.vbs, Setup.ps1, Uninstall.ps1, Build-Exe.ps1   # base launcher (legacy parameters are blocked)
  Set-ClaudeWindowIdentity.ps1, Launch-ClaudeIdentity.ps1, launch-identity.vbs, Install-ClaudeIdentity.ps1
                      # separate taskbar button + icon for one profile (explicit AppUserModelID + WM_SETICON from a hidden watcher)
  Repair-ClaudeProfiles.ps1, Connect-ClaudeProfile.ps1, Install-ClaudeTools.ps1
                      # check and repair after an update, guided re-login of B, desktop shortcuts
  Link-SharedConfig.py  # junction/symlink sharing of config between profiles; never credentials or identity
  Arm-ClaudeLogin.ps1, ClaudeOpenShim.ps1, ClaudeLoginRouter.cs, Apply-RouterRegistration.py   # claude:// login router
  SharedWorkspace*.py, SharedMemory*.py, NativeWorkspace.py, NativeWindowsIO.py, Inspect-SharedWorkspace.py
                      # preview-first shared workspace, ownership receipt, native Windows IO
tests/                # Python and PowerShell fixture suites (synthetic accounts, owned TEMP folders)
docs/MANUAL.md, docs/fr/MODE-OPERATOIRE.md   # operator manuals (English, French)
docs/reference/       # technical reference; docs/PROTOCOL-ROUTING.md is the routing contract
docs/dev-log/         # dated reports, ledger, roadmap, qualification receipts (history, not user documentation)
```

## Gotchas learned the hard way

- **MSIX virtualization.** HKCU and AppData writes made by a packaged process (Codex, Claude Desktop) and by *all its
  descendants* are redirected to a private per-package store that Windows Settings never reads. Descendants report no
  package identity themselves, so `NativeWindowsIO.require_unpackaged_process()` walks the ancestor chain. Native writes and
  the Python helpers must run from a normal shell or a shortcut; from inside Claude Code they refuse by design, and three
  subprocess-entry tests skip with an explicit reason. Run `tests/Run-SharedWorkspaceTests.py` from a normal shell.
- **PowerShell 5.1 and accents.** Scripts containing non-ASCII text must be saved as UTF-8 **with BOM**, otherwise 5.1
  reads them as ANSI and mangles text and shortcut names. Native stderr inside `$ErrorActionPreference = 'Stop'` aborts
  5.1: wrap native calls with a local `Continue`. Under strict mode, read optional JSON properties through a helper.
- **Pinning.** Pinning a running window's button creates a generic pin with the app icon. Pin the shortcut created by
  `Install-ClaudeIdentity.ps1`. A pinned shortcut owns the button only if its AppUserModelID equals the window's.
- **Links.** Directory junctions need no admin; file symlinks need Developer Mode. An atomic rename-write by an app breaks
  a file link silently (the repair re-links and keeps a backup). Removing a link never follows it.
- **Routing marker.** `bin\target.txt` is a v2 JSON record: only `armed` (or a legacy/unreadable file) blocks a native
  transition; `consumed` and `disarmed` are quiet.
- **Paths from the runner.** CI temp folders are 8.3 short names (`RUNNER~1`); compare canonical paths, never raw strings.
- **Editing.** Keep CRLF/BOM as the file already has them. When writing Windows paths through scripts, avoid escape
  sequences in the shell (`\f`, `\U`): prefer the Edit tool.

## Conventions

- **PowerShell** is the primary language for launching and repair; **Python 3.12+ (standard library only)** for the
  shared-workspace tooling. No dependencies are installed by any script.
- Everything runs **without admin rights**, is **idempotent**, and is **preview-first**: a mutating command needs explicit
  approval flags, records a journal, and can be rolled back.
- Resolve user paths from `$env:USERPROFILE`, `$env:APPDATA`, `[Environment]::GetFolderPath('Desktop')`; never hard-code
  `C:\Users\<name>` or a drive letter, and never commit personal paths. Machine-specific notes go in `*.local.md`, which
  is git-ignored.
- Never read, log, copy or print credentials, tokens or the contents of a login store; compare hashes only.
- Comment-based help (`.SYNOPSIS` / `.PARAMETER`) on every PowerShell script.

## Testing changes

```powershell
python -B tests/Run-SharedWorkspaceTests.py          # full Python qualification (fixtures, TEMP only)
powershell -NoProfile -File tests\Test-ClaudeRepair.ps1
powershell -NoProfile -File tests\Test-ClaudeIdentity.ps1   # interactive desktop required
```

To check a real launch by hand, start a profile and confirm the flag reached the process:

```powershell
.\scripts\Launch-Claude.ps1 -ProfileDir "$env:TEMP\claude-test"
Get-CimInstance Win32_Process -Filter "Name='Claude.exe'" |
    Where-Object { $_.CommandLine -like '*claude-test*' } | Select-Object ProcessId, CommandLine
```

## Git workflow

- Single trunk: **`master`** is the stable branch and is never committed to directly. Work on `feature/*`, `fix/*`,
  `docs/*` or `chore/*` branches and merge by pull request with a merge commit (no squash, no rebase).
- CI (`ci.yml`) runs PSScriptAnalyzer and the fixture matrix on Windows PowerShell 5.1 and PowerShell 7; it must be green
  before merging.
- **No AI attribution** in commits or pull requests: no `Co-Authored-By` for an assistant, no "generated with" footer, no
  session link. Messages describe the change only.
- Releases are tagged `vX.Y.Z` with a `CHANGELOG.md` entry and an archive whose SHA-256 is published alongside it.

## Out of scope

- Codex or other apps (this project is Claude Desktop only).
- Modifying the Claude app's files, signing or repackaging it, or shipping Claude artwork.
- Anything requiring admin elevation.
- Merging claude.ai chat history between accounts (it lives on Anthropic's servers).
