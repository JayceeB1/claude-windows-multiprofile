# Shared workspace fork - implementation ledger

Updated 2026-10-06 (Q1 delivery). Delivery order, file budgets, dependencies and stop gates:
[Shared workspace roadmap](SHARED-WORKSPACE-ROADMAP.md). This is the sole ledger.
Requirements below are separate from implementation and evidence statuses.

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

## Verified repository and CI snapshot

Read-only fetch confirmed remote `JayceeB1/claude-windows-multiprofile`.
The clean local checkout started on master and was switched normally to the
tracking PR branch; no reset, clean, stash, forced checkout, merge or rebase.
Code HEAD is `794148f4072a59b4ca146b5199f5e7cea8fe8bb6`; master remains at
`2ee03050185ace47581e9607341bd91cddd5ae9a`. No delta from the supplied code HEAD.
[PR #1](https://github.com/JayceeB1/claude-windows-multiprofile/pull/1) was OPEN,
draft, seven commits and nine cumulative files at inspection, before this
additional two-document commit. No merge performed. Local user's configured Git
identity is used without changes or assistant attribution; upstream licence and
credits remain intact. Inherited CLAUDE.md identity/branch and old test guidance
are superseded by the user's explicit instructions and actual branch/tests.

[Run 37375728981](https://github.com/JayceeB1/claude-windows-multiprofile/actions/runs/37375728981)
was reread with `gh run view 37375728981 --json url,status,conclusion,headSha,jobs`
and each job's own `gh run view 37375728981 --job <id> --log`.
All three jobs are completed/success. The workflow tests the temporary PR merge
ref `5fed29786c087fd9d53d8bce0d9755dc9488936a`, combining the code HEAD and base;
this is NOT a merge into master. Historical cancelled/pending runs are not the
current gate. This evidence predates the documentary commit.

| Job / receipt | Environment | Observed result |
| --- | --- | --- |
| [111983866240](https://github.com/JayceeB1/claude-windows-multiprofile/actions/runs/37375728981/job/111983866240) | Windows runner, PS7 7.6.6 | 11 scripts parsed; 153 profile assertions; 3 argument cases; **129** launcher assertions; 39 dispatch scenarios / 521 assertions |
| [111983866371](https://github.com/JayceeB1/claude-windows-multiprofile/actions/runs/37375728981/job/111983866371) | Windows runner, PS5.1 5.1.26100.33438 | 11 scripts parsed; 153 profile assertions; 3 argument cases; **126** launcher assertions; 39 dispatch scenarios / 521 assertions |
| [111983866006](https://github.com/JayceeB1/claude-windows-multiprofile/actions/runs/37375728981/job/111983866006) | Ubuntu runner, pwsh, PSScriptAnalyzer | Errors-only scan succeeded: “No PSScriptAnalyzer errors.” Warnings were not qualified. |

Local environment checked: Windows native PowerShell 7.6.6, Windows PowerShell
5.1.26100.9549 and Python 3.14.7. No WSL execution or dependency installation.
After reading the test and guarded imports, parser preflight inspected all
11 scripts/tests with `Parser::ParseFile`, then `./tests/Test-ShimLogging.ps1`
ran once under native PS7: 39 scenarios / 521 assertions PASS. Only newly owned
random TEMP metadata files/locks and launch doubles were exercised and cleaned;
no real Claude process, profile, registry, account or OAuth flow.
The PS5.1 suite was NOT rerun locally; its evidence above is its own CI log.
No local lint run, broader campaign, installer, uninstall, arming entry point,
live diagnostic or protocol link execution was performed.

Exploration: jCodeMunch list/index/outline returned 13 files but zero PowerShell
symbols. GitNexus list was queried; local index-only analysis did not complete
and was interrupted through its owned command session. Direct source reads
covered the required scripts, four tests, CI, README, routing guide and ledger.
No graph result is used as architecture proof. No application/test/CI edits.

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
Native Windows PS7 and current cross-shell CI evidence are recorded above.
This remains synthetic qualification, not real Desktop acceptance. Full older
slice details remain in Git; no historical PASS is promoted to a local gate.

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

## Implementation and evidence register

Status vocabulary: TODO / IN_PROGRESS / BLOCKED / IMPLEMENTED /
VERIFIED_SYNTHETIC / VERIFIED_LOCAL. Synthetic qualification can use a native
Windows host; VERIFIED_LOCAL is reserved here for the actual user installation.
A passing implementation test does not satisfy the user acceptance requirements.
Each future slice must add its exact commit, environment, command and receipt
before changing its evidence status. The roadmap-only turn started no remaining
implementation; the separately authorized Q1 delivery is recorded below.

| ID | Status | Dependencies | Commit / evidence environment and command | Receipt / limit | Next action |
| --- | --- | --- | --- | --- | --- |
| S2a | VERIFIED_SYNTHETIC | baseline | `973fc155`; Windows CI, Test-SetupProfiles with pinned baseline | Current run above; profile loop doubles only | Preserve repair |
| S2b | VERIFIED_SYNTHETIC | S2a | `f4ef960`, test repair `f6ea7a9`; Windows CI, Test-Launcher / Test-ArgBuilder | Current run; no real process/environment-loading proof | Preserve child-only environment |
| A-PRESERVE | TODO | S4a-S5b | Requirement recorded in `3546ddb`; no installation receipt | User reports A already works; not locally observed this turn | Inventory then acceptance |
| S2c1 | VERIFIED_SYNTHETIC | S2b | `5c908a7`; Windows CI, Test-ShimLogging | Closed new-log schema; old logs not sanitized | Preserve schema |
| S2c2 | VERIFIED_SYNTHETIC | S2c1 | Initial `81da85e`, actual-null repair `794148f`; cross-shell CI and local PS7 Test-ShimLogging | Current receipts above; real TEMP IO, same-process contention and simulated interleaving | Q1 |
| S2c2-Q1 | VERIFIED_SYNTHETIC | S2c2 | Production `794148f`; harness/worker in this Q1 delivery commit; native PS5.1/7 + Python | `python tests/Test-RoutingProcesses.py`: 8 cases PASS; details below; no Desktop launch | Q2 crash/expiry recovery |
| S2c2-Q2 | TODO | Q1 | None | Crash/expiry recovery not qualified across processes | Barrier-driven death and explicit recovery |
| S2c2-D1 | TODO | Q2 | None; source review only | Current default ping can consume intent; raw command lines/old logs exposed | Passive expurgated diagnostic |
| S2c2-D2 | TODO | D1 | None; source review only | README/guide still claim legacy default reset and armer registry writes | Align v2 examples/guidance |
| S3a | BLOCKED | D2 + supplied ZIP | None; filename search only in supplied workspace | **ARTEFACT_MANQUANT**; reported 40 tests unverified, no import | Obtain actual artifact, review before import |
| S4a | TODO | D2 | None | A paths/config provenance and physical ownership unobserved | Read-only inventory; can proceed while ZIP missing |
| S3b | TODO | S3a + S4a | None; official docs read, not runtime proof | Import/plan gated by missing ZIP | Requalify reviewed no-write bridge |
| S3c | TODO | S3b | None | No apply/rollback receipts | Minimal selected-key changes on fixtures |
| S3g | TODO | S3c + selected list | None; optional | No global sharing requested by default | Defer or qualify explicit allowlist |
| S4b | TODO | S4a + S3b | None | Setup lacks complete collision/ownership preview | Additive no-write plan |
| S4c | TODO | S4b + S3c | None | Full Setup not fixture-qualified for preserving A | Additive execution/rollback on fixtures |
| S4d | TODO | S4c | None; Uninstall source reviewed | Name-derived fallback and unchecked custom config deletion; route.lock/temp not cleaned; no ownership/conflict protection | Owned B removal, retain data by default |
| S4e | TODO | S4d + D2 | None | No qualified one-command package | Preview-first entry and guide |
| S5a | TODO | S4e + explicit local approval | None | Browser focus is **HYPOTHESIS TO TEST** | Observe HTTPS/profile identity/claude:// separately |
| S5b | TODO | S5a + all required synthetic gates + approval | None | Two Desktop identities, memory and removal unobserved | Real disposable-project acceptance |

## S2c2-Q1 — Windows multi-process synthetic qualification (2026-10-06)

User's subsequent go-ahead authorizes Q1 only. Parent documentary commit:
`55ee33066fb5e31dbde7c8815e3d80b57ba7d909`; production routing source remains
`794148f4072a59b4ca146b5199f5e7cea8fe8bb6`. Three owned delivery files:
`tests/Test-RoutingProcesses.py`, `tests/fixtures/RouteWorker.ps1`, this ledger.
Resolve the atomic Q1 commit with `git log -1 --format=%H -- tests/Test-RoutingProcesses.py`.
No roadmap, application script or CI change; no merge.

Command: `python tests/Test-RoutingProcesses.py` (both shells by default).
Environment: native Windows, Python 3.14.7, Windows PowerShell 5.1.26100.9549,
PowerShell 7.6.6. Worker startup receipts check actual PID, requested mode and
shell major version. Each copied production source and worker is parsed before
import; AST checks require the existing dot-source guards and exact shim
assignments. No dependencies installed and no WSL execution.

| Case | PS5.1 | PS7 | Observed assertion / receipt |
| --- | --- | --- | --- |
| callbacks | PASS | PASS | Two independent callback workers; first acknowledges consumed tombstone while holding the real lock, contender refuses with ROUTE_BUSY without changing bytes; release produces exactly one CreateNew launch receipt for B with exact args/config and parent environment unchanged; later replay refuses with TARGET_READ_FAILED |
| concurrent-arm | PASS | PASS | B armer pauses after writing its actual v2 intent while retaining the lock; A contender refuses; marker bytes stay unchanged; A still refuses outstanding B after release |
| occupied-lock | PASS | PASS | Separate holder acknowledges real FileShare.None lock; both arm and callback refuse; independent exclusive-open cleanup guard refuses the held lock; marker unchanged; release permits a new lock probe |
| timeout-control | PASS | PASS | Parent deliberately withholds release; waiting for a result raises BARRIER_TIMEOUT within the configured 0.25-second wait instead of claiming success; explicit release then result/exit and lock probe succeed |

Final summary: **8 cases PASS; owned fixtures removed; no Desktop qualification**.
One initial PS5.1 run caught a fixture scope bug: dot-sourcing the armer's param
block replaced the worker's selected profile. The worker now preserves/restores
its fixture profile; no production repair or weakened assertion was required.
The full matrix was rerun after final harness changes.

Boundaries: Python owns each Popen/Windows handle from creation and never scans
or terminates by process name/PID discovery. JSON stdout/stdin acknowledgments
order the interleaving; no sleeps establish PASS. Per-case execution deadline
15 seconds, overall execution deadline 120 seconds, bounded cleanup waits of
2 seconds per retained child handle/reader. A missed barrier or timeout fails;
only owned test workers may be terminated on failure. Cleanup waits for their
exit, rejects aliases, checks the ownership token and resolved TEMP scope,
refuses an exclusively held lock, then removes only that fixture. Successful
cases also prove unchanged manifest bytes, no temporary write sidecars and no
synthetic data/config directories created.

The real planner, armer, dispatcher, lock, file replacement, marker reader,
logger and callback start-info builder run on freshly copied sources and real
TEMP metadata. Package discovery and both window/process-start boundaries are
recording doubles; the fake executable is inert fixture text. Callbacks and
A/B roots are synthetic. The installed application, protocol registration,
accounts, credentials, memory, browser and existing A are not exercised.

This is deterministic controlled cross-process contention, not a stress campaign
or proof of arbitrary simultaneous browser logins. Process-death timing,
consumed-without-launch failure recovery and expiry remain Q2. The worker's
barrier can wait while the parent is alive; the parent enforces its deadline.
CI currently does not invoke the new Python matrix: local receipts establish Q1;
existing/new CI results must not be presented as Q1 runtime proof. CI integration
is not added in this three-file slice.

Additional Q1 validation: all 12 PowerShell scripts/tests parsed under PS7;
Python AST parsed; local installed PSScriptAnalyzer 1.25.0 errors-only scan of
`tests` passed (no warning-free claim). Relative ledger links, file sizes and
single NEXT SLICE checked; full three-file diff reviewed.

Four controlled mutation checks (two per shell) altered only owned fixture
copies: FileShare.None -> FileShare.ReadWrite was rejected with LOG_EVENTS;
replacing consumed tombstone writing with the original intent was rejected with
UNEXPECTED_WORKER_EVENT before a launch receipt. Each failure was required,
not counted as an unexplained PASS; production sources were untouched and all
mutant fixtures were removed. These validate the harness's failure detection.
Jev's advisory gate returned escalate despite verifying the supplied claims;
manual review covered guarded imports, all real-launch doubles, fixture scope,
retained process handles, alias refusal and exclusive-open cleanup. No automatic
probabilistic approval or real-host proof is claimed.

Validated Q1 source SHA-256 (resolve the delivery commit with the command above):
- `tests/Test-RoutingProcesses.py`: `c503094365f1f15a999d1fddb488e0d50e5bfe2ddf049fc43a27b79ede2e9377`
- `tests/fixtures/RouteWorker.ps1`: `f264d1e991255ed5380afb03bc90ff2f0c6de43344aaed757193bdf9ece3b844`

The user's requested deep local structure analysis remains in S4a when repository
facts leave gaps. It has not been run against the actual installation this turn.

## Decisions and planning evidence

- Projects stay where they are; no migration or mandatory worktrees. The user
  owns the one-writer-per-project rule. Two agents may use different projects.
- Login/data and config roots stay distinct. Existing project instructions,
  project skills, settings and tool definitions are already common on disk;
  effective loading remains a gate. Selected non-secret global resources are
  optional; credentials/connectors/account preferences remain account-specific.
- Keep A's existing entry point. Two clear shortcuts must not silently replace
  it or infer A's paths/config from stock conventions or a terminal variable.
- Setup currently force-copies launcher assets, rewrites profiles.json and
  creates shortcuts; S2a does not prove additive install safety. Uninstall's
  stock-name/isDefault checks do not prove ownership or physical separation.
- Protocol changes require separate consent, a local ownership/backup record
  and conflict-aware restoration. Removal retains data by default. Any deletion
  is a distinct explicit action restricted to proven-owned B additions, never
  A/shared memory. Never delete a held lock; inspect orphan temporary sidecars.
- Browser focus idea is neither accepted as fact nor rejected. The future trial, subject to explicit approval,
  observes (1) HTTPS destination window/profile, (2) its account,
  (3) returned claude:// target independently. Choose B, verify browser account,
  close stale login tabs, one login at a time. Two open Desktop windows do not
  require concurrent logins. Focus cannot justify automatic A fallback.
- Current intent does not correlate the outgoing OAuth request: a delayed
  callback can consume a new arm. Preserve state/PKCE; no unsupported origin
  recognition promise. Consumed-without-launch requires deliberate recovery.
- ZIP lookup was restricted to the repository (including untracked/hidden file
  names) and the supplied visualization workspace. Neither contained the ZIP;
  no other drive search or invented Windows equivalent of a sandbox path.
  Missing artifact blocks S3 import, not these documents or Q1.
- Official sources reread on 2026-10-05:
  [memory storage](https://code.claude.com/docs/en/memory#storage-location),
  [precedence](https://code.claude.com/docs/en/settings#settings-precedence),
  [Desktop configuration](https://code.claude.com/docs/en/desktop#shared-configuration).
  autoMemoryDirectory is documented in every settings scope with absolute/~/
  paths, project/local trust and a blockReadsOutsideWorkingDirectories caveat.
  Managed > CLI > local > shared project > user; environment rules vary by key.
  Desktop reads shared configuration, with MCP surface-specific precedence.
  Installed embedded-version support, config-root isolation and actual memory
  loading remain unverified. No global memory path that mixes projects.
- Bridge proof and Desktop A->B/B->A proof are separate. Adopt only chosen
  existing project memory, minimal edits, non-secret backups, idempotence and
  conflict-aware rollback. Personal paths/sensitive evidence stay local/ignored;
  public receipts use placeholders. No complete account-root copies/links.
- No automatic merge. Future implementation slices are 2-4 files, bounded
  preflight/tests, diff review, atomic commit, report, STOP. Any A restart needs
  saved work and explicit agreement; no forced stop/logout/replacement.

References checked for the locking/IO contract:
[FileShare.None](https://learn.microsoft.com/en-us/dotnet/api/system.io.fileshare?view=netframework-4.8.1),
[File.Move no-overwrite behavior](https://learn.microsoft.com/en-us/dotnet/api/system.io.file.move?view=netframework-4.8.1),
[native-app OAuth flow boundaries](https://www.rfc-editor.org/rfc/rfc8252.html).

Document validation (roadmap-only turn): both files are below 500 lines; relative links resolve;
UTF-8 readback, one NEXT SLICE and staged `git diff --check` pass. The complete
two-document diff was reviewed; application, test and CI files are unchanged.

## NEXT SLICE

**S2c2-Q2 — Windows synthetic crash, expiration and explicit recovery.**
Three files: the Q1 Python harness, its guarded PowerShell worker and this ledger.
Qualify holder death before/after consumption, consumed-without-launch state,
expiry and deliberate disarm/new named arm with acknowledged phases, bounded
waits and termination only through retained test-owned handles. No Claude
termination, installation or real login. Q2 is TODO: wait for the user's next
go-ahead, complete that slice alone, report its evidence and STOP.
