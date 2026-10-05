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

User clarification for S4: project folders remain at their existing locations;
there is no planned move or project deletion. Local verification must confirm
that adding/removing B only affects its owned additions, not shared resources.

## Work rules

One coherent micro-slice, 2-4 files, self-review, tests, atomic commit, draft PR,
then STOP. No merge without explicit approval. Keep files below approximately
500 lines. Use the connected user's Git identity; do not copy upstream's author
or add assistant/co-author attribution. Keep master unchanged until approval.

## Published baseline

Branch: `fix/setup-profile-path-collision`; draft PR #1.
Master base: `2ee03050185ace47581e9607341bd91cddd5ae9a`.

| Slice | Commit | Evidence / scope |
| --- | --- | --- |
| S2a - installer map collision | `973fc1550ec3d1ca0f2c1f9ab474972f4ade3ce5` | Separate resolved path variables from case-insensitive hashtable parameters; unchanged public contract. |
| S2b - launcher | `f4ef9603188cdba7d28c876893bef8d820188521` | Child-only environment, quoted paths, validation before IO; no parent environment mutation. |
| S2b test repair | `f6ea7a99976427343f780f8c963fab63bdafac76` | Distinguish empty vs absent environment variable; no production change. |
| Existing A gate | `3546ddb2face6a5f4e922d46a73c268f817928c6` | Requirements above, not a machine qualification. |
| S2c1 - secret-free logs | `5c908a795af7ee44e287d8528f4af4ed1c0272ea` | Fixed event/category fields; no callback or raw exception in explicit outputs. |

[Run #5](https://github.com/JayceeB1/claude-windows-multiprofile/actions/runs/37372078960):
Windows PowerShell 5.1 job `111971465212` succeeded: 11 scripts parsed, 153 setup
assertions, 3 argument cases, 126 launcher assertions, 25 logging scenarios / 271
assertions. At S2c2 entry the pwsh and lint jobs were **cancelled without running**,
not passed. Earlier run #2 failed in the absent-environment test; #3 passed the
Windows PowerShell job. No complete cross-shell CI PASS has yet been observed.

## S2c2 - explicit callback routing and one-shot intent

Parent: `5c908a795af7ee44e287d8528f4af4ed1c0272ea`; same branch/PR, four files:
`ClaudeOpenShim.ps1`, `Arm-ClaudeLogin.ps1`, `Test-ShimLogging.ps1`, this ledger.
Existing CI already executes that test file in both Windows jobs after parsing.

- Arming resolves a declared profile in `profiles.json`. Data/config paths are
  explicit; no dispatch inference from `defaultProfile`, `isDefault`, or parent
  environment. A custom A config is preserved; empty config explicitly means
  stock behavior and strips the inherited variable. S4 must verify this mapping
  against the actual existing session before any real use.
- `target.txt` now contains a schema-v2 intent: named profile, hash of manifest
  text, creation/expiry timestamps (integer milliseconds, five-minute lifetime).
  Missing/legacy/default/malformed/expired/consumed markers and changed manifests
  fail closed. Unknown profiles and lexical root overlap/nesting also block.
- Arming, disarming and dispatch share `route.lock`, opened with FileShare.None.
  A contender fails immediately. Arming never overwrites an outstanding intent,
  including expired/legacy metadata. `-Profile default` is deliberate DISARM,
  never a stock-account selection; `default -Launch` is rejected. To target A,
  its actual declared name must be selected.
- A valid intent is flushed/replaced with a consumed tombstone BEFORE discovery
  or launch. The lock remains held through dispatch. No post-launch reset can
  erase a later arm; a repeat callback cannot reuse the consumed intent.
  Prerequisite/launch failures do not retry or fall back. Optional window-launch
  failure during arming attempts to disarm; if that write fails, report failure
  and require explicit disarm before any subsequent login attempt.
- Callback dispatch uses the existing launcher's real ProcessStartInfo builder,
  forwarding the profile/config and unmodified validated link. Only installed
  MSIX discovery is used. The armer no longer rewrites protocol registry keys.
  Setup/explicit consent owns registration, not a routine account launch.
- Logs retain S2c1's closed event schema. No paths, links, args or exception text.
  DISPATCH_COMPLETE means dispatch returned, NOT a successful account login.

### Evidence boundaries and known residual risks

The new tests use synthetic manifests/callbacks and doubles for dispatch/OS
boundaries. They exercise the real planner, start-info builder and dispatcher,
plus real file locking and atomic marker writes in an owned random TEMP directory.
Reentrant callback tests model a contender; they are NOT a multi-process stress
campaign. No Claude process, account, credential or existing profile is exercised.
No local Windows/PowerShell runtime is available. Source review and size/encoding
checks are not runtime PASS; actual new CI results must be read and recorded in
PR #1. This ledger summarizes older slices; their full details remain in Git.

The intent is NOT cryptographic correlation with the outgoing OAuth request.
Only Claude owns/verifies its state/PKCE. A delayed callback from a previous
browser flow can consume a newly armed intent. Close stale login tabs, initiate
only ONE login flow at a time, verify the browser account, and do not claim
arbitrary simultaneous-login safety. State-bound routing would require an
additional supported source of outgoing-request correlation; not implemented.

Validation of root independence here is lexical, not proof against junctions,
short names, hard-link aliases or another noncooperating process. Physical path
identity and metadata ownership belong to S4's local inventory. Full installers,
Desktop runtime and actual identity/memory A<->B remain UNQUALIFIED. A running
Desktop retains its environment; refocusing does not reconfigure it.

Historical route.log contents, PowerShell debugging/transcripts/in-memory errors,
OS process command-line telemetry and Claude internal logs are NOT sanitized.
The URL remains in the child command line. Do not publish old logs. The older
PROTOCOL-ROUTING.md and routing diagnostic still describe the legacy marker/log
behavior: update them before packaging. New route.lock and any orphan temporary
metadata need ownership-aware handling in S4; never delete a held lock file.

## Remaining ledger / exact next work

1. Read S2c2 CI results on its exact HEAD; repair this slice if needed, then STOP.
   No inference from old PASS results or pending/cancelled jobs.
2. S2c2 qualification follow-up: update routing guide/diagnostic, exercise the
   real Windows armer/dispatcher metadata boundary across processes, and keep
   the single-browser-flow limitation explicit. No account test on A.
3. S3: re-review/import the separate Python memory bridge (40 tests previously
   reported in `claude-shared-memory-slice1.zip`, not integrated). Verify current
   autoMemoryDirectory support and actual Desktop loading. Share selected project
   memory only, not whole config/auth roots or cloud conversations.
4. S4: read-only inventory of actual A, ownership manifest, new B paths, preview,
   local non-secret backups, safe rollback/uninstall, one-command packaging.
   Existing Uninstall.ps1 -RemoveData is NOT qualified for shared paths.
5. S5: disposable-project real-machine qualification of A/B identities, memory
   A->B and B->A, approved restart, and B removal leaving A/shared memory intact.
   Session/cloud-history merging and simultaneous Cowork VMs remain out of scope.

References checked for the locking/IO contract:
[FileShare.None](https://learn.microsoft.com/en-us/dotnet/api/system.io.fileshare?view=netframework-4.8.1),
[File.Move no-overwrite behavior](https://learn.microsoft.com/en-us/dotnet/api/system.io.file.move?view=netframework-4.8.1),
[native-app OAuth flow boundaries](https://www.rfc-editor.org/rfc/rfc8252.html).
