# S5 router invisible in the picker: MSIX virtualization — 2026-10-06

Result: RESOLVED for the protocol picker. After the router namespaces were written to the real
registry from a process tree with no packaged ancestor, the `claude` picker lists
"Claude Login Router" (marked "Nouveau") next to Claude. Selecting a default stays manual and
NOT_RUN. B launch, B configuration/memory loading and two-account acceptance remain NOT_RUN.

## Observation

Two observers read the same HKCU paths in one session.

| Read | Inside the Claude Desktop process tree | Process created by WMI (parent `WmiPrvSE.exe`) |
| --- | --- | --- |
| `HKCU\Software\Classes\claude\shell\open\command` (64 and 32-bit) | present, official versioned Claude.exe | absent |
| `HKCR\claude` `URL Protocol` | present | present |
| `RegisteredApplications\ClaudeShim`, `Software\ClaudeShim`, `Classes\ClaudeShim.claude` | absent | absent |

The operator's own PowerShell (pasted output) matches the second column. This is the neutral
reader proposed in the router diagnostic: the discrepancy was an observer-context effect.

## Cause

The installation and repairs had been executed from Codex, an MSIX package. HKCU and AppData
writes of a packaged process are redirected to a private per-package store:

- `AppData\Roaming\Claude-B` (an owned B root in the receipt) did not exist in the real file
  system; the folder was at `%LOCALAPPDATA%\Packages\OpenAI.Codex_*\LocalCache\Roaming\Claude-B`.
  `.claude-b` and `ClaudeProfiles` are outside AppData and were real.
- The router keys were absent from the real registry. The package hive
  (`...\SystemAppData\Helium\User.dat`) was locked while Codex ran and was not inspected.
- Consistent with the Procmon capture: Settings enumerated 816 HKCU values, the Codex-side
  observer 817, the extra value being `ClaudeShim`.

Fix: `scripts/Apply-RouterRegistration.py --apply --approved`, run by the operator from a
PowerShell opened from the Start menu, wrote exactly `desired_registry(install)` (receipt
`registry_after`, real registry previously empty, read-back equal). Picker observed by the operator.

## Inheritance finding: identity alone is not enough

Package virtualization is inherited by every descendant of a packaged process, although the
descendant has no package identity. Observed in the Code session: `python.exe` and `bash.exe`
returned `GetCurrentPackageFullName` = 15700 (no package) yet read the private registry layer;
the only packaged process was an ancestor `Claude.exe` (code 122) five levels up. A guard that
tests only the current process would have passed there.

## Guard (code)

`NativeWindowsIO.require_unpackaged_process()` refuses (`PACKAGED_PROCESS_REFUSED`) when the
process or any ancestor has a package identity; any unexpected result fails closed; ancestors that
cannot be opened count as unpackaged; a parent younger than its child (PID reuse) ends the walk.
It runs before any read or write in every `native-*` action of `SharedWorkspace.py`, in
`Repair-Registration.py` and in `Apply-RouterRegistration.py`. Verified live: refused from the
Claude Code session, expected to pass from a Start-menu PowerShell. Fixture tests patch the two
inspection functions; seven added cases cover packaged self, packaged ancestor, unopenable and
unpackaged ancestors, fail-closed codes, CLI/repair-helper refusal before any read, and the real
API shape. Windows matrix: 179 executed, 178 PASS, 1 explicit 8.3 SKIP.

## Still open

- The receipt records `AppData\Roaming\Claude-B` with a physical identity of the redirected
  folder. `NativeWorkspace.load` therefore refuses from any real process (`DIRECTORY_REQUIRED`),
  which blocks `native-rollback` and `native-remove-b`. Reconciliation needs a reviewed,
  explicit receipt transition after B is first launched from a real shortcut; not performed.
- The redirected `Claude-B` copy under the Codex package is not deleted or adopted.
- A stale private registry layer written by Codex may still hold the old router keys; it is not
  visible to Settings and was not modified.
- Launch B only from the generated shortcut or a real shell. Launching it from a packaged tree
  would again redirect its `--user-data-dir` under AppData.
