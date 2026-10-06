# Claude Windows multiprofile

This fork prepares two official Claude Desktop windows with separate account data
and Code configuration roots, using the same existing project folders and
explicitly selected project memory. Preserve the working account A in place;
add account B without migrating projects or requiring worktrees.

**Delivery status:** routing/diagnostic, memory planner/transactions and additive install/removal are qualified on
Windows fixtures. Desktop operator evidence is recorded for selected A memory. Native additive execution, B memory
loading and two-Desktop acceptance remain unqualified. An explicit native adapter and command wrappers are
qualified on isolated Windows fixtures (COM, locks and disposable registry APIs exercised). Real Desktop acceptance
remains NOT_RUN. The default Setup/Uninstall invocation still refuses mutations. Follow the [ledger](docs/SHARED-WORKSPACE-LEDGER.md),
[roadmap](docs/SHARED-WORKSPACE-ROADMAP.md) and [qualification receipts](docs/SHARED-WORKSPACE-QUALIFICATION.md).

## Preview-first shared workspace

Requires Windows and Python 3.12+, standard library only. Nothing installs dependencies or launches Claude.

The router host is an own C# WinExe, not a Claude binary. A missing local `scripts/ClaudeLoginRouter.exe`
is compiled using the existing Windows .NET Framework64 v4 compiler during preview/package preparation;
this creates an ignored build artifact in the source directory. No compiler is downloaded. The generated
PE is retained between preview and installation so approval hashes remain stable, and packaged with its source.
Changing that C# source requires a fresh build and a new approval preview; existing build files are not overwritten.
Keep a private specification outside Git, named `*.workspace.local.json`. It explicitly declares A's existing
`dataDir`/`configDir`, B's new distinct roots, the launcher install parent, Desktop shortcut folder and each existing
project's own memory mapping. Unknown config provenance, trust, managed/CLI overrides or version evidence refuses a plan.
Operator-reported Desktop paths are recorded as such; equal CLI/Desktop paths do not prove B loading or MSIX redirection.

```powershell
python -B scripts/SharedWorkspace.py help
python -B scripts/SharedWorkspace.py preview --spec "$env:TEMP\claude.workspace.local.json"
# Optional private exact paths/key changes/hashes; new file only, outside observed roots:
python -B scripts/SharedWorkspace.py preview --spec "$env:TEMP\claude.workspace.local.json" --output "$env:TEMP\claude-preview.local.md"
# Allowlisted self-contained code/docs archive with PACKAGE.json hashes, no profiles or private receipts:
python -B scripts/SharedWorkspace.py package --output "$env:TEMP\claude-workspace-reviewed.zip"
```

Private specification shape (replace placeholders; mark evidence true only when established):

```json
{
  "schema": 1,
  "profiles": {
    "A": {"dataDir": "C:\\PATH\\ExistingAData", "configDir": "C:\\PATH\\ExistingAConfig"},
    "B": {"dataDir": "C:\\PATH\\NewBData", "configDir": "C:\\PATH\\NewBConfig"}
  },
  "projects": [{
    "project": "F:\\PATH\\ExistingProject",
    "memory": "C:\\PATH\\ExistingAConfig\\projects\\SelectedProject\\memory",
    "evidence": {
      "config_provenance": false, "memory_provenance": false,
      "trust_confirmed": false, "external_policy_reviewed": false,
      "version": "OBSERVED_VERSION", "surface": "desktop_user_report"
    }
  }],
  "install_dir": "C:\\PATH\\NewLauncher",
  "desktop_dir": "C:\\PATH\\ExistingDesktop",
  "protocol": {"change": false, "consent": false, "expected_before": null}
}
```

Preview never creates B or memory folders. Existing launcher roots/shortcut names are refused, not adopted.
Selected project instructions/settings stay on disk. Preview exposes only the `autoMemoryDirectory` change and hashes,
never whole settings/env/hooks. Fixture rollback preserves later unrelated edits and refuses changed/replaced owned targets.
B removal retains its data by default, keeps A routing, and never uninstalls the official Claude package.

