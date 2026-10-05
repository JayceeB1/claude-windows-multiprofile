# Shared workspace fork - implementation ledger

## Contract

Two Claude Desktop accounts with separate Desktop data directories and separate
Claude Code config roots. Both accounts work in the same existing local project
folders and share explicitly selected project memory. One agent writes to a
project at a time, managed by the user. No worktree requirement.

Do not share/copy credentials, cookies, complete config roots, internal Desktop
stores, or cloud conversations. No automatic account/quota rotation. Preserve
upstream licensing; do not modify or redistribute Claude binaries.

### Existing session preservation - mandatory acceptance gate

The user explicitly confirmed on 2026-10-05 that a working session already
exists. Treat that session as account A, to preserve in place, NOT as a disposable
test profile or a fresh login. The exact local paths and effective configuration
have not been inspected on the user's machine. These are requirements to
implement and qualify, not protections already proven by the current code.

- Start with a read-only inventory of paths/config provenance and existing
  launcher/routing metadata. Do not read, print, upload or clone auth tokens,
  cookies or session databases. Do not assume A uses the stock data/config paths:
  an existing custom CLAUDE_CONFIG_DIR must not be silently replaced by the
  launcher's omitted/empty ConfigDir behavior. Ambiguity blocks configuration.
- Keep A's data/config roots, conversations, projects and existing entry point
  in place. No move, rename, reset, forced logout, account replacement or forced
  process termination. Any needed orderly restart must be explicitly agreed,
  after active work is saved; it is not a logout or a migration.
- Add B using newly provisioned, distinct data/config roots. Refuse a collision
  with any existing profile instead of adopting/overwriting it. Use explicit
  labels identifying A as the existing session and B as the added account.
  No whole-root links/copies, including through junctions or symlink aliases.
- Share only selected project resources/memory after isolated tests. No blanket
  rewrite of A's settings or memory. Each intended non-secret settings change
  needs a preview, local backup and conflict-aware rollback. Do not introduce
  shared memory inside a directory that B's uninstall is allowed to remove.
- Login callbacks must have an unambiguous intended target; never silently send
  B's callback to A as a fallback. Changes to existing protocol registration or
  shortcuts require explicit approval, an ownership record and safe restoration.
- Install/uninstall/rollback must preserve A and shared resources, including
  when paths alias or nest. Delete only demonstrably owned additions, never a
  pre-existing directory inferred from its name. Check conflicts before restore.
- Qualification must show A remains usable before/after adding B and after
  removal of B, including a user-approved restart where needed. Confirm the
  effective accounts A/B locally without exporting secrets. Do not interpret
  this as a guarantee against independent provider-side session expiry.

## Work rules

One coherent micro-slice, 2-4 files, self-review, tests, atomic commit, draft PR,
then STOP. No merge without explicit approval. Keep files below approximately
500 lines. Use the connected user's Git identity; do not copy upstream's author
or add assistant/co-author attribution. Keep master unchanged until approval.

## S2a - installer parameter collision

Base: `2ee03050185ace47581e9607341bd91cddd5ae9a` (upstream/fork master).
Branch: `fix/setup-profile-path-collision` (fork has no develop branch).

`Setup.ps1` reused `$dataDir` / `$configDir` for paths while `$DataDir` /
`$ConfigDir` are typed hashtable parameters. PowerShell variable names ignore
case. Assigning a path therefore attempts to replace a hashtable parameter.
The fix renames only the per-profile values to `$profileDataDir` /
`$profileConfigDir`. Public parameters, overrides, manifest keys, shortcuts,
stock-profile behavior and router registration remain unchanged.

`tests/Test-SetupProfiles.ps1` parses the real installer, extracts its parameter
block and profile loop, and runs only those fragments with in-memory directory
and shortcut doubles. It never invokes Setup.ps1 as an installer. It covers
stock-first/last, both isolated defaults, independent/partial overrides,
case-insensitive map keys, explicit empty config, map preservation, repeat
invocation, and ordinary/sign-in shortcut arguments including spaces.
The pinned original must fail specifically on hashtable conversion. Separate
DataDir and ConfigDir mutants must fail as well: an arbitrary exception is not
a passing negative test.

CI parses every PowerShell script before executing tests and runs the profile
suite plus the existing argument-builder suite on Windows PowerShell 5.1 and
PowerShell 7. The existing PSScriptAnalyzer job remains enabled.

### Evidence boundaries

