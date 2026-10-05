# claude:// routing: current v2 contract

This guide describes the source contract qualified on synthetic Windows fixtures,
not proof of the current user's Desktop/account installation. The authoritative
[ledger](SHARED-WORKSPACE-LEDGER.md) separates implementation, synthetic evidence
and actual installation acceptance. Preserve upstream [MIT](../LICENSE) credits.

## Explicit intent and account selection

A declared named profile in profiles.json supplies data/config paths. A is the
existing session to preserve; B is an addition. Names do not establish physical
ownership or identity. Inventory actual A before installation or protocol edits.
Do not assume stock paths, terminal environment or `isDefault` identifies A.

For an already qualified installation declaring A and B:

```powershell
# Arm B for one login and optionally open its configured window.
& "$env:USERPROFILE\ClaudeProfiles\bin\Arm-ClaudeLogin.ps1" -Profile B -Launch
# For a deliberate A login, choose its explicit declared name.
& "$env:USERPROFILE\ClaudeProfiles\bin\Arm-ClaudeLogin.ps1" -Profile A
# Disarm explicitly. No account is selected or launched.
& "$env:USERPROFILE\ClaudeProfiles\bin\Arm-ClaudeLogin.ps1" -Profile default
```

These are alternatives, not a sequence of login attempts. Initiate one browser
login flow at a time; verify its account and close stale login tabs before a new
attempt. `-Launch` opens a profile without changing a running process's environment.
`-Profile default -Launch` is invalid. Arming/disarming does not rewrite registration.

## Versioned one-shot metadata

The armer, disarmer and dispatcher share a nonblocking exclusive route.lock.
The lock file is retained after release; never delete a held lock. target.txt is
v2 JSON. Armed state records a declared profile, exact manifest SHA-256 and numeric
created/expires milliseconds with a five-minute interval. It contains no callback.
Missing or old default/path markers, malformed/inconsistent metadata and expired
intents refuse dispatch without fallback A. Changing manifest text invalidates
its binding, even if the parsed map would be equivalent.

The dispatcher writes a consumed tombstone BEFORE package discovery, argument
building or process launch, holding the lock through dispatch. Consumption does
not prove launch. A crash or failed discovery/launch keeps consumption; replay
refuses. An expired outstanding armed record blocks re-arm until explicit disarm.
Consumed state permits a deliberate new named arm; disarm is also available.
Recovery never automatically retries or silently changes the account.

Before-consumption death may leave a valid old intent. After-consumption death
leaves no replayable intent. If launch happens but its acknowledgment is lost,
consumption alone cannot distinguish launched from not launched. Fixture receipts
qualify that ambiguity; they do not promise exactly-once Desktop activation.
Mid-write power loss, noncooperating mutation and physical aliases need separate
qualification. Orphan sidecars require ownership-aware handling, not blanket deletion.

The marker is not correlated to the outgoing OAuth request. A delayed old callback
can consume a newly armed intent. Browser focus does not establish the outgoing
or returning account; state/PKCE belongs to the supported authentication flow.
Do not claim arbitrary simultaneous-login safety or automatic account rotation.

## Passive diagnostic

```powershell
powershell -NoProfile -File scripts\Test-ClaudeRouting.ps1
# -NoPing is compatible and has the same passive behavior.
powershell -NoProfile -File scripts\Test-ClaudeRouting.ps1 -NoPing
```

An optional `-InstallDir` names the metadata parent containing bin. Review the
script and inventory that path first. D1 tests have not invoked the user's
installed diagnostic. Default output is one JSON event with this closed schema:

| Field | Values / interpretation |
| --- | --- |
| version / event / mode | 1 / DIAGNOSTIC_PASSIVE / passive |
| snapshot | locked (read snapshot under an existing lock) or unavailable |
| reason | none, path_unavailable, lock_missing, lock_unavailable |
| manifest | readable (syntactic map only), missing, invalid, unknown |
| intent | armed, consumed, disarmed, missing, invalid, unknown |
| expiration | active, expired, invalid, not_applicable, unknown |
| binding | match, mismatch, not_applicable, unknown |
| protocolChoice | router, other, missing, unknown; only UserChoice observation |
| package | present, missing, unknown; only package-query observation |
| dispatch | not_probed, always |