The fixture OS adapter remains TEMP-bounded. JSON shortcut doubles and in-memory protocol values are not native
.lnk/registry proof. The new Windows 64-bit candidate uses COM shortcut staging/read-back, physical ownership
receipts, selected-key memory transactions and cooperative locks. Actual Desktop/runtime qualification is NOT_RUN.
`apply`, `install`, `remove` and `restore` remain unavailable; only explicit `native-*` actions enter the candidate.
See the [manual acceptance procedure](MANUAL-TEST.md) before any native operation.

### Native candidate commands — separately authorized real-profile trial

These commands were qualified only on owned TEMP fixtures, never on real profiles or project settings.
COM uses explicit Unicode IShellLinkW. Registry algorithms were tested against a model and actual Windows APIs
in a unique disposable HKCU namespace; production associations/default-handler selection remain unexecuted. Obtain separate authorization before real profiles/projects. Python must be a real
installed runtime, not a Store alias. Wrappers accept `-PythonExecutable "C:\PATH\python.exe"` to select it explicitly.

```powershell
# Prepare a private approval capsule; reads selected metadata and optionally router registry namespaces.
# Creates only this new private output, never profiles or a memory directory:
python -B scripts/SharedWorkspace.py native-preview --spec "C:\PATH\plan.workspace.local.json" --output "C:\PATH\plan.native.local.json"
# AFTER qualification and explicit approval of the saved capsule; all relevant writers closed:
python -B scripts/SharedWorkspace.py native-install --spec "C:\PATH\plan.workspace.local.json" --approval "C:\PATH\plan.native.local.json" --approved --writers-closed
# B-only removal; retains B data, A routing and shared memory:
python -B scripts/SharedWorkspace.py native-remove-b --install-dir "C:\PATH\NewLauncher" --approved --writers-closed
# Full owned-additions rollback; selected memory key restored, B data/metadata retained:
python -B scripts/SharedWorkspace.py native-rollback --install-dir "C:\PATH\NewLauncher" --approved --writers-closed
```

Protocol registration requires spec consent plus `--approve-protocol` at installation and rollback. It adds only
new HKCU router namespaces and one RegisteredApplications value, refusing existing ownership. It leaves the
classic `claude` registration and UserChoice intact; choosing a default handler is manual. Removal of B retains
this router for A. `--delete-owned-b-data` is a separate explicit deletion option on B removal only.
Receipts bind approved paths, physical identities and file hashes; changed ownership refuses recovery.
Partial operations may require manual review: write/journal crashes and arbitrary external-editor races are not
transactional CAS guarantees. Checksums detect corruption, not hostile receipt authors. Rollback retains launcher
directories, locks, journals and B roots rather than deleting unrecorded additions. No official package uninstall.

## Existing mechanism

The launcher resolves the official installed MSIX executable dynamically through
`Get-AppxPackage`, then uses a distinct `--user-data-dir` for each profile.
`CLAUDE_CONFIG_DIR` is passed to the child process for a configured Code root;
the parent environment is preserved. Running Desktop processes retain their
existing environment. Effective loading and identity must be observed in each
Desktop window, not inferred from launcher arguments.

Project folders stay where they are. Existing project instructions and settings
are already common on disk. Selected project memory requires an explicit mapping;
credentials, account logins, connectors and complete config roots stay separate.
There is no cloud conversation merge, account rotation or global root sharing.

## Routing an explicitly selected login

The [routing guide](docs/PROTOCOL-ROUTING.md) describes the current v2 contract.
The following examples are for an already inventoried and authorized installation
whose manifest declares the names A and B. They are not an installation recipe.

```powershell
# One deliberate B login. Verify the browser account; close stale login tabs.
& "$env:USERPROFILE\ClaudeProfiles\bin\Arm-ClaudeLogin.ps1" -Profile B -Launch

# To intentionally route A, use its declared name. Never use default as A.
& "$env:USERPROFILE\ClaudeProfiles\bin\Arm-ClaudeLogin.ps1" -Profile A

# Explicitly disarm; this does not select or launch A.
& "$env:USERPROFILE\ClaudeProfiles\bin\Arm-ClaudeLogin.ps1" -Profile default
```

Choose only ONE arm for ONE login flow. An intent expires after five minutes and
is bound to the exact manifest. It is consumed before discovery or launch.
Missing, legacy, expired, consumed or inconsistent intent refuses dispatch;
there is no fallback account. An expired outstanding intent must be explicitly
disarmed before a new named arm. A consumed intent permits deliberate new named
arming. Neither path automatically retries a callback.