The publication environment has Python but no PowerShell/Windows runtime and
cannot clone GitHub directly. Source was read through the GitHub connector;
local reconstruction of Setup.ps1 was verified against its exact Git blob SHA
`3f713a77ca90cbd1456d9b9a215970f9b0ea08ef` before editing. Static review and
source-diff checks are not a runtime PASS. CI run links and actual results belong
in the draft PR after execution. A workflow definition is not proof of a run.

No installation, login, MSIX resolution, real shortcut creation, Desktop memory
sharing or user-machine qualification is claimed by this slice.

## S2b - explicit child configuration and quoted launch paths

Parent: `973fc1550ec3d1ca0f2c1f9ab474972f4ade3ce5`; same branch and draft PR #1.
Four files in this slice: launcher, launcher tests, CI, and this ledger.

`Launch-Claude.ps1` builds a .NET `ProcessStartInfo` using `UseShellExecute=false`
and an independently materialized child environment. An explicit `ConfigDir`
sets only the child's `CLAUDE_CONFIG_DIR`; omitted/empty removes that variable
from the child and selects stock behavior. The caller's process/user/machine
settings are never mutated. Other inherited variables are intentionally left
unchanged; this is config-path isolation, not proof of effective account identity.

Paths are validated before discovery or writes. The profile is one quoted
argument; trailing backslashes are doubled before the closing quote. Directory
creation uses literal .NET paths. Dot-sourcing is inert. Discovery/creation/start
failures propagate; no start follows a failed prerequisite. Successful directory
creation is not rolled back if a later step fails (avoid deleting existing data).

Tests exercise the real start-info builder and launcher orchestration using
in-memory OS-boundary doubles: spaces/brackets/Unicode/UNC/trailing separators,
A/B/stock configs, parent preservation, independent child copies, invalid input,
MSIX selection/fallback/missing app, and failures at discovery/creation/start.
No Desktop, process or real directory is created by the tests. CI runs the new
suite after parser preflight in both existing Windows shell jobs. Runtime results
must be recorded in PR #1 from actual logs, not inferred from this implementation.
The publication environment still has no PowerShell and cannot clone GitHub.
The three baseline files were verified against their exact Git blob hashes.

### Known boundaries after source review

`Arm-ClaudeLogin.ps1 -Launch` already forwards the recorded config into this
launcher. However, `ClaudeOpenShim.ps1` starts the executable directly and does
not read that config: a callback that cold-starts a profile can bypass S2b.
Therefore the whole login chain remains UNQUALIFIED until S2c fixes/tests it.
An existing Desktop instance retains its old environment: exit that profile
fully and reopen after a config change. Do not claim that refocusing fixes it.
No API/provider credential variables are changed or logged; check effective
account identity in the later real-machine gate. No memory bridge integration.

### References checked for this design

- Microsoft: [child environment and UseShellExecute](https://learn.microsoft.com/en-us/dotnet/api/system.diagnostics.processstartinfo.environmentvariables?view=netframework-4.8.1).
- Microsoft: [Windows argument quoting](https://learn.microsoft.com/en-us/cpp/c-language/parsing-c-command-line-arguments?view=msvc-170).
- Anthropic: [per-account config directories](https://code.claude.com/docs/en/authentication#log-in-with-multiple-accounts).

## Prior prototype

The earlier `claude-shared-memory-slice1.zip` contains a standalone Python memory
bridge and 40 previously reported Linux tests. It is NOT integrated in this
commit. Re-review it and rerun its tests before importing it; do not turn the
previous report into a Windows/Desktop claim.

## Next slices / known debt

1. S2b: implementation added above; close only against actual CI evidence.
   S2a: PowerShell 7 previously PASS; the other two jobs were still queued
   when this slice started. Do not infer a complete S2a PASS.
2. S2c: harden login routing. `ClaudeOpenShim.ps1` currently logs complete OAuth
   callback URLs (also on failure); never publish those logs. Remove token-bearing
   URLs from logging and qualify routing/env behavior before real account tests.
3. S3: import/revalidate the Python memory bridge, then integrate explicit
   project-memory sharing without merging profile config roots. Check current
   `autoMemoryDirectory` support and actual Desktop loading before adoption.
4. S4: one-command packaging, reversible changes, safe handling of existing
   profiles, and protection of shared memory during uninstall. The upstream
   `Uninstall.ps1 -RemoveData` is not yet qualified for shared paths.
5. S5: user-machine qualification on a disposable project: verify accounts A/B,
   memory A -> B and B -> A, restart, and rollback. Session history/cloud memory
   and simultaneous Cowork VMs remain out of scope.

NEXT: read current CI evidence and STOP. Next code slice is S2c: remove OAuth
URLs from logs and propagate profile config through the callback route. No real
account test or memory migration until those paths and uninstall are qualified.
