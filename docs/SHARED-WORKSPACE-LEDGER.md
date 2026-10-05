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

## S2c1 - callback-safe logging and failure reporting

Parent: `3546ddb2face6a5f4e922d46a73c268f817928c6`; same branch and draft PR #1.
Four files: shim, synthetic logging tests, CI, ledger. No installation or change
to the existing session A, its profile paths, shortcuts or protocol registration.

`route.log` now records only timestamp, allowlisted event code, and target kind
(`unknown`, `stock`, `profile`). No URL/query/fragment, target path, arguments or
raw exception is interpolated, even on MSIX lookup, process start or IO failures.
The full callback is still forwarded unchanged to Claude. `LAUNCH_REQUESTED`
means dispatch was attempted; `DISPATCH_COMPLETE` means launch and marker reset
returned successfully, NOT that authentication succeeded.

All dispatch failures return status 1, propagated by the entry point. Failures
before dispatch cannot start a process. A failed log write cannot print its raw
exception or recursively log elsewhere. Failure of the pre-dispatch log blocks
launch. Post-launch reset/log failures return failure without retrying or killing
the app. The tests capture all explicit PowerShell streams and fake log writes;
they verify exact event sequences, full callback forwarding and process/reset
counts. Synthetic query/fragment/custom-field/path sentinels and raw exception
messages cover success, missing input/app/marker, discovery, read, builder,
launch, reset and log-write failures. Both throw and nonterminating Write-Error
are exercised. A strict closed-schema guard also rejects deliberate fake leaks.

### Limits and next gate

Only NEW shim log entries and explicit dispatch output are covered. Historical
logs are neither read nor deleted. Windows command-line telemetry, PowerShell
transcription/debugging and in-memory error records, and Claude's own logs are
not sanitized by this patch. The callback necessarily remains in launch args.
Do not publish an old route.log. The existing protocol document's examples with
`target <- URL` describe the OLD format, not the patched log; this section is the
current contract until that guide is refreshed with the routing slice.

Routing/default selection and the post-launch marker reset ordering are retained,
not qualified. Cold-start profile config propagation, ambiguous-target fallback,
marker races and safe behavior for existing session A still block real logins.
S2c2 must address these before adoption; this slice does not claim account safety
or shared-memory functionality. No whole profile or credential is copied.

### Evidence

At slice entry, run #3 (`37368772382`, code `f6ea7a9`) had its Windows PowerShell
job completed successfully; the pwsh/lint jobs were cancelled. Run #4 at the
parent was still queued. Do not infer a full cross-shell qualification.
CI includes the new suite after parser preflight in both Windows jobs. Read the
new commit's results before claiming runtime PASS. No local Windows/PowerShell
runtime is available; local source/YAML checks are not runtime proof.

References checked: [OWASP logging exclusions](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude)
and [PowerShell terminating-error handling](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_try_catch_finally?view=powershell-7.5).

## Prior prototype

The earlier `claude-shared-memory-slice1.zip` contains a standalone Python memory
bridge and 40 previously reported Linux tests. It is NOT integrated in this
commit. Re-review it and rerun its tests before importing it; do not turn the
previous report into a Windows/Desktop claim.

## Next slices / known debt

1. S2a/S2b: recheck cross-shell CI at the current HEAD; evidence above.
2. S2c1: new log/output contract above; close only against current CI evidence.
   S2c2: propagate config through callbacks and fail closed on ambiguous targets,
   including the existing session A. Qualify arming/reset behavior without logins.
3. S3: import/revalidate the Python memory bridge, then integrate explicit
   project-memory sharing without merging profile config roots. Check current
   `autoMemoryDirectory` support and actual Desktop loading before adoption.
4. S4: one-command packaging, reversible changes, safe handling of existing
   profiles, and protection of shared memory during uninstall. The upstream
   `Uninstall.ps1 -RemoveData` is not yet qualified for shared paths.
5. S5: user-machine qualification on a disposable project: verify accounts A/B,
   memory A -> B and B -> A, restart, and rollback. Session history/cloud memory
   and simultaneous Cowork VMs remain out of scope.

NEXT: read current CI evidence and STOP. Then S2c2 only: profile config and
unambiguous callback routing, preserving session A. No real account test or memory
migration until routing and uninstall are qualified. No merge without approval.