Arming does not change protocol registration. The intent is not correlated to
the outgoing OAuth request: a delayed old callback may consume a new arm.
Browser focus is a hypothesis to test, not account selection or state/PKCE proof.
Consumption and launch-request events do not establish authentication success.

## Passive diagnosis

```powershell
# Review the script first; this command observes only, with no live activation.
powershell -NoProfile -File scripts\Test-ClaudeRouting.ps1
# Optional: specify a previously inventoried metadata parent.
powershell -NoProfile -File scripts\Test-ClaudeRouting.ps1 -InstallDir 'D:\ClaudeProfiles'
```

The default emits one expurgated `DIAGNOSTIC_PASSIVE` JSON event. `-NoPing` remains
accepted for compatibility; both forms are passive. There is no live-probe option.
No process command lines, old logs, raw registry values or personal paths are
printed. Missing/busy locks and unavailable metadata remain unknown.
`dispatch=not_probed` always applies. Package presence, UserChoice classification
and readable metadata do not prove which running Desktop receives a callback.

New route.log lines contain fixed event codes and target kinds only. Historical
logs and OS/Claude command-line telemetry may contain secrets; do not publish
old logs or use raw process dumps for diagnosis. See the guide for event meanings.

## Setup and removal boundaries

Setup's legacy profile parameters remain for compatibility; their full execution is blocked.
The new explicit wrapper is `-NativeSpec ... -NativePreview ...` for capsule preparation, or
`-NativeSpec ... -NativeApproval ... -Approved -WritersClosed` for installation after qualification.
`-ApproveProtocol` supplies separate protocol consent. The private spec controls all paths; legacy path switches
do not configure the native candidate. No stock-path inference or adoption of an existing installation.

Uninstall's candidate requires `-Native -InstallDir ... -Approved -WritersClosed`; add `-Rollback` for full recovery,
or separately approve `-RemoveData` for B-only deletion. `-Profile` and `-KeepRouting` are refused in native mode.
Default invocation refuses cleanup. No deletion inferred from stock names; data retention is the default.
No forced logout/restart, profile migration, blanket config link or app copying.

Historical upstream observations concern Cowork VM placement and shared-HOME
collisions. Requalify on the installed build before relying on them. Two
simultaneous Cowork VMs are outside this fork's acceptance scope.

## Development and evidence

PowerShell launch/routing scripts target Windows PS5.1 and PS7 without admin
rights. Python 3.12+ runs the process fixture harness and reviewed bridge preparation. Existing runtime scripts do not install dependencies.

```powershell
python -B tests/Run-SharedWorkspaceTests.py
python tests/Test-RoutingProcesses.py
powershell -NoProfile -File tests\Test-RoutingDiagnostic.ps1
pwsh -NoProfile -File tests\Test-RoutingDiagnostic.ps1
```

The commands above reproduce synthetic qualification; real Desktop gates remain unexecuted.
These existing tests use synthetic accounts and owned TEMP metadata. They do not launch
Claude. CI runs parser/analyzer/routing regressions and the shared-workspace fixture matrix; Q1/Q2 and D1 runtime
receipts remain separately qualified. Actual A/B identity, configuration,
shared memory and removal remain local acceptance gates. PR #1 stays draft.

## Credits and license

Forked from [vodongha/claude-desktop-clone](https://github.com/vodongha/claude-desktop-clone).
The `--user-data-dir` technique and prior UserChoice-hash work are credited to
[Zoltak-Dev/ai-multi-instance](https://github.com/Zoltak-Dev/ai-multi-instance).
This fork does not implement UserChoice-hash automation. See [MIT](LICENSE).
It does not modify, repackage or redistribute Claude binaries.

## Tiếng Việt — trạng thái

Bản fork đang kiểm thử định tuyến và chẩn đoán thụ động. Chưa xác minh cài đặt
an toàn hoặc hai tài khoản Desktop thực tế. Giữ nguyên tài khoản A và thư mục
project; không chạy Setup/Uninstall để sửa nhanh. Chỉ định tên profile khi đăng
nhập; `-Profile default` chỉ huỷ kích hoạt định tuyến. Xem ledger và hướng dẫn
định tuyến trước khi thao tác trên cài đặt thật.
