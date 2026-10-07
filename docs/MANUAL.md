# Manual: Claude Desktop with two accounts (A and B)

This page says what to click, where everything lives, and what to do after a Claude update or when an account asks you
to sign in again. Nothing here requires typing a command in daily use. A French version is in
[fr/MODE-OPERATOIRE.md](fr/MODE-OPERATOIRE.md).

Account **A** is the one you already use. Account **B** is the second one this project adds.

## 1. Daily use: two shortcuts

On the **Desktop**:

| Shortcut | Account | Icon |
| --- | --- | --- |
| **Claude (A existing)** | A, your original account | the normal Claude icon |
| **Claude (B)** | B, the second account | your own icon for B |

- Both windows can run at the same time, each with **its own taskbar button**.
- **Pin "Claude (B)" once**: right-click the Desktop shortcut, "Pin to taskbar". Afterwards start B from the taskbar.
- Never pin the button of an already open window: Windows then creates a generic pin with the original icon. If that
  happens, unpin it and pin the Desktop shortcut instead.
- The older shortcut **"Claude (B added)"** still works but has neither the B icon nor its own button. Keep it: the base
  installation watches it.

In the **"Claude multi-comptes"** Desktop folder (created by `Install-ClaudeTools.ps1`; the shortcut names are French):

| Shortcut | When to use it |
| --- | --- |
| **Réparer Claude (A+B)** | After a Claude update, or when something looks wrong (icon came back, sharing broken) |
| **Reconnecter B** | When account B asks you to sign in again |
| **Mode opératoire** | The manual (French version) |

## 2. Where things are

The paths below are the defaults. `%USERPROFILE%` is your user folder (`C:\Users\<you>`); if you chose other folders at
installation, use those.

| Item | Location |
| --- | --- |
| Shortcuts | `%USERPROFILE%\Desktop\` and `%USERPROFILE%\Desktop\Claude multi-comptes\` |
| Base launcher (do not edit) | `%USERPROFILE%\ClaudeProfiles\bin\` |
| B's taskbar identity and icon | `%USERPROFILE%\ClaudeProfiles\identity\` (`identity.json` records what was installed) |
| Shared-config journal and backups | `%USERPROFILE%\ClaudeProfiles\shared-config\` |
| Last version seen in good state | `%USERPROFILE%\ClaudeProfiles\repair-state.json` |
| Desktop A data (login) | `%APPDATA%\Claude\` |
| Desktop B data (login) | `%APPDATA%\Claude-B\` |
| Claude Code config of A | `%USERPROFILE%\.claude\` |
| Claude Code config of B | `%USERPROFILE%\.claude-b\` |
| These tools | the folder where you cloned this repository ("the repository" below) |
| The Claude application | managed by Windows, `C:\Program Files\WindowsApps\Claude_<version>_...`; leave it alone |

The two **logins** live in `%APPDATA%\Claude` and `%APPDATA%\Claude-B`. That is what keeps both accounts signed in from
one day to the next.

## 3. What A and B share, and what they never share

**Shared live** (what one does is seen by the other): skills, agents, plugins, mods, **projects with their memory**, your
global `CLAUDE.md`, your settings (`settings.json`) and the Desktop MCP configuration. Your project folders are the same
on disk anyway. The **Claude Code session list** (the "Recents" sidebar of the Code tab, with its projects) is shared too:
a session started in A appears in B and the other way round, and can be resumed from either account (for example when one
account hit its limit). Open a given session in one window at a time.

**Interface mods** (panels, the band above the prompt, the status line, commands) follow two mechanisms already in place:
their folders (`mods`, `dev-mods`) are linked, and the list of mods to load (`CLAUDE_CODE_PLUGIN_DIRS` in the `env` block
of `settings.json`) is read by B through the same `settings.json`. A mod added in A and declared in that list therefore
appears in B at the start of its next session; a plugin installed through the plugin system (`enabledPlugins`) follows the
same path. Still per session: the "Enable hot reloading for this session?" question, and development mods in progress
(one folder per session in `dev-mods`). To check in B, open a Code session and look for the mod's panel or band; otherwise
type `/reload-plugins`.

**Copied once**: the list of your user-level MCP servers (read from `%USERPROFILE%\.claude.json`, copied into
`%USERPROFILE%\.claude-b\.claude.json`). If you add one in A later, run "Réparer"; if B already has a different list,
the repair leaves it as is and tells you (see troubleshooting).

**Never shared, for safety**: the login, tokens, credentials, account identity, cookies, and each account's **claude.ai chat
conversations** (they are stored on Anthropic's servers under your account and nothing can merge them). Only the **local
Claude Code sessions** are shared. Claude Code scheduled tasks live in the same folder as the sessions, so they are common
to both accounts: if you create some, avoid opening A and B at the same time at the scheduled moment.

## 4. After a Claude update

**What happens.** Windows installs the new version in a new folder. Nothing in these tools contains the application path:
everything finds it again at each launch. Your logins are in `AppData`, which an update does not touch. Most of the time
there is **nothing to do**.

**After each update, in 30 seconds:**

1. Close both Claude windows (windows already open keep the old version).
2. Double-click **"Réparer Claude (A+B)"**.
3. Read the lines. Everything should say **OK** (or **RÉPARÉ**, which is fine too). Press Enter to close.
4. Start A and B from their shortcuts.

**What the repair checks, and fixes by itself when it can:**

| Check | Automatic fix |
| --- | --- |
| Claude version, update detected | information only |
| A registered session for A and for B | no: use "Reconnecter B" |
| B's shortcut, icon and separate button | yes, reinstalled identically |
| Login router in the real registry | yes |
| Shared-config links | yes (B must be closed); a file replaced by a plain copy is backed up, then linked again |
| Base installation receipt (only needed to remove or restore B natively) | yes, with B closed: B's folder identity is re-recorded (journal, validation, rollback if it fails) |
| Which application receives `claude://` links | no: set in Windows |

