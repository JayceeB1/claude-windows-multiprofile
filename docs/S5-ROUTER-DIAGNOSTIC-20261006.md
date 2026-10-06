# S5 discriminating router diagnostic — 2026-10-06

Scope: read-only Windows registration/association observations and documentation.
No router installation/repair, association write, notification replay, callback arm,
URI activation, B launch, A stop/logout, package mutation or global collection.
The supplied memo was reviewed as research input; its instructions did not expand authorization.

## Post-restart baseline

The operator restarted the machine and still sees only official Claude in the protocol picker.
The registered-app deep link had previously opened only the general Default Apps page.
Before/after package versions are 2.19675.1.0; PE FileVersion is 2.19675.1 and observed
embedded Code executable directory is 2.1.288. No observed update explains the result.
All 19 owned file identities/hashes match; router registry matches the installation receipt.
Shell name/executable resolution remains successful, and enumeration still returns both
the router and Claude with IsRecommended S_OK. This does not prove Settings eligibility.
Known A singleton is present after restart; B singleton is absent and no callback intent
file is present. Neither singleton nor process presence proves account authentication.
The performed session renewal did not suffice; a unique cause or absence of all caches is not proved.

## Scheme, handler and application are different identifiers

| Subject | Read-only observation | Bound conclusion |
| --- | --- | --- |
| `HKCU\Software\Classes\claude` | Present; default `URL:claude` REG_SZ; `URL Protocol` empty REG_SZ | Actual scheme declaration exists |
| `HKLM\Software\Classes\claude` | Absent in native observer view | No machine declaration at this inspected path/view |
| `HKCR\claude` | Same observed declaration as HKCU | Merged Classes view contains the scheme |
| Scheme `shell\open\command` | Absent in inspected HKCU/HKLM/HKCR paths | Does not by itself invalidate a separately registered handler |
| `ClaudeShim.claude` | HKCU/HKCR ProgID, URL marker, display metadata, own executable command and `%1` | Separate classic handler registration; not the scheme name |
| `RegisteredApplications\ClaudeShim` | HKCU REG_SZ -> `Software\ClaudeShim\Capabilities` | Correct name for the per-user registered-app deep link |
| Router capabilities | `claude=ClaudeShim.claude`; ApplicationName `ClaudeShim` | Handler advertised for the existing scheme |
| Official package | Registered Claude MSIX 2.19675.1.0; application Id `Claude`, executable `app\Claude.exe`, EntryPoint `Windows.FullTrustApplication` | Packaged registration route, distinct from router's classic capabilities |
| Official manifest | `windows.protocol`, `uap3:Protocol Name="claude" Parameters="&quot;%1&quot;"` | Explicit MSIX declaration of this same scheme |

The visible official app and missing router use different registration mechanisms.
Who originally wrote the classic HKCU scheme declaration is UNKNOWN: current registry contents
do not establish their author. The MSIX declaration does not establish that it wrote that key
or that profile/file/registry virtualization caused the picker discrepancy.

A bounded lookup at the presumed legacy Windows.Protocol ContractId path for this exact package
found no key in HKCU/HKLM; that path assumption does not prove missing MSIX registration.
`Classes\Applications\ClaudeLoginRouter.exe` and `Classes\Applications\Claude.exe` are both absent
in the inspected HKCU/HKLM views. This is not a demonstrated differentiator requiring a router write.

## Windows App SDK comparison

Current Microsoft sources were reread; their Git blob identities match the supplied memo:
Association.cpp `016a799362ef38db450296bb2a477e8b0cc54cc1`,
ActivationRegistrationManager.cpp `13219363980bff8918af0f95b18dcaa50c3bb9e8`.

