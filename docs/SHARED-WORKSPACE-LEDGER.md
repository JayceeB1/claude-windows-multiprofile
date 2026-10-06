# Shared workspace fork - implementation ledger

Updated 2026-10-06 (native candidate qualified on Windows fixtures). Delivery order and dependencies: [Shared workspace roadmap](SHARED-WORKSPACE-ROADMAP.md). This is the sole ledger. Requirements below are separate from implementation and evidence statuses.

## Contract

Two Claude Desktop accounts with separate Desktop data directories and separate Claude Code config roots. Both accounts work in the same existing
local project folders and share explicitly selected project memory. One agent writes to a project at a time, managed by the user. No worktree
requirement.

Do not share/copy credentials, cookies, complete config roots, internal Desktop stores, or cloud conversations. No automatic account/quota
rotation. Preserve upstream licensing; do not modify or redistribute Claude binaries.

### Existing session preservation - mandatory acceptance gate

The user explicitly confirmed on 2026-10-05 that a working session already exists. Treat that session as account A, to preserve in place, NOT as
a disposable test profile or a fresh login. The exact local paths and effective configuration have only partial read-only observations; effective
Desktop A configuration remains unconfirmed. These are acceptance requirements, not protections already proven by the current code.

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

User clarification for S4: project folders remain at their existing locations; there is no planned move or project deletion. Local verification
must confirm that adding/removing B only affects its owned additions, not shared resources.

## Work rules

Current user instruction authorizes fixture tests and normal delivery. No real-profile apply, login/restart or merge before Desktop acceptance. Keep files below approximately 500 lines. Use the connected user's Git identity; do not copy upstream's author or add assistant/co-author attribution. Keep master
unchanged until approval.

## Published baseline

Branch: `fix/setup-profile-path-collision`; draft PR #1. Master base: `2ee03050185ace47581e9607341bd91cddd5ae9a`.

| Slice | Commit | Evidence / scope |
| --- | --- | --- |
| S2a - installer map collision | `973fc1550ec3d1ca0f2c1f9ab474972f4ade3ce5` | Separate resolved path variables from case-insensitive hashtable parameters; unchanged public contract. |
| S2b - launcher | `f4ef9603188cdba7d28c876893bef8d820188521` | Child-only environment, quoted paths, validation before IO; no parent environment mutation. |
| S2b test repair | `f6ea7a99976427343f780f8c963fab63bdafac76` | Distinguish empty vs absent environment variable; no production change. |
| Existing A gate | `3546ddb2face6a5f4e922d46a73c268f817928c6` | Requirements above, not a machine qualification. |
| S2c1 - secret-free logs | `5c908a795af7ee44e287d8528f4af4ed1c0272ea` | Fixed event/category fields; no callback or raw exception in explicit outputs. |

## Verified repository and CI snapshot