No lock is created, no metadata written, no link activated, no process queried
or launched, no installed routing script imported and no route.log read.
The existing lock is opened read-only/exclusively for a short snapshot; this can
briefly contend with cooperating writers. Missing/busy locks are unknown, not
proof of handler failure. Metadata reads are bounded and reject reparse ancestors.
File access timestamps may change; fixture bytes and last-write times are preserved.
There is no live-probe option. A separately scoped future probe must refuse any
outstanding or uncertain intent before activation; it is not implemented here.

Package presence, router UserChoice, active expiration and hash match do not
prove OS delivery, a valid complete path plan, actual Desktop identity/config,
authentication or memory loading. No delay/new log line establishes those gates.

## New-log meanings and exposure boundaries

New lines follow `YYYY-MM-DDTHH:mm:ss event=CODE target=KIND`; CODE and KIND
come from closed lists. They do not include URL, profile name, path or exception.

| Event | Meaning |
| --- | --- |
| MISSING_URL / INVALID_URL | Callback input refused |
| ROUTE_BUSY | Exclusive lock unavailable; no dispatch |
| TARGET_READ_FAILED | Intent/manifest missing, invalid, expired, consumed or inconsistent; no fallback |
| RESET_FAILED | Consumption write failed; no launch |
| APP_DISCOVERY_FAILED / APP_NOT_FOUND | Discovery failed after consumption |
| ARGUMENT_BUILD_FAILED | Start-info construction failed after consumption |
| LAUNCH_REQUESTED | Launch about to be attempted, not confirmation |
| LAUNCH_FAILED | Launch boundary failed; consumption retained |
| DISPATCH_COMPLETE | Launch boundary returned and completion log succeeded; not authentication proof |

Target kinds are unknown/stock/profile in the logger's allowed schema; current
named dispatch uses profile and refusal before selection uses unknown. No default
account selection is implied by the legacy stock enum. A log write itself may
fail; absence of a line is inconclusive. Do not publish old logs: historical
URL/path logs, PowerShell debugging, OS command-line telemetry and Claude's own
logs are outside this sanitizer. The callback remains in the child command line.

## Registration, historical observations and installation gates

Setup currently writes router ProgId/Capabilities/RegisteredApplications and may
back up an existing classic command. Selecting the protocol handler in Windows
Settings is separate from arming. The upstream guide reported UserChoice, MSIX
and classic-key interactions and a chooser label of Console Window Host. Treat
that label and precedence behavior as historical observations to requalify on
the installed Windows/Claude build; a passive UserChoice read is not activation proof.
Do not compute or bypass a UserChoice hash as a repair, run a ping while armed,
print command lines, remove Squirrel folders or rerun Setup/Uninstall as a shortcut.

Safe additive Setup/Uninstall, actual A provenance, physical path identity,
selected memory and rollback are still pending. Protocol changes require an
explicitly scoped local trial with ownership and conflict-aware restoration.
Keep A's entry point, projects and session intact. Two simultaneous Cowork VMs
are outside scope. Historical VM-placement/shared-HOME observations are not
current-build proof. Nothing here promises provider-side session permanence.

## Credits

Fork lineage: [vodongha/claude-desktop-clone](https://github.com/vodongha/claude-desktop-clone).
The data-directory technique and prior UserChoice-hash work originate in
[Zoltak-Dev/ai-multi-instance](https://github.com/Zoltak-Dev/ai-multi-instance).
Other upstream prior art included
[sypnose-cloud/claude-desktop-multi](https://github.com/sypnose-cloud/claude-desktop-multi).
This unofficial fork launches the official installed app; it does not copy,
modify, repackage or redistribute it. Native multi-account support or changed
protocol handling may supersede this approach; requalify before delivery.
