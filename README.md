# Claude Desktop multi-account (Windows)

Run **two Claude Desktop accounts side by side** on Windows, each with its own login and its own taskbar button, while
sharing the same skills, plugins, mods, project memory, settings and Claude Code sessions.

> **Unofficial and experimental.** This project is not affiliated with, endorsed by or sponsored by Anthropic.
> "Claude" is a trademark of Anthropic. It does not modify, repackage or redistribute the Claude application, and it
> ships no Claude artwork: you supply your own icon for the second account.

## What you get

- **Two accounts at once.** The official, unmodified Claude Desktop is launched twice with distinct Chromium
  `--user-data-dir` folders, so each window keeps its own login.
- **A separate taskbar button and icon for account B**, using only documented shell properties (an explicit
  AppUserModelID and `WM_SETICON` set from a separate hidden process; nothing is injected into Claude).
- **The same setup in both accounts.** Skills, agents, plugins, mods, project memory, `CLAUDE.md`, settings, the Desktop
  MCP configuration and the local Claude Code session list are linked with directory junctions and file symlinks.
  Credentials, tokens and account identity are never linked or copied (asserted by a test).
- **Check and repair after a Claude update**, and a **guided re-login** of account B, as desktop shortcuts: no command
  to type in daily use.
- **A login router** so a `claude://` sign-in callback reaches the intended account, with no fallback to a guessed one.

claude.ai chat history stays with each account: it lives on Anthropic's servers and nothing here can merge it.

## Requirements

- Windows 11 (developed and tested on 11 Pro) with the official Claude Desktop installed from the Microsoft Store/MSIX.
- Python 3.12 or newer (a real runtime, not the Store alias), standard library only.
- Windows **Developer Mode** on, for file symlinks. Directory junctions need no admin right.
- PowerShell 5.1 or 7. No administrator elevation is needed anywhere.

## Status

Version `0.1.0`, experimental. Validated on one real machine with two accounts: both windows run together, B has its own
button, sharing works, repair is idempotent, the router shows up in the Windows `claude://` picker. Not yet exercised on
real hardware: a **real Claude update** and a **real guided re-login**; both procedures are covered by fixtures only. The
full list of open items is in the [ledger](docs/dev-log/SHARED-WORKSPACE-LEDGER.md).

## Where to start

| You want to | Read |
| --- | --- |
| Use it day to day, repair after an update, log B in again | [Manual](docs/MANUAL.md) · [version française](docs/fr/MODE-OPERATOIRE.md) |
| Install it | `scripts\Install-ClaudeMultiAccount.ps1`, see [Manual, "Installing from scratch"](docs/MANUAL.md#6-installing-from-scratch) |
| Understand the design and the safety rules | [Technical reference](docs/reference/SHARED-WORKSPACE.md) · [login routing](docs/PROTOCOL-ROUTING.md) |
| Check what was tested and how | [Manual acceptance](MANUAL-TEST.md) · [development log](docs/dev-log/) |
| Contribute | [CONTRIBUTING](CONTRIBUTING.md) · [CLAUDE.md](CLAUDE.md) for AI assistants |

## How it works, in short

1. The launcher resolves the installed MSIX executable through `Get-AppxPackage` at every start (the versioned folder
   changes on each update, so no path is hard-coded) and starts it with a distinct `--user-data-dir`.
2. A second launcher gives profile B its own AppUserModelID and icon. Pin its shortcut, never a running window's button.
3. `scripts/Link-SharedConfig.py` links the shared configuration of B to A's. It previews by default, records a journal,
   backs up what it replaces, can roll back, and removing a link never follows it.
4. `scripts/Repair-ClaudeProfiles.ps1` compares the package version with the last known good state, checks each login
   (presence only), the identity launcher, the router registration and the links, and repairs only what this project owns.
5. Windows virtualizes registry and AppData writes made by packaged apps and by **all their descendants**, in a private
   store that Windows Settings never reads. The tools therefore refuse to write from inside such a process tree; run them
   from a shortcut or from a PowerShell opened from the Start menu.

Every mutating command is preview-first and needs explicit approval flags. Nothing logs out an account, migrates a
profile, uninstalls the official package or chooses your default app for you.

## Tests

```powershell
python -B tests/Run-SharedWorkspaceTests.py
powershell -NoProfile -File tests\Test-ClaudeRepair.ps1
powershell -NoProfile -File tests\Test-ClaudeInstall.ps1
powershell -NoProfile -File tests\Test-ClaudeIdentity.ps1   # needs an interactive desktop
```

CI runs PSScriptAnalyzer and the fixture matrix on Windows PowerShell 5.1 and PowerShell 7. The tests use synthetic
accounts and owned temporary folders; they do not start Claude. Run the Python suite from a normal shell: three
subprocess-entry tests skip inside a packaged process tree, by design.

## Credits and license

This project is a fork and builds on the work of others (see [NOTICE](NOTICE.md) for the full lineage):

- [vodongha/claude-desktop-clone](https://github.com/vodongha/claude-desktop-clone), the original launcher (MIT).
- [fredless/claude-windows-multiprofile](https://github.com/fredless/claude-windows-multiprofile) by **Fred Nielsen**: the `claude://` login-routing design and first implementation that this project's router is built on, and the profile contract behind Setup/Uninstall. Thank you, Fred.
- [Zoltak-Dev/ai-multi-instance](https://github.com/Zoltak-Dev/ai-multi-instance), origin of the `--user-data-dir`
  technique and of the prior UserChoice-hash work (this project does not implement UserChoice-hash automation).
- [sypnose-cloud/claude-desktop-multi](https://github.com/sypnose-cloud/claude-desktop-multi), prior art on running
  several instances.

Everyone who contributed is listed in [AUTHORS](AUTHORS.md). Released under the [MIT License](LICENSE).