Read-only fetch confirmed remote `JayceeB1/claude-windows-multiprofile`. The clean local checkout started on master and was switched normally to
the tracking PR branch; no reset, clean, stash, forced checkout, merge or rebase. Code HEAD is `794148f4072a59b4ca146b5199f5e7cea8fe8bb6`; master
remains at `2ee03050185ace47581e9607341bd91cddd5ae9a`. No delta from the supplied code HEAD. [PR #1](https://github.com/JayceeB1/claude-windows-multiprofile/pull/1) was OPEN, draft, seven commits and nine cumulative files at inspection, before this additional two-document commit. No merge
performed. Local user's configured Git identity is used without changes or assistant attribution; upstream licence and credits remain intact.
Inherited CLAUDE.md identity/branch and old test guidance are superseded by the user's explicit instructions and actual branch/tests.

[Run 37375728981](https://github.com/JayceeB1/claude-windows-multiprofile/actions/runs/37375728981) was reread with `gh run view 37375728981
--json url,status,conclusion,headSha,jobs` and each job's own `gh run view 37375728981 --job <id> --log`. All three jobs are completed/success.
The workflow tests the temporary PR merge ref `5fed29786c087fd9d53d8bce0d9755dc9488936a`, combining the code HEAD and base; this is NOT a merge
into master. Historical cancelled/pending runs are not the current gate. This evidence predates the documentary commit.

| Job / receipt | Environment | Observed result |
| --- | --- | --- |
| [111983866240](https://github.com/JayceeB1/claude-windows-multiprofile/actions/runs/37375728981/job/111983866240) | Windows runner, PS7 7.6.6 | 11 scripts parsed; 153 profile assertions; 3 argument cases; **129** launcher assertions; 39 dispatch scenarios / 521 assertions |
| [111983866371](https://github.com/JayceeB1/claude-windows-multiprofile/actions/runs/37375728981/job/111983866371) | Windows runner, PS5.1 5.1.26100.33438 | 11 scripts parsed; 153 profile assertions; 3 argument cases; **126** launcher assertions; 39 dispatch scenarios / 521 assertions |
| [111983866006](https://github.com/JayceeB1/claude-windows-multiprofile/actions/runs/37375728981/job/111983866006) | Ubuntu runner, pwsh, PSScriptAnalyzer | Errors-only scan succeeded: “No PSScriptAnalyzer errors.” Warnings were not qualified. |

Local environment checked: Windows native PowerShell 7.6.6, Windows PowerShell 5.1.26100.9549 and Python 3.14.7. No WSL execution or dependency
installation. After reading the test and guarded imports, parser preflight inspected all 11 scripts/tests with `Parser::ParseFile`, then
`./tests/Test-ShimLogging.ps1` ran once under native PS7: 39 scenarios / 521 assertions PASS. Only newly owned random TEMP metadata files/locks
and launch doubles were exercised and cleaned; no real Claude process, profile, registry, account or OAuth flow. The PS5.1 suite was NOT rerun
locally; its evidence above is its own CI log. No local lint run, broader campaign, installer, uninstall, arming entry point, live diagnostic or
protocol link execution was performed.

Exploration: jCodeMunch list/index/outline returned 13 files but zero PowerShell symbols. GitNexus list was queried; local index-only analysis
did not complete and was interrupted through its owned command session. Direct source reads covered the required scripts, four tests, CI, README,
routing guide and ledger. No graph result is used as architecture proof. No application/test/CI edits.

## S2c2 - explicit callback routing and one-shot intent

Parent: `5c908a795af7ee44e287d8528f4af4ed1c0272ea`; same branch/PR, four files: `ClaudeOpenShim.ps1`, `Arm-ClaudeLogin.ps1`, `Test-
ShimLogging.ps1`, this ledger. Existing CI already executes that test file in both Windows jobs after parsing.

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

The new tests use synthetic manifests/callbacks and doubles for dispatch/OS boundaries. They exercise the real planner, start-info builder and
dispatcher, plus real file locking and atomic marker writes in an owned random TEMP directory. Reentrant callback tests model a contender; they
are NOT a multi-process stress campaign. No Claude process, account, credential or existing profile is exercised. Native Windows PS7 and current
cross-shell CI evidence are recorded above. This remains synthetic qualification, not real Desktop acceptance. Full older slice details remain in
Git; no historical PASS is promoted to a local gate.

The intent is NOT cryptographic correlation with the outgoing OAuth request. Only Claude owns/verifies its state/PKCE. A delayed callback from a
previous browser flow can consume a newly armed intent. Close stale login tabs, initiate only ONE login flow at a time, verify the browser
account, and do not claim arbitrary simultaneous-login safety. State-bound routing would require an additional supported source of outgoing-
request correlation; not implemented.

Validation of root independence here is lexical, not proof against junctions, short names, hard-link aliases or another noncooperating process.
Physical path identity and metadata ownership belong to S4's local inventory. Full installers, Desktop runtime and actual identity/memory A<->B
remain UNQUALIFIED. A running Desktop retains its environment; refocusing does not reconfigure it.

Historical route.log contents, PowerShell debugging/transcripts/in-memory errors, OS process command-line telemetry and Claude internal logs are
NOT sanitized. The URL remains in the child command line. Do not publish old logs. Historical versions described legacy marker/log behavior; D2 supersedes those instructions. New route.lock and any orphan temporary metadata need ownership-aware
handling in S4; never delete a held lock file.

## Implementation and evidence register

Status vocabulary: TODO / IN_PROGRESS / BLOCKED / IMPLEMENTED / IMPLEMENTED_NOT_TESTED / VERIFIED_SYNTHETIC / VERIFIED_LOCAL. Synthetic qualification can use a native
Windows host; VERIFIED_LOCAL is reserved here for the actual user installation. A passing implementation test does not satisfy the user
acceptance requirements. Each future slice must add its exact commit, environment, command and receipt before changing its evidence status. The
roadmap-only turn started no remaining implementation; the separately authorized Q1 delivery is recorded below.

| ID | Status | Dependencies | Commit / evidence environment and command | Receipt / limit | Next action |
| --- | --- | --- | --- | --- | --- |
| S2a | VERIFIED_SYNTHETIC | baseline | `973fc155`; Windows CI, Test-SetupProfiles with pinned baseline | Current run above; profile loop doubles only | Preserve repair |
| S2b | VERIFIED_SYNTHETIC | S2a | `f4ef960`, test repair `f6ea7a9`; Windows CI, Test-Launcher / Test-ArgBuilder | Current run; no real process/environment-loading proof | Preserve child-only environment |
| A-PRESERVE | TODO | S4a-S5b | Requirement recorded in `3546ddb`; no installation receipt | User reports A already works; not locally observed this turn | Inventory then acceptance |
| S2c1 | VERIFIED_SYNTHETIC | S2b | `5c908a7`; Windows CI, Test-ShimLogging | Closed new-log schema; old logs not sanitized | Preserve schema |
| S2c2 | VERIFIED_SYNTHETIC | S2c1 | Initial `81da85e`, actual-null repair `794148f`; cross-shell CI and local PS7 Test-ShimLogging | Current receipts above; real TEMP IO, same-process contention and simulated interleaving | Preserve |
| S2c2-Q1 | VERIFIED_SYNTHETIC | S2c2 | Production `794148f`; harness/worker in this Q1 delivery commit; native PS5.1/7 + Python | `python tests/Test-RoutingProcesses.py`: 8 cases PASS; details below; no Desktop launch | Preserve |
| S2c2-Q2 | VERIFIED_SYNTHETIC | Q1 | Parent `1497f48`; three-file Q2 delivery below; native PS5.1/7 + Python | 12 Q2 cases PASS, plus 8 Q1 regressions; four expiry mutants detected; no Desktop launch | Preserve |
| S2c2-D1 | VERIFIED_SYNTHETIC | Q2 | Parent `8b8431b`; three-file D1 delivery below; native PS5.1/7 | 33 fixture cases / 959 assertions per shell; six unsafe/leaking mutants detected; no installed invocation | Preserve |
| S2c2-D2 | VERIFIED_SYNTHETIC | D1 | Parent `c96402f`; four-file D2 delivery below | Docs/examples match v2 and D1; Setup non-guidance tokens unchanged | Preserve; S3a now reviewed |
| S3a | VERIFIED_SYNTHETIC | D2 + ZIP | `1664fa4`; frozen archive review | Original 40 Windows tests PASS; no verbatim import | Preserve lineage |
| S4a | IMPLEMENTED | D2 | `8f0947d`; read-only inventory + Desktop operator report | PARTIAL_LOCAL; path/index report accepted for preparation; native data redirection unresolved | Native acceptance |
| S3b | VERIFIED_SYNTHETIC | S3a + S4a operator evidence | `6f22250`, namespace repair `e7dd6ee`; Run-SharedWorkspaceTests | 31 planner contracts; no writes, explicit scope/trust/policy refusal | Preserve preview |
| S3c | VERIFIED_SYNTHETIC | S3b | `58e0fcb`; consolidated runner | 18 apply/recovery contracts plus planner; selected-key only; real apply NOT_RUN | Preserve fixture evidence |
| S3g | TODO | S3c + explicit list | Optional, omitted | No selected global resources or whole-root sharing | Defer |
| S4b | VERIFIED_SYNTHETIC | S4a + S3b | `059bf05`; consolidated runner | 10 additive preview contracts; no writes | Preserve preview |
| S4c | VERIFIED_SYNTHETIC | S4b + S3c | `9e4b9ae`; consolidated runner | 12 historical TEMP-only install/guard contracts; native candidate separate | S4f qualification |
| S4d | VERIFIED_SYNTHETIC | S4c | `bd34247`, guard `574342f`; runner + Test-Uninstall | 9 B-removal contracts; data retained; native removal NOT_RUN | Native adapter acceptance |
| S4e | VERIFIED_SYNTHETIC | S4d + D2 | `c50c0da`, guide `839558d`; consolidated runner | 10 historical preview/package contracts; historical 19-member package | S4g qualification |
| S4f | VERIFIED_SYNTHETIC | S4c + S4d | `083c02b` + Q1 fixes/contracts; Windows | Actual TEMP COM/locks and disposable registry/mutex APIs; Desktop NOT_RUN | S5 admission |
| S4g | VERIFIED_SYNTHETIC | S4f + S4e | `7ae1479` + Q1; Python 3.14.7, PS5.1/7 | Actual TEMP wrappers/extracted package; Q2 168 contracts, 167 PASS / 1 SKIP | Desktop acceptance |
| S5a | TODO | S4e + explicit local approval | None | Browser focus is **HYPOTHESIS TO TEST** | Observe HTTPS/profile identity/claude:// separately |
| S5b | TODO | S5a + all required synthetic gates + approval | None | Two Desktop identities, memory and removal unobserved | Real disposable-project acceptance |

## S2c2-Q1 — Windows multi-process synthetic qualification (2026-10-06)

User's subsequent go-ahead authorizes Q1 only. Parent documentary commit: `55ee33066fb5e31dbde7c8815e3d80b57ba7d909`; production routing source
remains `794148f4072a59b4ca146b5199f5e7cea8fe8bb6`. Three owned delivery files: `tests/Test-RoutingProcesses.py`,
`tests/fixtures/RouteWorker.ps1`, this ledger. Resolve the atomic Q1 commit with `git log -1 --format=%H -- tests/Test-RoutingProcesses.py`. No
roadmap, application script or CI change; no merge.

Command: `python tests/Test-RoutingProcesses.py` (both shells by default). Environment: native Windows, Python 3.14.7, Windows PowerShell
5.1.26100.9549, PowerShell 7.6.6. Worker startup receipts check actual PID, requested mode and shell major version. Each copied production source
and worker is parsed before import; AST checks require the existing dot-source guards and exact shim assignments. No dependencies installed and
no WSL execution.

| Case | PS5.1 | PS7 | Observed assertion / receipt |
| --- | --- | --- | --- |
| callbacks | PASS | PASS | Two independent callback workers; first acknowledges consumed tombstone while holding the real lock, contender refuses with ROUTE_BUSY without changing bytes; release produces exactly one CreateNew launch receipt for B with exact args/config and parent environment unchanged; later replay refuses with TARGET_READ_FAILED |
| concurrent-arm | PASS | PASS | B armer pauses after writing its actual v2 intent while retaining the lock; A contender refuses; marker bytes stay unchanged; A still refuses outstanding B after release |
| occupied-lock | PASS | PASS | Separate holder acknowledges real FileShare.None lock; both arm and callback refuse; independent exclusive-open cleanup guard refuses the held lock; marker unchanged; release permits a new lock probe |
| timeout-control | PASS | PASS | Parent deliberately withholds release; waiting for a result raises BARRIER_TIMEOUT within the configured 0.25-second wait instead of claiming success; explicit release then result/exit and lock probe succeed |

Final summary: **8 cases PASS; owned fixtures removed; no Desktop qualification**. One initial PS5.1 run caught a fixture scope bug: dot-sourcing
the armer's param block replaced the worker's selected profile. The worker now preserves/restores its fixture profile; no production repair or
weakened assertion was required. The full matrix was rerun after final harness changes.

Boundaries: Python owns each Popen/Windows handle from creation and never scans or terminates by process name/PID discovery. JSON stdout/stdin
acknowledgments order the interleaving; no sleeps establish PASS. Per-case execution deadline 15 seconds, overall execution deadline 120 seconds,
bounded cleanup waits of 2 seconds per retained child handle/reader. A missed barrier or timeout fails; only owned test workers may be terminated
on failure. Cleanup waits for their exit, rejects aliases, checks the ownership token and resolved TEMP scope, refuses an exclusively held lock,
then removes only that fixture. Successful cases also prove unchanged manifest bytes, no temporary write sidecars and no synthetic data/config
directories created.

The real planner, armer, dispatcher, lock, file replacement, marker reader, logger and callback start-info builder run on freshly copied sources
and real TEMP metadata. Package discovery and both window/process-start boundaries are recording doubles; the fake executable is inert fixture
text. Callbacks and A/B roots are synthetic. The installed application, protocol registration, accounts, credentials, memory, browser and
existing A are not exercised.

This is deterministic controlled cross-process contention, not a stress campaign or proof of arbitrary simultaneous browser logins. Process-death
timing, consumed-without-launch failure recovery and expiry remain Q2. The worker's barrier can wait while the parent is alive; the parent
enforces its deadline. CI currently does not invoke the new Python matrix: local receipts establish Q1; existing/new CI results must not be
presented as Q1 runtime proof. CI integration is not added in this three-file slice.

Additional Q1 validation: all 12 PowerShell scripts/tests parsed under PS7; Python AST parsed; local installed PSScriptAnalyzer 1.25.0 errors-
only scan of `tests` passed (no warning-free claim). Relative ledger links, file sizes and single NEXT SLICE checked; full three-file diff
reviewed.

Four controlled mutation checks (two per shell) altered only owned fixture copies: FileShare.None -> FileShare.ReadWrite was rejected with
LOG_EVENTS; replacing consumed tombstone writing with the original intent was rejected with UNEXPECTED_WORKER_EVENT before a launch receipt. Each
failure was required, not counted as an unexplained PASS; production sources were untouched and all mutant fixtures were removed. These validate
the harness's failure detection. Jev's advisory gate returned escalate despite verifying the supplied claims; manual review covered guarded
imports, all real-launch doubles, fixture scope, retained process handles, alias refusal and exclusive-open cleanup. No automatic probabilistic
approval or real-host proof is claimed.

Validated Q1 source SHA-256 (resolve the delivery commit with the command above):
- `tests/Test-RoutingProcesses.py`: `c503094365f1f15a999d1fddb488e0d50e5bfe2ddf049fc43a27b79ede2e9377`
- `tests/fixtures/RouteWorker.ps1`: `f264d1e991255ed5380afb03bc90ff2f0c6de43344aaed757193bdf9ece3b844`

The user's requested deep local structure analysis remains in S4a when repository facts leave gaps. It has not been run against the actual
installation this turn.

## S2c2-Q2 — Crash, expiration and explicit recovery (2026-10-06)

Q2 alone is authorized by the user's NEXT SLICE instruction. Parent: `1497f482e6764c7467b07277c7f63f708acf9120`; production remains `794148f`.
Owned files: `tests/Test-RoutingProcesses.py`, `tests/fixtures/RouteWorker.ps1` and this ledger. Resolve this atomic delivery commit with `git
log -1 --format=%H -- tests/Test-RoutingProcesses.py`. No application, roadmap or CI implementation changed; PR #1 remains draft because its
installation and Desktop acceptance criteria remain unqualified.

Command: `python tests/Test-RoutingProcesses.py`. Native Windows environment: Python 3.14.7, Windows PowerShell 5.1.26100.9549 and PowerShell
7.6.6. Final receipt: **PASS Q1/Q2: 20 cases; owned fixtures removed; no Desktop qualification**. Eight Q1 regressions and twelve new Q2 cases
passed, within the existing 15-second case / 120-second suite deadlines.

| New case | PS5.1 | PS7 | Observable receipt / assertion |
| --- | --- | --- | --- |
| death-before-consume | PASS | PASS | Real lock acquired through the retained production scriptblock; PID-checked barrier before returning it to the dispatcher; forced death leaves exact armed bytes, no launch, outstanding arm refusal; unchanged lock file identity and new-process probe succeed |
| death-after-consume | PASS | PASS | Discovery barrier verifies consumed tombstone before any launch; forced death leaves it intact; replay refuses, no launch; same lock recovered |
| death-after-launch | PASS | PASS | Launch double flushes CreateNew B receipt, then pauses before launch-recorded/result/DISPATCH_COMPLETE; death leaves exactly one receipt and consumed tombstone; replay adds no receipt |
| discovery-failure | PASS | PASS | Double acknowledges injected discovery exception; result/exit 1, APP_DISCOVERY_FAILED, consumed bytes survive replay; deliberate new named A arm and callback succeed |
| launch-failure | PASS | PASS | Double acknowledges exception before creating receipt; result/exit 1, LAUNCH_REQUESTED then LAUNCH_FAILED; consumed bytes survive replay, no implicit launch; new named A arm succeeds |
| expiration-recovery | PASS | PASS | Real locked writer uses production intent constructor with time six minutes earlier, keeping the exact five-minute interval and manifest binding; callback and both A/B re-arm refuse without changing expired bytes; explicit default disarm then new A arm succeeds |

Each death case and expiry also verifies default disarm launches nothing, callback while disarmed refuses, new named A arm launches nothing
implicitly, one explicitly submitted callback records A, and its replay refuses without changing tombstone/receipt bytes. Successful cases check
exact fixed event sequences, unchanged manifest, no temporary write sidecars, no data/config root creation, and an independent new-process lock
probe.

Important semantic distinction: expired armed intent requires explicit disarm before re-arm; consumed intent already permits deliberate new named
arming. Q2 qualifies the existing behavior and does not add a mandatory disarm gate for consumed state. Before-consumption death can leave a
valid old intent; this harness chooses explicit disarm rather than automatically replaying it.

Death injection targets only the parent's retained Popen/Windows handle after the acknowledged phase and independent proof that the lock is held.
A nonzero termination exit, EOF without a result, released exclusive lock and unchanged file identity are required. No process scan, Claude
termination, sleep-based PASS or held-lock deletion. Q1 ownership-token, TEMP scope, alias rejection, bounded cleanup and safe import checks
remain in force.

Limits: controlled process death at these three barriers does not cover power loss or every instruction inside file replacement. No orphan temp
was observed at these phases; mid-write orphan admission/removal remains outside this test. If real process launch precedes holder death but its
acknowledgment is lost, consumed state alone cannot prove whether launch occurred or authentication succeeded. The synthetic durable receipt
demonstrates this ambiguity only; there is no exactly-once Desktop activation claim and no automatic retry.

Additional validation: 12 PowerShell files parsed under PS7; installed PSScriptAnalyzer 1.25.0 tests scan passed at Error severity. Four
controlled fixture-copy mutation checks, two per shell, disabled dispatcher expiration or allowed outstanding armed-state overwrite. The expiry
case rejected them with UNEXPECTED_WORKER_EVENT / RESULT_CODE_MISMATCH respectively; all mutant fixtures were removed. Production sources were
untouched. Complete diff and guarded imports reviewed; file sizes remain below 500 lines. GitNexus has no resolved PowerShell execution flows
here; direct source and native receipts establish behavior. CI still does not execute the Python matrix; synthetic Q2 runtime proof is local.
Jev's advisory gate verified all three supplied claims but escalated patch confidence (safe_to_apply 0.37, limiting rubric test_gap). Manual
review covered retained handles, death-phase ordering, lock identity, receipt preservation, expiry-only timestamp changes, imports and start
doubles; no probabilistic automatic approval is claimed. Real installation, browser login, accounts and memory remain unqualified. Next slice is
D1 only.

## S2c2-D1 — Passive diagnostic (2026-10-06)

User-authorized D1 only; parent `8b8431bc82cfb47defcc26c33b386fd803556dbc`. Three files: `scripts/Test-ClaudeRouting.ps1`, `tests/Test-
RoutingDiagnostic.ps1` and this ledger. Resolve the atomic delivery commit with `git log -1 --format=%H -- scripts/Test-ClaudeRouting.ps1`. The
earlier diagnostic source observations above describe its pre-D1 state.

Default output is one closed-schema JSON event `DIAGNOSTIC_PASSIVE`. Its fixed fields describe metadata snapshot availability, syntactic manifest
readability, intent state, expiration and manifest hash binding, package presence and UserChoice classification. No paths, profile names,
versions, raw registry values, URLs, command lines, exceptions or old log contents are emitted. `dispatch=not_probed` is invariant: neither
package presence nor UserChoice router classification establishes OS activation, login, identity or Desktop configuration. Readable
manifest/binding match is not full path-plan validation.

`-NoPing` remains compatible and has no effect; all invocations are passive. There is no live-probe option, delay, process query, arming or
launch. Installed routing scripts are never imported. Reads use bounded 64 KiB metadata and reject reparse ancestors. The snapshot takes a read-
only exclusive handle to an existing route.lock only, briefly contending with cooperating writers; it creates/writes nothing. Missing/busy lock,
unavailable path or inaccessible metadata remains unknown. File reads can affect filesystem access timestamps; bytes, file set and last-write
timestamps are preserved. Noncooperating alias races/power-loss durability and physical installation ownership are not proven by D1.

Commands: `powershell -NoProfile -File tests/Test-RoutingDiagnostic.ps1` and `pwsh -NoProfile -File tests/Test-RoutingDiagnostic.ps1`. Both
passed **33 cases, 959 assertions**, native PS5.1.26100.9549 / PS7.6.6. Cases cover missing, armed, consumed, disarmed, expired, future/invalid
timestamps, malformed/legacy/oversize metadata, binding mismatch, missing manifest, read/lock refusal, junction alias, missing/invalid path,
package/registry absence and failure, all-stream hostile messages, -NoPing compatibility and default path using a fixture USERPROFILE. Real TEMP
IO is used; package/registry boundaries are doubles. Installed-script import bombs and secret-bearing old logs remain inert. All owned fixtures
are removed after ownership, alias and lock checks; no installed invocation occurred.

Six controlled mutation checks (activation command, file write and output leak, each under both shells) were rejected by UNSAFE_COMMAND_BOUNDARY,
UNSAFE_MEMBER_BOUNDARY and OUTPUT_LEAK. Parser preflight passed for 13 PowerShell files; changed-script PSScriptAnalyzer 1.25.0 scan passed at
Error severity. Complete three-file diff reviewed; application routing, Setup, guides and CI remain unchanged. GitNexus rebuilt after a buffer-
pool failure but resolves no PowerShell flows; jCodeMunch reports no PowerShell symbols. Native fixture proof and direct boundary review
establish D1. CI does not invoke this new test yet; runtime receipts are local. Jev verified all three supplied claims but escalated patch
confidence (safe_to_apply 0.42; limiting rubric blast_radius). Manual review covered the CLI compatibility boundary, fixed output, read-only
modes, rejected aliases and missing/busy lock semantics; no probabilistic approval is claimed. PR #1 remains draft with Desktop acceptance
pending.

## S2c2-D2 — Current routing instructions (2026-10-06)
The user now authorizes chaining ready slices, retaining separate atomic commits.
Parent `c96402f884ca325ca0303a6f47a1fbc232ff2e54`; files: README, routing guide,
Setup printed guidance/comment and this ledger. Resolve commit with
`git log -1 --format=%H -- docs/PROTOCOL-ROUTING.md`.
Docs now describe named A/B intent, disarm, five-minute expiry, pre-launch
consumption, failure/recovery, fixed-log meanings and D1's passive JSON schema.
Removed live ping/raw process dumps, default-as-A/reset, armer-registry claims,
unsafe installation/removal repairs and unsupported authentication-success claims.
Historical Windows/Cowork behavior is identified as upstream evidence to requalify;
fork lineage, prior-art credits and MIT are preserved. Setup changed only printed
guidance and one stale comment. Setup parses under PS5.1/7; line comparison excludes
Write-Host/comments only and all other lines match the parent. Local links and fenced
examples reviewed; no Setup or installed diagnostic invocation. Existing D1 fixture
tests remain PASS in both shells. S4a proceeds independently of missing bridge ZIP.

## S4a — Inventory implementation and partial local evidence (2026-10-06)

Parent `ce2b7ba`; three files: `scripts/Inspect-SharedWorkspace.py`, `tests/test_workspace_inventory.py` and this ledger. Resolve atomic commit
with `git log -1 --format=%H -- scripts/Inspect-SharedWorkspace.py`.

Python uses read-attributes Windows handles, volume/file IDs and final paths for existing identity, projecting missing roots from an observed
parent. Alias, case, junction, hard-link and nesting conflicts are surfaced; existing same-name additions remain unowned. Unknown observations
refuse ownership. The model never permits apply. Identities are current snapshots, not race-proof future ownership. No account contents,
credentials, session DBs, old logs or process command lines are read. Only bounded routing metadata, named-asset presence, explicit entry
identity and the fixed package query are observed. No installed script executes.

`python tests/test_workspace_inventory.py`: 23 tests, 22 PASS, one SKIP: this volume does not provide a distinct 8.3 alias (native short-name
gate NOT_RUN). Synthetic short-name ID equivalence is tested separately; it is not native 8.3 proof. Real junctions, hard links, case/nesting,
malformed paths, unowned pre-existing folders, bounded metadata, output-alias refusal, create-once private reports, unchanged fixture bytes and
no secret reads are qualified on native Windows. Python AST preflight passed before local inventory. The only optional write is a new private
.local.md report outside protected roots; no overwrite is allowed.

Local read-only inventory used user-supplied A data/config candidates and a candidate fork-install parent. Both A candidates exist; fork-install
parent and profiles.json are absent. Installed MSIX version 2.19675.0.0 was observed under WindowsApps; this does not establish the
version/session currently running. The user reports opening A via its Start-menu/taskbar icon; no entry was changed. Private paths and receipts
are in ignored local reports, not Git or PR output. Actual effective Code configuration and full A provenance remain UNCONFIRMED; S4a exit
criteria are therefore BLOCKED/PARTIAL_LOCAL, despite implemented, fixture-qualified inventory. No mutation, installation or restart was
attempted. The missing ZIP still blocks S3a/S3b; do not substitute an invented bridge. Jev's advisory combined gate escalated with truncated
context; no approval is claimed. Manual review traced native handle access, metadata-only reads, private create-once output, unknown provenance
and unchanged D2 non-guidance code before delivery.

## S3a — Frozen archive review and Windows requalification (2026-10-06)

Parent `8804e5c`; only roadmap and ledger change. Original ZIP remains unchanged; SHA-256
`654c158ae9f506d422a66cab688c79888e966adc9a46d34985d759e7c8de7d60`. Four bounded normalized members, no duplicate/traversal/encrypted/symlink
members; source/doc hashes and line counts match QUALIFICATION.json. Python ASTs parse; 40 actual test methods exist. No explicit LICENSE
member/grant; the supplied document asserts originality. License disposition is recorded at admission. Historical
SHARED_MEMORY.md/QUALIFICATION.json are evidence, not current workflow.

After complete source/test reading, original Python members alone ran in owned TEMP under Python 3.14.7, isolated mode and redirected
HOME/USERPROFILE/TEMP: 40/40 Windows tests PASS, zero skips (including symlinks/hard links), exit 0, 1.67 seconds wall time under a 60-second
bound. Private receipt is Git-ignored. All quarantine paths were removed; apply/restore used synthetic fixtures only. Two fixture probes confirm
memory-under-B-config acceptance and full-settings backup containing a synthetic env secret. Planner-only admission and required
physical/provenance, bounded-read, scope/trust and selected-key backup adaptations are detailed in the roadmap. No original code imported into
Git. No actual project/profile apply/restore or account/session changes. S3a is complete; S3b remains blocked. Resolve this review commit with
`git log -1 --format=%H -- docs/SHARED-WORKSPACE-ROADMAP.md`.

## Read-only MSIX complement to S3a (2026-10-06)

Claude x64 / Anthropic, PBC: registered version 2.19675.0.0 before and after, PackageFullName stable; manifest SHA-256
`eab8b235a718c86e8715ed78fa8e62f91daff6266099fdae0db5a004dc817571`. Three FullTrustApplication declarations: Claude, SshAskpass, SshProxy;
runtime/trust attributes are implicit. Legacy registry-disabled declaration coexists with newer 12 registry exclusions and four LocalAppData
filesystem exclusions; unvirtualizedResources and service/full-trust capabilities are declared. Detailed namespace-sensitive interpretation and
source links are in the roadmap; private identity/location/XML receipts are Git-ignored. No package/profile mutation. Physical candidates are not
declared duplicates; MSIX declarations are not actual A redirection/use proof. Effective usage remains UNKNOWN. Preserve official package when
removing B; never use package uninstall as profile cleanup. Capture versions before/after qualification, account for automatic updates and
possible progressive server rollout; UI appearance alone is not identity proof. S3 requires effective memory loading/read-write evidence in Code,
not a settings-key presence test. Native 8.3 remains NOT_RUN. No cookies, credentials or session databases read.

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

References checked for the locking/IO contract: [FileShare.None](https://learn.microsoft.com/en-us/dotnet/api/system.io.fileshare?view=netframework-4.8.1), [File.Move no-overwrite behavior](https://learn.microsoft.com/en-us/dotnet/api/system.io.file.move?view=netframework-4.8.1), [native-app OAuth flow boundaries](https://www.rfc-editor.org/rfc/rfc8252.html).

## S4a selected-memory observation follow-up (2026-10-06)

Implemented explicit --project/--memory-candidate/--reported-surface options in Inspect-SharedWorkspace.py; read only selected keys from user/project/local settings with a 64 KiB bound, duplicate/nonfinite rejection and change checks; refuse reparse ancestors and multiply linked settings. Reject outside-scope configured/candidate paths before probing. Memory inspection counts at most 129 entries and checks index presence without reading contents or creating folders. Protect the selected project from receipt output; exclusive private .local.md output remains the only write. These checks are bounded observations, not a concurrent namespace-race security guarantee or effective precedence.

Windows Python qualification: 37 tests, 36 PASS, 1 SKIP (native 8.3 remains NOT_RUN). Fixtures cover no mutation/content reads, secret suppression, absent folders, scope boundaries, junctions/hard links, malformed/large/changing settings, conflicting scopes, entry cap, file candidates and private/path-free CLI output. No real apply/restore. Read-only local receipt (Git-ignored): user autoMemoryEnabled=true; autoMemoryDirectory absent; project/local settings missing; candidate has two entries and MEMORY.md, contents unread. CLI and same Desktop path are user reports; actual Desktop A loading is NOT_OBSERVED. Managed policy, CLI environment/arguments and active config resolution remain unobserved. S4a stays PARTIAL_LOCAL/BLOCKED; S3b admission stays BLOCKED, no prototype source imported. Registered Claude package 2.19675.1.0 before/after this inspection differs from historical 2.19675.0.0; update cause and running version unknown. No package/profile mutation. Missing proof: Desktop A Code on the selected project must expose its actual memory/config path and startup index loading. A targeted fresh Code-session context/path read-back or a scoped native file-access observation can establish this without Desktop /memory (unavailable there); perform only with saved work and separate consent if restart/instrumentation is needed.

## Desktop evidence and S3b/S3c/S4b fixture admission (2026-10-06)

Desktop operator path/startup report plus scoped metadata admit fixture preparation (PARTIAL_LOCAL); A data-root/B
loading remain unobserved. S3b: 30 original planner contracts; S3c: 18 apply/recovery plus 30 regressions; S4b: 10
additive preview plus 30 regressions. Later namespace regression brings planner to 31 contracts. No real apply.
No archive license grant: independently authored adaptation retains lineage, without verbatim redistribution.
[Detailed receipts](SHARED-WORKSPACE-QUALIFICATION.md) retain commits, test disposition and IO limits. Terminal/embedded
Code installations differ; scratch memory is independent. No auth-storage/env inference. Native 8.3 remains NOT_RUN.

## S4c fixture installation (2026-10-06)

FixtureWindows is restricted to owned TEMP paths; shortcut JSON and an in-memory protocol are explicit OS doubles,
never native .lnk/registry proof. Additive copied assets/B roots have physical ownership and hash receipts; repeated
install, partial failure and conflict-aware rollback retain B data and A/project/memory. Unknown sidecars/locks refuse
cleanup. Legacy Setup now refuses full execution before OS IO; its profile-loop regression fragments remain intact.
Native installation/shortcuts/registry remain NOT_RUN. 52 Windows tests PASS (40 prior + 12 install/guard cases), no skips.

## S4d removal qualification (2026-10-06)

61 Windows fixture tests PASS (52 prior + 9 B-removal cases), zero skips: B data retained by default, separately
acknowledged fixture deletion limited to recorded physical B roots, A-only routing/shortcut and package preserved.
Modified/aliased roots/shortcuts, occupied locks, partial installs and changed protocol owners refuse removal.
Uninstall.ps1 now refuses native cleanup before mutation; Test-Uninstall.ps1 passes under PS5.1 and PS7.
No stock-name fallback, package removal or actual profile deletion. Native removal remains NOT_RUN.

## S4e preview/package entry (2026-10-06)

50 Windows cases PASS at the S4e slice (40 prior + 10 entry/package), no skips: offline preview/help, exact private key/hash reports,
protected/exclusive output, credential-named input refusal, allowlisted package hashes and extracted relative imports.
No native mutation actions. README/manual procedure supersede legacy Setup/Uninstall recipes. Native OS adapter and
S5 trials remain NOT_RUN; this closes preparation, not actual two-account acceptance. Optional global sharing omitted.

## New document/issue reconciliation and REA-A1 (2026-10-06)

PR #2 document-only commit aeb8cb8 admitted as 8d1b672; no old implementation snapshot merged. Issues changed from disabled to enabled during this review; connected JayceeB1 has admin/push/triage rights. Follow-up [#3](https://github.com/JayceeB1/claude-windows-multiprofile/issues/3) created. REA-A1 (`c5389b7`): pinned 4.0.1 packaged fixture and reproduction CORRECT, adoption EXPERIMENTAL; seven classified questions, exact artifact/resource hashes and main.cjs delta. Generic compare UNKNOWN; graph churn PARTIAL. Initial Startup timeout/CRLF repair retained; [receipt](REA-SMOKE-20261006.md). ELF/PE/Claude pair/runtime/8.3 NOT_RUN; no global setup, normal-use dependency or real profile mutation/isolation proof.

## S4f/S4g candidate and Q1 fixture qualification (2026-10-06)

Candidate commits 083c02b/7ae1479/42e8297 stopped before tests as instructed. Subsequent user go-ahead authorizes Q1.
Windows matrix: 164 unique contracts, 163 PASS / 1 explicit 8.3 SKIP; 28 new native TEMP and 9 registry-model contracts.
Actual Unicode COM read-back, operation/routing locks, PS5.1/PS7 wrappers and extracted-package native workflow pass.
Fixes: IShellLinkW/IPersistFile avoids observed WScript Unicode loss; explicit PythonExecutable bypasses Store alias
ambiguity; unreadable B traversal refuses before mutation. Registry simulated only; native APIs/mutex remain NOT_RUN.
Q1/Q2 process matrix 20 PASS; both-shell Setup/argument/launcher/dispatch/uninstall/diagnostic regressions pass; analyzer
Error severity clean. Initial harness/Unicode/alias/lint invocation failures retained in [qualification](SHARED-WORKSPACE-QUALIFICATION.md).
Jev review escalated confidence; manual source review performed, no automatic acceptance. CAS/hostile receipt protection
not claimed; interrupted manifest/receipt ownership needs review. A, shared resources and official package never touched.
Q1 fixes/tests: 9a614c3/c5db4a8. [CI 37508782528](https://github.com/JayceeB1/claude-windows-multiprofile/actions/runs/37508782528) at 431d40c passed: 164 contracts, 163 PASS / 1 SKIP per shell.
Q2: 168 contracts, 167 PASS / 1 SKIP; four actual registry/mutex API tests in guarded disposable HKCU; no production associations.
Commit/push/draft-PR/CI resume under test authorization; do not merge or promote fixtures to Desktop acceptance.

## NEXT SLICE

Separately authorized S5 trials with confirmed A provenance and an exact reviewed private plan. Native 8.3 stays NOT_RUN;
optional REA-A2 follows issue #3. Effective B memory/config and two-Desktop acceptance remain unqualified.