[RegisterForProtocolActivationInternal](https://github.com/microsoft/WindowsAppSDK/blob/main/dev/AppLifecycle/ActivationRegistrationManager.cpp)
first calls RegisterProtocol, then creates its handler ProgID/verb/application/capability mapping.
[RegisterProtocol](https://github.com/microsoft/WindowsAppSDK/blob/main/dev/AppLifecycle/Association.cpp)
uses HKCU and returns without writing when the scheme and its URL Protocol value already exist.
That existence condition is met on this host. The fork omits a separate scheme-registration step,
but the corresponding host declaration is NOT missing. Adding or repairing the real `claude` key
is therefore not justified by this comparison. HKLM/admin is not established as required.

Other differences remain structural, not causal: the SDK derives App/ProgID names and a
WindowsAppRuntimeApplications capabilities location, whereas the fork uses its own names/location.
The SDK adds OpenWithProgids for file extensions, not for its protocol branch. Its association
notification uses SHCNF_IDLIST (0), also used by the fork. No fake browser/file associations proposed.

## Effective association — new API evidence

Called only IApplicationAssociationRegistration::QueryCurrentDefault, with `claude`,
AT_URLPROTOCOL=1, AL_EFFECTIVE=1. COM creation and query returned S_OK; output is `Undecided`.
Additional read-only AL_USER and AL_MACHINE queries each returned `0x80070483` with no output.
No setter, ClearUserAssociations, handler Invoke or ShellExecute was called.

The returned `Undecided` class exists in HKLM/HKCR and points to the Windows OpenWith executable
with a DelegateExecute GUID. It is a system selection fallback, not our handler or the official app.
Thus absent UserChoice was insufficient evidence to name the effective handler; the API now provides
the effective fallback. This does not explain why the picker admits only one of two enumerated candidates.
The API can also return legacy commands; no returned string is blindly assumed an app ProgID.
[Microsoft API contract](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-iapplicationassociationregistration-querycurrentdefault).

## One proposed next experiment — targeted Settings observation

Historical preparation status: PREPARED / NOT_RUN, before the user subsequently authorized
the tool/elevation and performed the capture manually. Results are recorded below.
No causal correction is yet justified. Observe the consumer with one short Procmon capture
instead of writing more registry entries or restarting Windows.

1. Use signed Microsoft Process Monitor from the [official source](https://learn.microsoft.com/en-us/sysinternals/downloads/procmon).
   No Procmon executable was resolved on the current PATH and none of its known process names was running;
   this was not an exhaustive installed-tool inventory. Download/use and elevation were subsequently authorized.
2. Confirm the selected version's local help supports capture-disabled startup (normally `/NoConnect`)
   before starting it. Do not launch ordinary recording and then filter it. If startup suppression cannot
   be verified, stop. No boot logging, profiling, network capture, existing-instance termination or silent EULA acceptance.
3. While capture is disabled, filter to the current SystemSettings.exe PID and registry read operations
   RegOpenKey, RegQueryValue, RegEnumKey and RegEnumValue. Disable filesystem/network/process activity classes.
   Scope paths to the own RegisteredApplications value/shared parent enumeration, own Capabilities tree,
   own ProgID, actual `claude` declaration and UserChoice, plus the observed Undecided class. Include only
   their exact HKCU/HKCR/HKLM forms and the equivalent current-user HKU paths; never include the entire Classes,
   AppModel, registry, profile or WindowsApps trees. Do not filter out SUCCESS or NOT FOUND results.
4. Enable and verify Drop Filtered Events before recording. Ordinary Procmon display filters are
   non-destructive and do not bound retained data. Verify the process/path/operation rules act together;
   broad default Include rules must not bypass them. If retention cannot be bounded, stop without capture.
5. Capture for at most 20 seconds: open the registered-app route and then the `claude` picker, select nothing,
   stop immediately. One pass only. No OAuth flow, callback, B launch, account or project interaction.
6. Keep raw PML/configuration privately outside the repository or in an ignored location. PML may retain
   process metadata in addition to filtered events; do not export process trees, command lines, environments,
   stacks or unrelated data. Tool/kernel observation is not claimed globally absent merely because retained
   events are filtered. Publish only an allowlisted summary of operation, normalized relevant path, result,
   counts and relative time. No raw PML/CSV screenshots or traces in Git/PR/issues.

Question: does Settings consult the router's capabilities/ProgID, and what read/result differs from the
visible official candidate? Missing optional values alone do not prove rejection. No events may reflect
cache, filter coverage or a broker. Do not automatically widen capture to all processes or AppModel storage;
an unobserved broker remains UNKNOWN and requires a separately justified scope before any extension.

Completion of this diagnostic slice does not close the native Settings gate or two-account acceptance.
Native 8.3 and B runtime/configuration/memory/removal gates remain NOT_RUN.

## Authorized operator-controlled capture — result

The user approved Procmon use/elevation, then chose manual guidance after native input failed.
Microsoft Procmon64 4.11 was downloaded into a unique private TEMP directory; Authenticode is Valid,
signer Microsoft Corporation. The executable's embedded help confirms /NoConnect suppresses automatic
collection. The initial hidden preparation launch had no targetable window; a visible /NoConnect launch
provided a window showing No events (capture disabled). No /AcceptEula, boot logging, notification replay
or router repair was performed. Computer Use was stopped following a reported physical Escape press;
subsequent filter/capture/save operations were performed by the operator, not by automation.

The supplied filter screenshot confirms PID 36912 and four registry-read operations. The operator
confirmed the added path filters, Drop Filtered Events, stopped recording and saved displayed events
as CSV into the private TEMP directory. These are OPERATOR_CONFIRMED steps; the complete filter state
and recorder start/stop timing were not independently captured. The manual trigger was the protocol
picker from the already open Default Apps page; the registered-app deep link was not replayed in this pass.

CSV analysis: 10,020 rows, all SystemSettings.exe PID 36912, all within the four allowed read operations
and the recorded registration/scheme path scope. Retained event span is 7.8586995 seconds; this is not
independent proof of the recorder's total wall time. No raw CSV/PML, other application names, command
lines, environments or screenshots of event data are published. Private receipt retains the CSV hash.

| Observation | Captured Settings consumer | Direct read-only observer after capture |
| --- | --- | --- |
| HKCU RegisteredApplications | 816 distinct successful enumerated value names, four passes; no ClaudeShim token in any retained path/detail | 817 values in both 32/64-bit views; ClaudeShim present, enumeration index 0 at read time |
| Enumeration index 0 | Four successful entries, none named ClaudeShim | ClaudeShim at index 0 at read time |
| HKCR claude open | Nine NAME NOT FOUND results, Desired Access Maximum Allowed | Opens succeed with both READ and MAXIMUM_ALLOWED in both views |
| HKCU Classes claude | Nine successful opens; default value read twice; URL Protocol length negotiation observed | Declaration still present |
| Own ProgID/capabilities | Zero retained accesses or name mentions for ClaudeShim | Exact installed registration and 19 file identities/hashes still match receipt |
| Effective association | Not changed by the recording | QueryCurrentDefault again returns S_OK / Undecided; no callback intent present |

Of the rows, 9,993 concern RegisteredApplications and 27 the actual scheme. BUFFER OVERFLOW and
NO MORE ENTRIES occur during enumeration/length negotiation; they are not independently rejection
causes. Missing optional FriendlyTypeName is likewise not a causal diagnosis. The visible official
MSIX candidate's AppModel lookup was outside this path allowlist and was not observed.

A limited-query handle reports Settings package identity
`windows.immersivecontrolpanel_10.0.8.1000_neutral_neutral_cw5n1h2txyewy`.
This differs from the unpackaged direct observer. The measured visibility/access discrepancy is
consistent with a consumer-context difference; package identity does not prove registry virtualization,
a specific cache mechanism, a Windows bug, or that machine-level registration would fix it.
The two enumerations are from different contexts/times, not a simultaneous equality test.
No broker activity was captured and no automatic process/path expansion or second recording occurred.
Official Claude package remains 2.19675.1.0. Native Settings/two-account gates remain BLOCKED/NOT_RUN.

## One next minimal experiment proposed — independent neutral reader

Before any HKLM move or router change, compare the same exact values using a non-elevated Windows
PowerShell opened manually from Start, outside the Codex-created process tree. This tests whether
the direct observer's parent context affects the baseline. It is a single read-only experiment;
no new capture, package install, callback, profile operation or framework is needed.

```powershell
reg.exe query "HKCU\Software\RegisteredApplications" /v ClaudeShim /reg:64
reg.exe query "HKCU\Software\RegisteredApplications" /v ClaudeShim /reg:32
reg.exe query "HKCR\claude" /v "URL Protocol" /reg:64
reg.exe query "HKCR\claude" /v "URL Protocol" /reg:32
```

If that neutral reader cannot see these values while the Codex-side reader can, the observer/context
boundary is further localized. If it sees them, the discrepancy is narrower to Settings/its execution
context. Neither outcome alone identifies a particular virtualization mechanism. Proposal only;
this independently launched reader remains NOT_RUN. No correction to the real registration is applied.
