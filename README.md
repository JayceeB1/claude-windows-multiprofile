# Claude Windows multiprofile

This fork prepares two official Claude Desktop windows with separate account data
and Code configuration roots, using the same existing project folders and
explicitly selected project memory. Preserve the working account A in place;
add account B without migrating projects or requiring worktrees.

**Delivery status:** routing and the passive diagnostic are qualified on fixtures.
Safe additive installation, memory adoption and two-Desktop acceptance remain
unfinished. Follow the [ledger](docs/SHARED-WORKSPACE-LEDGER.md) and
[roadmap](docs/SHARED-WORKSPACE-ROADMAP.md). Do not run the current Setup or
Uninstall against the working installation before the corresponding ownership,
preview and rollback gates are delivered and the local operation is authorized.

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

Current Setup supports `-Profile`, `-DefaultProfile`, per-profile `-DataDir` and
`-ConfigDir`, `-InstallDir`, `-LoginShortcuts` and `-NoProtocolRouting`. These are
existing implementation parameters, not proof of safe adoption of A.
`-DefaultProfile` selects stock-path construction at setup time; it does not
identify A's actual data/config provenance and is unrelated to armer disarming.
Setup currently replaces files, manifests and shortcuts. Its registration writes
need explicit scope and backups. Do not rerun it as a routing repair shortcut.

Current Uninstall is not ownership-qualified for custom A or shared memory.
Do not infer safe deletion from a folder name or use `-RemoveData` as cleanup.
The planned removal retains data by default and checks ownership and conflicts.
No forced logout/restart, profile migration, blanket config link or app copying.

Historical upstream observations concern Cowork VM placement and shared-HOME
collisions. Requalify on the installed build before relying on them. Two
simultaneous Cowork VMs are outside this fork's acceptance scope.

## Development and evidence

PowerShell launch/routing scripts target Windows PS5.1 and PS7 without admin
rights. Python 3.12+ runs the process fixture harness; the future reviewed bridge
may have its own prerequisites. Existing runtime scripts do not install dependencies.

```powershell
python tests/Test-RoutingProcesses.py
powershell -NoProfile -File tests\Test-RoutingDiagnostic.ps1
pwsh -NoProfile -File tests\Test-RoutingDiagnostic.ps1
```

These tests use synthetic accounts and owned TEMP metadata. They do not launch
Claude. CI runs its existing parser, analyzer and routing regressions; it does
not yet execute either new fixture matrix. Actual A/B identity, configuration,
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