An update can replace B's `claude_desktop_config.json` with an ordinary copy, silently breaking the sharing of that one
file. "Réparer" detects it and restores the link after setting the old file aside in `ClaudeProfiles\shared-config\backups`.

The repair **does not run by itself**: you start it with a double-click. Nothing is scheduled in the background.

## 5. When an account asks you to sign in again

This can happen after an update, a long absence or a password change. These tools cannot prevent it, but they guide the
sign-in. The cause comes from Claude, not from this setup; a clean sign-in fixes it.

### Account A

1. Check that `claude://` links go to **Claude** (normal state; "Réparer" shows it).
2. Open **Claude (A existing)**, click sign in, finish in the browser.

### Account B: double-click "Reconnecter B"

The script does everything except one click Windows reserves for you.

1. In the browser, **open a private window** and sign in to claude.ai with account B. Close other Claude sign-in tabs.
2. **Step 1**: Settings opens. Search "claude", click "CLAUDE", choose **Claude Login Router**, then "Set default". The
   script waits for that choice.
3. **Step 2**: B opens. Click sign in, **check in the browser that it is really account B**, authorize. You have 5 minutes.
   The script notices that B's stored login changed (only a hash is compared; nothing secret is read).
4. **Step 3**: in the same Settings window, set **Claude** back ("CLAUDE", "Claude", "Set default"). The script notices
   the return to normal.

Good to know:
- Do **one sign-in at a time** and close old sign-in tabs before starting again.
- If window **A** reacts instead of B, stop, run nothing else, and report it.
- If you forget step 3, the router stays the default and a future sign-in of A is refused for safety: "Réparer" shows it
  (router active).

## 6. Installing from scratch

Do this once, from a PowerShell opened **from the Start menu** (not from Codex nor Claude Desktop: those programs redirect
their writes and the tools refuse to run there). In the repository folder:

1. The base launcher and the router: see the [technical reference](reference/SHARED-WORKSPACE.md) and the
   [routing guide](PROTOCOL-ROUTING.md). This step is preview-first and needs a private specification file.
2. B's icon and separate button (preview without `-Apply`, then with it; supply your own `.ico`, none is shipped):
   ```powershell
   .\scripts\Install-ClaudeIdentity.ps1 -Name B -ProfileDir "$env:APPDATA\Claude-B" -ConfigDir "$env:USERPROFILE\.claude-b" -IconPath C:\path\claude-b.ico -Apply
   ```
3. The tool shortcuts (the "Claude multi-comptes" folder):
   ```powershell
   .\scripts\Install-ClaudeTools.ps1 -Apply
   ```
4. Sharing the configuration, with B closed (preview, then apply):
   ```powershell
   python -B scripts\Link-SharedConfig.py
   python -B scripts\Link-SharedConfig.py --apply --approved --replace-files
   ```
   Or simply double-click "Réparer Claude (A+B)", which does the same.

## 7. Rolling back

Each step is undone without touching your logins or your projects:

```powershell
python -B scripts\Link-SharedConfig.py --rollback --approved      # B closed: removes the links, restores the previous state
.\scripts\Install-ClaudeIdentity.ps1 -Name B -Remove -Apply        # removes B's shortcut and separate button
.\scripts\Install-ClaudeTools.ps1 -Remove -Apply                   # removes the "Claude multi-comptes" folder
```

Removing a link never deletes what it points to: A's files stay intact.

## 8. Troubleshooting

| Symptom | Probable cause | What to do |
| --- | --- | --- |
| Both windows under one button, original icon | B was started without "Claude (B)" | Close B, start it with "Claude (B)" |
| The original icon comes back on B's button | Generic pin made from an open button | Unpin it, pin the Desktop **shortcut** |
| "Réparer" shows **BLOQUÉ** for sharing | B is open | Close B, run "Réparer" again |
| "Réparer" says it was started from Codex or Claude Desktop | The tools refuse to run in those programs | Use the Desktop shortcut |
| `TARGET_MCP_SERVERS_DIFFER...` for MCP servers | B already has a list different from A's | `python -B scripts\Link-SharedConfig.py --apply --approved --replace-mcp` (B closed) |
| "Login router: absent from the registry" | Router must be registered again | "Réparer" does it |
| The router is not in Settings | Registry must be registered again | "Réparer", then reopen Settings |
| B is not signed in | Session missing or expired | "Reconnecter B" |
| "Installation receipt: to reconcile" | The base receipt still records an old location of B's folder | "Réparer" with B closed: fixed, the line turns OK |
| A window stayed on the old version | Window opened before the update | Close it and start it again |

## 9. Golden rules

- One account per window: start A with A's shortcut, B with B's.
- Start the tools from a Desktop shortcut or from a PowerShell opened from the Start menu.
- Do not edit `ClaudeProfiles\bin` nor B's `claude_desktop_config.json` by hand: they are links.
- Close B before touching the sharing or the links.
- One sign-in at a time, and always check the account shown in the browser before authorizing.
