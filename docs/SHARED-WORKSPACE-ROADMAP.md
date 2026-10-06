# Shared workspace roadmap

Planning baseline: 2026-10-05; branch `fix/setup-profile-path-collision`, code
HEAD `794148f4072a59b4ca146b5199f5e7cea8fe8bb6`, base `master`
`2ee03050185ace47581e9607341bd91cddd5ae9a`. See the
[existing ledger](SHARED-WORKSPACE-LEDGER.md) for statuses and evidence.
This is the delivery plan. The user's 2026-10-06 instruction authorizes chaining
ready slices; actual installation/apply on real profiles still requires separate consent.

## Result and boundaries

Preserve the working account A in place, including its existing entry point.
Add account B in a second official Claude Desktop window, especially the Code
tab, with distinct login/data and config roots. Both use the same existing
project folders and explicitly selected project memory. No project migration,
duplication or mandatory worktrees. The user permits one writer per project;
agents may work simultaneously on different projects.

Deliver an additive previewable setup, two clearly labelled shortcuts, selected
shared memory, and conflict-aware rollback. Keep A's original shortcut; any
additional A-labelled shortcut must reproduce the inventoried entry point.
Equal project paths do not prove absence of impact: settings, hooks, memory,
process reuse and protocol registration can still affect A.

No cloud conversation merge, automatic transcript continuation/account rotation,
two simultaneous Cowork VMs, new orchestration platform or new chat UI.
Preserve upstream licence/credits and installed Claude binaries.

## What exists and what remains uncertain

Retain S2a's map-collision repair, S2b's child-only environment and quoting,
S2c1's closed log schema, and S2c2's explicit named v2 intent, manifest hash,
five-minute lifetime, shared nonblocking lock and consumption before launch.
Missing/legacy/expired/consumed/inconsistent intent refuses dispatch without A
fallback. `-Profile default` disarms; it does not select A. Arming no longer
changes registration. The File.Replace actual-null repair stays in place.

CI proves synthetic behavior; current real-file contention was within one
process and interleaving was simulated. There is no two-Desktop/account or
memory A/B proof. Current Setup overwrites files/maps/shortcuts and has no full
ownership/physical-alias gate. Current diagnostic pings by default and prints
raw process command lines. Current Uninstall can infer deletion targets from
names and has no shared-memory/alias ownership proof. Do not run these against
the installation before the corresponding protections are delivered.

## Resource-sharing decisions

| Resource | Proposed treatment | Evidence still needed |
| --- | --- | --- |
| Existing project files, project CLAUDE.md/rules, project skills and non-secret tool definitions | Already common on disk when both open that project; no copy required | Effective loading/trust in each Code window |
| Selected project auto memory | Adopt the chosen existing directory; one mapping per project | Bridge tests, then independent Desktop reads/writes |
| User instructions, non-secret settings, skills, agents, tool definitions | Optional allowlist of selected files/keys; preview and local backup | Scope, precedence and Desktop behavior; no whole-root link |
| Tool credentials, env secrets, account logins/cookies, session stores, account-specific permissions/preferences and connectors | Remain account-specific | Effective A/B isolation and provenance |

Project-local settings are common to both accounts on the same disk too; do not
treat them as an account-specific override. MCP definitions can contain secrets:
never copy `.claude.json`, Desktop config or an env block wholesale.
Global selective sharing is optional; separate identities and selected project
memory are mandatory. No general global-sync subsystem is required.

## Official configuration basis (read 2026-10-05)

[Memory](https://code.claude.com/docs/en/memory#storage-location) documents
`autoMemoryDirectory` in all settings scopes, an absolute or `~/` path, workspace
trust for project/local sources, and a restriction when
`permissions.blockReadsOutsideWorkingDirectories` is enabled. Recheck the
installed embedded Code version and policy before choosing the scope. A global
constant memory path risks mixing projects; do not use it as a universal map.

[Settings precedence](https://code.claude.com/docs/en/settings#settings-precedence)
is managed > command line > project local > project shared > user. Environment
pairs have their own rules; lists may merge. Preserve unrelated keys and inspect
effective sources rather than assuming the terminal environment describes A.

[Desktop shared configuration](https://code.claude.com/docs/en/desktop#shared-configuration)
describes common CLI/Desktop files, project instructions, hooks/skills and MCP.
Desktop MCP resolution has surface-specific precedence. These documents support
the proposed bridge, not proof that this installed Desktop honors the selected
config root or memory directory. CLI PASS is insufficient for that gate.

## Delivery sequence

All slices below are required unless marked optional. Each retains diff review,
bounded tests, an atomic commit and evidence. Chain satisfied prerequisites under
the user's current authorization; stop at actual unresolved gates. No automatic merge.
Anticipated paths are planning names,
not files created this turn. Keep each file around 500 lines; prefer Python for
new orchestration, retaining the existing PowerShell implementation.

Sequence: Q1 -> Q2 -> D1 -> D2 -> S3a; S4a may proceed if S3a is blocked.
S3b requires S3a + S4a; S3c requires S3b. S4b requires S4a + S3b; S4c requires
S4b + S3c. S4d -> S4e -> S5a -> S5b follow S4c. No real installation before
S4 protections and separate user approval. Optional S3g can be deferred.

### S2c2-Q1 — Multi-process lock and one-shot dispatch

- Objective: qualify two callbacks for one arm, concurrent arming, and an
  occupied lock using real Windows metadata IO and a recording launch double.
- Files (3): `tests/Test-RoutingProcesses.py`, `tests/fixtures/RouteWorker.ps1`,
  `docs/SHARED-WORKSPACE-LEDGER.md`.
- Prerequisites: reviewed S2c2 baseline, both Windows shells available; guarded
  imports, random owned TEMP metadata, no installed paths/registry or Claude.
- Tests: explicit IPC/barriers acknowledge lock-held/armed/consumed phases;
  per-case deadline 15 seconds, suite deadline 120 seconds. Run under PS5.1/7;
  assert exactly one launch receipt and tombstone, loser refusal/no fallback,
  no overwrite by contender, lock release and unchanged manifest.
- Exit: observable receipts and exit codes prove every case; timeout is failure,
  never inferred PASS from sleep. Cleanup only verified test-owned children and
  fixture paths. Never terminate Claude or delete a held lock.
- Stop: report Q1 alone; any production defect becomes a separate bounded repair
  proposal before Q2. Do not combine qualification with real login.

### S2c2-Q2 — Crash, expiration and explicit recovery

- Objective: qualify holder death before/after consumption and consumed-without-
  launch state; establish expiration and deliberate recovery semantics.
- Files (3): Q1 harness, Q1 worker, ledger.
- Prerequisites: Q1; handles and child ownership recorded before test termination.
- Tests: barrier-driven death injection; before consumption the old intent may
  remain, after consumption no replay launches. Discovery/launch failure keeps
  consumption. Inject an expired fixture timestamp without waiting five minutes;
  refuse dispatch/re-arm until explicit disarm, then new named arm. Same bounds
  as Q1; observe lock recovery, sidecars and no implicit retry/fallback.
- Exit: deterministic receipts for each crash phase and recovery; document
  ambiguity where a process launched before death but acknowledgment was lost.
- Stop: synthetic qualification report; no automatic retry against Desktop.

### S2c2-D1 — Passive diagnostic

- Objective: make diagnosis effect-free by default, with expurgated v2 state and
  fixed-schema events. No live ping consuming an intent.
- Files (3): `scripts/Test-ClaudeRouting.ps1`, `tests/Test-RoutingDiagnostic.ps1`,
  ledger.
- Prerequisites: Q2; review diagnostic OS boundaries before execution.
- Tests: fixtures verify default makes no activation/arming/process launch or
  writes; no raw URL, command line, exception, personal path or old-log output.
  Any separately approved live probe must first refuse outstanding intent.
- Exit: passive default verified under both shells; unknown state is reported
  rather than inferred from a delay or merely a new log line.
- Stop: diagnostic only; no installed diagnostic invocation this slice.

### S2c2-D2 — Current routing instructions

- Objective: replace legacy default fallback/log/registry claims and unsafe
  diagnostic recommendations with v2 procedure and known limits.
- Files (4): `docs/PROTOCOL-ROUTING.md`, `README.md`, `scripts/Setup.ps1`
  (printed diagnostic guidance only), ledger.
- Prerequisites: D1; preserve upstream credit and separate historical evidence.
- Tests: review all examples/links; parse Setup; verify no behavior change beyond
  its guidance, no old default-as-A/reset or armer-registry claims.
- Exit: named A/B, disarm, five-minute expiry, consumption and log meanings match
  code; no old-log publication or inferred authentication success.
- Stop: docs/guidance delivery; no Setup execution.

### S3a — Recover and review the external bridge

- Objective: review `claude-shared-memory-slice1.zip` before any import; record
  actual module layout, licence, safe IO and requalification commands.
- Files (2): roadmap and ledger; no import in this review slice.
- Prerequisites: actual supplied local ZIP, now supplied and reviewed on 2026-10-06.
  Frozen archive SHA-256: `654c158ae9f506d422a66cab688c79888e966adc9a46d34985d759e7c8de7d60`.
  Its historical ledger/NEXT SLICE does not supersede this fork's current state.
- Tests: inspect archive members without unsafe extraction; verify claimed
  40 tests and bounded fixture behavior by reading, not trusting the report.
- Exit: artifact/source identified and import file budget recorded; otherwise
  BLOCKED for import only. Do not invent/rewrite the missing implementation.
- Stop: review report; import waits for S4a provenance and the recorded adaptations.

#### S3a source admission review — 2026-10-06

Four actual members under `claude-shared-memory-slice1/`: `shared_memory.py`
(333 lines), `tests/test_shared_memory.py` (322), `SHARED_MEMORY.md` (204) and
`QUALIFICATION.json`. Normalized names are unique, with no traversal, encrypted
or symlink members; each is below 64 KiB. Python parses, and all three source/doc
SHA-256 and line counts match the historical qualification receipt. No LICENSE
member or explicit license grant is present; the document calls the additions
original. Preserve authorship/lineage and record license disposition at admission.

The receipt's 40 Linux tests are historical. After reading the complete source
and test suite, the original two Python members were copied individually into
owned TEMP for Windows requalification, without repository import. Python 3.14.7,
isolated interpreter, redirected HOME/USERPROFILE/TEMP, 60-second deadline:
`python -B -I -m unittest discover -s <owned-fixture>/tests -v` passed **40/40,
zero skips**, including actual symlinks and hard links. Quarantines were removed;
private output receipt is ignored by Git. No actual profile/project apply/restore.

Confirmed on synthetic fixtures: `make_plan` accepts memory underneath B's config
root, contrary to the outside-B-deletion-root requirement; `apply_plan` backs up
the entire prior settings JSON, including a synthetic env secret. These are
required adaptations, not regressions to ignore because the original tests pass.
Additional source gaps: lexical nesting/transaction identity misses Windows
short-name equivalence; configDir empty defaults to home/.claude without effective
A provenance; disabled memory is checked only in project-local settings; no
distinct-project memory map or trust/managed-policy evidence is established.
`read_optional` stats size then reads all bytes, leaving a growth race in the
claimed bound. Atomic replacement is expressly not CAS against live editors.

S3b admission budget: three files, planned `scripts/SharedMemoryPlan.py`,
`tests/test_shared_memory_plan.py`, ledger; optional usage document makes four.
Adapt only reviewed parsing/path/profile/memory helpers, Plan and make_plan.
Use a genuinely bounded reader, observed physical identity and explicit protected
A/B roles, per-project mapping, effective-scope/trust refusal and path-free public
output. Original plan tests must be retained/requalified or explicitly disposed;
apply/restore tests remain baseline evidence for S3c, not S3b qualification.
Exclude atomic_write, transaction_paths, locked, apply_plan, restore and the
action-switching CLI from S3b. S3c must use selected-key non-secret backups and
conflict-aware restore instead of wholesale settings snapshots/deletion.
No original archive document/ledger is imported as current guidance.
Desktop operator evidence now admits S3b planner/fixture development; unresolved effective scopes still refuse real plans.

#### Read-only MSIX complement to this review — 2026-10-06

Registered package: Claude, x64, publisher Anthropic, PBC, version 2.19675.0.0
before/after the read; PackageFullName remained stable. AppxManifest.xml SHA-256:
`eab8b235a718c86e8715ed78fa8e62f91daff6266099fdae0db5a004dc817571`.
Read-only package/manifest observations are retained in ignored private receipts.
No cookies, credential files, session DBs or profile contents were read.
Host build observed: 26300.9550 / 26H2; do not reuse this snapshot after updates.

Applications Claude, SshAskpass and SshProxy declare respectively
`app\Claude.exe`, `app\resources\claude-ssh-askpass.exe` and
`app\resources\claude-ssh-proxy.exe`, all with `Windows.FullTrustApplication`.
RuntimeBehavior/TrustLevel attributes are not explicit. Microsoft's
[Application schema](https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/element-application)
maps that EntryPoint to packagedClassicApp/mediumIL; this is schema interpretation,
not observation of actual activation, elevation, child processes or data-root use.

Manifest declares `desktop6:RegistryWriteVirtualization=disabled`, plus the newer
virtualization namespace with 12 excluded HKCU keys for browser integration/Office.
Four excluded filesystem directories are declared under KnownFolder:LocalAppData:
Microsoft/Office/16.0/WEF, Claude-3p, Claude-Data and Claude/logs. Capabilities include
runFullTrust, localSystemServices, packagedServices, unvirtualizedResources and
internetClient. No desktop6 FileSystemWriteVirtualization scalar is declared.
[Microsoft flexible virtualization](https://learn.microsoft.com/en-us/windows/msix/desktop/flexible-virtualization)
documents version-dependent precedence for old/new declarations. Do not collapse
these namespaces into a universal claim that virtualization is disabled everywhere.

Physical presence of the user's two A candidates, declared MSIX virtualization
and actual Desktop/Code usage are independent axes. Neither duplication nor
redirection of those candidates was established. Actual effective use stays unknown.
For qualification, capture registered package identity/version and observed running
UI version before/after; flag automatic updates and requalify affected gates rather
than reuse old receipts. UI differences alone are not account/isolation proof;
consider the user's reported possibility of server-side progressive feature rollout.
Removing B must preserve the official Claude package; package uninstall is never
a profile-cleanup operation. Source/fixture checks must exclude package removal.
S3 must eventually prove effective loading of autoMemoryDirectory in each Code
window and independent read/write-back; mere settings-key presence is insufficient.
S3b/S3c fixture results remain separate from that Desktop gate. Native 8.3 stays NOT_RUN.

### S4a — Read-only A inventory and physical ownership model

- Objective: inventory actual A data/config provenance, installed package version,
  existing entry point, non-secret routing metadata and fork-owned additions.
- Files (3): `scripts/Inspect-SharedWorkspace.py`,
  `tests/test_workspace_inventory.py`, ledger.
- Prerequisites: D2; inspect script/preflight before local inventory. User-guided
  effective Desktop configuration proof; terminal variables alone are insufficient.
- Tests: fixture aliases, junctions, case/short-name equivalents, nested roots,
  pre-existing same-name folders and ambiguous ownership; refuse uncertain targets.
- Exit: private local/ignored inventory with public placeholders only; A mapping
  evidenced without cookies, credentials, session DBs, old logs or global dumps.
  Existing A entry point is preserved. No path ownership inferred from its name.
- Stop: no writes to account/project roots; unresolved provenance blocks apply.

### S3b — Import and qualify the bridge's no-write plan

- Objective: import only reviewed bridge portions and adopt the selected existing
  project memory without moving it; propose minimal per-project settings edits.
- Files (3-4): reviewed Python planner module and tests (exact names fixed by S3a),
  ledger, optional bridge usage doc. No invented archive paths.
- Prerequisites: S3a + S4a; current version/scope/policy rechecked; chosen memory
  belongs outside all B deletion roots. If archive budget exceeds four files,
  split import and planner qualification before mutation is allowed.
- Tests: requalify the reported tests and add no-write preview, project identity,
  aliases/nesting, distinct projects, override precedence, disabled/trust-rejected
  memory, existing content preservation and minimal key diffs.
- Exit: exact proposed plan with hashes/provenance, no credentials or whole-root
  sharing; independent projects cannot map accidentally to one common directory.
- Stop: plan only, no real settings changes.

### S3c — Bridge apply and conflict-aware rollback on fixtures

- Objective: qualify minimal selected-key edits, non-secret backups, idempotence
  and rollback that detects subsequent edits instead of overwriting them.
- Files (3): reviewed bridge apply module, its tests, ledger.
- Prerequisites: S3b; backup selected non-secret values, not an entire settings
  file that might contain credentials/env secrets.
- Tests: repeated apply, partial failure, concurrent edit, missing/replaced target,
  previous-key absence, preserve unrelated keys and both projects' memory bytes.
- Exit: fixture receipts prove apply/rollback; no claim of Desktop loading.
- Stop: no real bridge adoption until the approved installation/qualification.

### S3g — Selective global resources (optional)

- Objective: share only explicitly chosen non-secret global instructions/skills/
  tool definitions; use project resources already common wherever sufficient.
- Files (3): reviewed bridge allowlist module, tests, ledger.
- Prerequisites: S3c and an explicit resource list; may be omitted from delivery.
- Tests: mixed secret/non-secret source refusal, key/file preview, permissions and
  MCP surface precedence, idempotence and rollback conflicts.
- Exit: no whole-root copy/link, credentials and account preferences separate.
- Stop: no blanket global sync or extra platform.

### S4b — Additive install plan

- Objective: plan only new B roots, stable launcher assets, ownership records,
  clear A-existing/B-added shortcuts and separately consented protocol changes.
- Files (3): `scripts/SharedWorkspacePlan.py`, `tests/test_workspace_plan.py`, ledger.
- Prerequisites: S4a + S3b; selected memory and A roots protected.
- Tests: physical collisions/nesting/aliases, existing assets, name conflicts,
  mapping preservation, no-write preview and install without protocol consent.
- Exit: reviewable additive plan including non-secret backups and rollback;
  A entry point and project folders unchanged. No adoption by folder name.
- Stop: preview only; missing access/ownership blocks apply.

### S4c — Additive execution on fixtures

- Objective: execute the approved plan safely, retaining PowerShell launcher and
  dynamic MSIX resolver; protocol registration is a separately authorized action.
- Files (4): `scripts/Setup.ps1`, `scripts/SharedWorkspacePlan.py`,
  `tests/test_workspace_install.py`, ledger.
- Prerequisites: S4b + S3c; fixture OS adapters reviewed before any script runs.
- Tests: repeated install, failures mid-write, changed plan inputs, unrelated
  shortcut/config preservation, backups and conflict-aware rollback.
- Exit: owned additions recorded, no silent replacement of A or shared roots.
- Stop: fixture-only report; real installation still requires approval.

### S4d — Remove B while preserving A and memory

- Objective: qualify current Uninstall replacement behavior: retain data by
  default; distinct explicit deletion only for proven-owned B additions.
- Files (3): `scripts/Uninstall.ps1`, `tests/Test-Uninstall.ps1`, ledger.
- Prerequisites: S4c ownership contract; no name-derived or stock-name safety claim.
- Tests: alias/nesting, custom A, shared memory, partial install, modified protocol
  registration and shortcut conflicts; occupied route.lock refusal; released
  orphan route.lock/temp cleanup only when ownership and inactivity are proven.
  Preserve the installed official Claude package; never uninstall it to remove B.
- Exit: rollback checks current values before restore; never delete a held lock,
  A or shared memory. Removing B must not remove routing still needed by A.
- Stop: fixtures only, no actual Uninstall or data deletion.

### S4e — Minimal packaging and one-command guide

- Objective: package existing scripts plus reviewed bridge, with preview-first
  entry, expurgated diagnostic and consent gates; no dependency auto-install.
- Files (4): `scripts/SharedWorkspace.py`, `tests/test_workspace_entry.py`,
  `README.md`, ledger.
- Prerequisites: S4d + D2; Python prerequisite explicit if the chosen bridge needs it.
- Tests: help/preview offline, clean fixture install/rollback, missing prerequisites,
  package hashes and launcher-relative imports; examples and public path review.
- Exit: one documented entry command; bounded workflow, no chat UI or migration.
- Stop: ready for user-approved local qualification, no automatic merge/release.

### S5a — Browser-focus hypothesis, approved local trial

- Objective: test the user's hypothesis that foregrounding the already signed-in
  browser window/profile determines where Desktop's HTTPS login opens.
- Files (2): `MANUAL-TEST.md`, ledger; private receipts remain outside Git.
- Prerequisites: S4e protections, approved additive B installation and explicit
  local browser/login trial; no real trial during this documentary turn.
- Tests: record browser/version/profile and foreground window, observe HTTPS
  destination separately from its authenticated account and from the returned
  claude:// Desktop target. Start with harmless HTTPS navigation when useful;
  it alone cannot prove the actual login link behavior. Close stale login tabs,
  choose B explicitly, verify browser identity, perform one login flow at a time.
- Exit: observed/failed/inconclusive hypothesis recorded on this browser; focus
  never replaces explicit intent or permits fallback A. Do not bypass state/PKCE.
- Stop: no simultaneous-login experiment. A delayed old callback can consume a
  new arm: current marker is not correlated to the outgoing OAuth request.

### S5b — Two-Desktop acceptance and delivery decision

- Objective: prove the full user result on a disposable project in local Code
  sessions, then decide whether the draft is ready for user-directed delivery.
- Files (3): `MANUAL-TEST.md`, `README.md`, ledger.
- Prerequisites: S5a, all required synthetic gates, saved active work and explicit
  agreement for any A restart, settings edits, B removal or separate data deletion.
- Tests: A usable before/after B, effective A/B identities and distinct config
  roots, same project path without worktree, selected memory A->B then B->A,
  another project excluded, persistence after agreed restart, B removal retaining
  A and shared memory. Observe each Desktop loading the memory, not just equal
  paths or a bridge PASS. Two windows do not require concurrent login flows.
- Exit: local receipts expurgated for publication, each gate independently marked;
  absent evidence stays unverified. Do not promise provider session permanence.
  Record versions before/after, handle automatic updates and require actual
  autoMemoryDirectory loading/read-write evidence, not only a settings-key match.
- Stop: delivery decision and report; no automatic merge, deployment or restart.

## Optional REA artifact investigation track

New documentation PR #2 supplies [REA-QUALIFICATION.md](REA-QUALIFICATION.md); only its document is admitted,
not the old branch snapshot. This optional track does not replace native profile protections or existing regressions.
REA-A1: packaged fixture smoke at pinned REA 4.0.1 is VERIFIED_SYNTHETIC, adoption EXPERIMENTAL. Exact source recipe,
artifact hashes, structured questions and limitations are in [the dated receipt](REA-SMOKE-20261006.md).
REA-A2: complete source-built ELF/native PE and explicit provider readiness, then a genuinely archived Claude pair;
[issue #3](https://github.com/JayceeB1/claude-windows-multiprofile/issues/3) tracks these unexecuted gates. No global setup,
mandatory dependency, authenticated-process attachment, provider auto-install or automatic runtime promotion.
Large-target REA issues #623/#746 stay unconfirmed local risks. Claude Code #33619 remains open; #57529 is a closed
duplicate, not a confirmed cause of this user's folder button failure. GitHub Issues are now enabled; both issue and
PR creation permissions were read back for the connected account. REA output must preserve OBSERVED/INFERRED/UNKNOWN.

## Current continuation boundary

S2-D2, S3a review, Desktop operator evidence and S3b/S3c/S4b-e preparation have historical Windows fixture receipts.
S4f/S4g-Q1/Q2 qualify the native candidate on Windows fixtures; Q2 adds four actual registry/mutex API contracts.
Actual Unicode COM shortcuts, file locks, PS5.1/PS7 wrappers and extracted package executed only on owned TEMP.
Registry algorithms use a model and actual APIs in a bounded disposable HKCU namespace; real associations/ACL variants remain NOT_RUN.
The latest user instruction authorizes tests, superseding the prior stop-before-tests. Normal commit/push/draft-PR
updates and CI resume; no merge while required Desktop acceptance is missing. Default legacy invocations stay refused.
S5 approved provisioning is installed; two bounded owned-registration repairs retain A/package and leave B unlaunched.
Operator default-app picker still offers only Claude despite Shell enumeration of the dedicated router: UI gate BLOCKED.
Next: inspect the registered-app Settings page before considering session refresh; reboot causality remains UNKNOWN.
Project/profile share/apply/restore, removal or restart still needs separate local authorization.
The earlier CLI-only/Desktop-path blocker is superseded by the user's Desktop screenshot, not generalized to all projects.
Native 8.3, effective B loading/config isolation and two-Desktop acceptance remain NOT_RUN. Optional REA-A2 stays deferred.
