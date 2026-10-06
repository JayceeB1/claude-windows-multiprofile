# REA qualification plan for Claude Desktop / Claude Code updates

## Status

Research/qualification plan only.

Originally drafted while GitHub Issues were disabled; they are now enabled. Remaining work is tracked in
[REA-A2 / issue #3](https://github.com/JayceeB1/claude-windows-multiprofile/issues/3). This plan alone does not install
REA or authorize adoption. The [packaged smoke receipt](REA-SMOKE-20261006.md) establishes a narrow synthetic result;
full adoption, native provider readiness and Claude comparison remain unqualified.

Primary upstream:

- REA: https://github.com/morluto/rea
- Claude Code releases: https://github.com/anthropics/claude-code/releases

## Why this is relevant

This project depends on concrete behavior of the shipped Windows Claude
application and Claude Code runtime:

- MSIX package discovery;
- Electron/Chromium profile isolation through `--user-data-dir`;
- per-profile `CLAUDE_CONFIG_DIR`;
- `claude://` login callback routing;
- profile-local memory/config state;
- session and permission behavior across updates.

Release notes are useful, but they do not prove what changed in the actual
artifact installed on Windows.

REA is interesting because it can inspect packaged applications and
Electron/JavaScript artifacts and can produce evidence linked to the shipped
artifact rather than only summarizing source or changelogs.

The desired role is therefore:

```text
old Claude artifact
        │
        ├──── static/package inspection
        │
new Claude artifact
        │
        ▼
      REA diff
        │
        ▼
candidate changed surfaces
        │
        ▼
targeted multiprofile tests
        │
        ▼
human-readable report + machine-readable receipt
```

REA is an **investigation tool**, never the authority deciding whether
multi-profile isolation is safe.

## Qualification goal

Determine whether REA can reliably answer bounded questions such as:

1. Which packaged files changed between two Claude Desktop versions?
2. Did Electron bootstrap, deep-link handling, profile-path logic, IPC or
   configuration access change?
3. Did relevant JavaScript bundles or native helpers change?
4. Can a REA finding be traced to concrete artifact evidence?
5. Does REA correctly say **unknown** when the artifact does not establish a
   behavior?
6. Can the resulting hints reduce the amount of blind regression testing after
   an update?

## Security boundary

REA's own documentation is explicit that its provider bridges are **not a
sandbox**. Treat every inspected binary/package as untrusted input and every
runtime observation as privileged local execution.

For this repository:

- start with **static analysis only**;
- prefer WSL for the first qualification when practical;
- use disposable copies of packages/artifacts;
- do not provide REA with production credentials, cookies, private profile
  directories or unrelated user data;
- do not attach REA to a live authenticated Claude process during the first
  qualification;
- never publish proprietary/private artifacts or captured secrets in GitHub
  evidence.

Runtime/Electron observation is a separate later gate.

## Phase A — ground-truth smoke

Before touching Claude artifacts, validate REA on targets where the answer is
already known.

Use at least:

- one small ELF built from known source;
- one small PE built from known source;
- one small Electron/package fixture with a deliberate version delta.

Questions should have mechanical ground truth, for example:

- identify a known function;
- identify one known call/reference;
- detect one added/removed resource;
- detect one intentionally changed configuration path;
- distinguish unchanged from changed files.

Record:

```text
target_sha256
rea_version
provider
provider_version
question_id
expected
observed
evidence_refs
classification
duration_ms
notes
```

Allowed classifications:

- `CORRECT`
- `PARTIAL`
- `FALSE_POSITIVE`
- `FALSE_NEGATIVE`
- `UNKNOWN_CORRECTLY_REPORTED`
- `UNSUPPORTED`

## Phase B — Claude package comparison

Only after Phase A is acceptable, compare two archived Claude Desktop package
versions.

The comparison should be artifact-identity driven:

```text
artifact A SHA-256
artifact B SHA-256
REA version/provider
exact operation/parameters
result/evidence ids
```

Investigate only surfaces relevant to this project:

- MSIX/AppX manifest changes;
- executable / native helper inventory;
- Electron/ASAR/resource changes;
- deep-link / `claude://` handling;
- profile path selection;
- config/storage path use;
- launch flags;
- IPC/bootstrap code;
- update-related changes that can affect multi-instance behavior.

Do not infer runtime behavior from filenames or strings alone.

Every conclusion must be one of:

- **OBSERVED** — directly established by artifact evidence;
- **INFERRED** — plausible interpretation of observed evidence;
- **UNKNOWN** — not established by the inspected artifact.

## Phase C — targeted regression map

Translate artifact findings into existing project checks.

Example:

```text
REA finding
  "deep-link bootstrap changed"
        ↓
targeted test
  Test-ClaudeRouting.ps1
        ↓
result
  PASS / FAIL
```

Useful mappings may include:

| Changed surface | Targeted project validation |
|---|---|
| MSIX package layout | launcher/package discovery tests |
| Electron bootstrap | concurrent-profile launch smoke |
| deep-link handler | `Test-ClaudeRouting.ps1` |
| profile/config path logic | per-profile isolation tests |
| session/permission-related CLI behavior | Claude Code compatibility qualification |

REA findings should reduce test-search space, not replace tests.

## Phase D — optional runtime observation

Runtime observation is **not part of initial adoption**.

If static qualification is strong enough, a later experiment may evaluate
passive Electron/browser/process observation.

Requirements before that experiment:

- disposable test profile;
- no personal account/session;
- explicit process identity;
- bounded observation scope;
- no arbitrary interaction outside the declared target;
- redacted, reviewable evidence;
- clean detach/cleanup.

## Adoption gate

REA becomes an approved optional investigation tool for this repo only if all
of the following hold:

1. Ground-truth smoke demonstrates useful precision on the target classes.
2. Findings preserve artifact identity and are auditable.
3. Observations, inferences and unknowns remain distinguishable.
4. A Claude package comparison produces at least one useful test-targeting
   result without material false-positive noise.
5. The workflow does not require unsafe access to live user profiles.
6. The maintenance cost is lower than the regression-testing effort it saves.

Possible verdicts:

- `ADOPT_STATIC_ONLY`
- `EXPERIMENTAL`
- `REJECT_NO_SIGNAL`
- `REJECT_SECURITY_BOUNDARY`

There is no automatic promotion from static-only to runtime observation.

## One-command target

If adopted, prefer one small wrapper such as:

```powershell
python tools/qualify_rea.py --old <artifact-a> --new <artifact-b> --out <receipt-dir>
```

The exact implementation is intentionally unspecified until the manual
qualification proves value.

The wrapper should:

- auto-detect REA readiness;
- print a clear preflight;
- fail closed;
- preserve raw outputs;
- emit one machine-readable receipt;
- never install system dependencies silently.

## Non-goals

- no decompilation for curiosity without a project question;
- no bypass of Claude security/permissions;
- no credential/session extraction;
- no modification of Anthropic binaries;
- no replacement of project regression tests;
- no automatic acceptance of upstream README claims;
- no mandatory REA dependency for normal use of this repository.

## First micro-slice

One objective only:

> prove that REA can correctly detect a known version delta in a disposable
> packaged fixture and preserve auditable evidence.

Do not start with Claude itself.

If that PASSes, proceed to one archived Claude package pair.


## Current qualified boundary — 2026-10-06

Imported from documentation PR #2 without resetting this fork's implementation branch. REA 4.0.1 was evaluated in
an isolated TEMP prefix with lifecycle scripts disabled and redirected home/cache paths, not globally configured.
The packaged fixture subcase and independent reproduction are CORRECT; full verdict EXPERIMENTAL. File hashes and
main.cjs delta are traceable; semantic node churn is not a changed-file count. Native ELF/PE and Claude pair NOT_RUN.
The test-only Run-ReaPackagedSmoke.py accepts an installed pinned tool prefix, generates its own fixtures and installs
nothing. It is not the future arbitrary-artifact qualification wrapper. Keep REA optional and the native multiprofile
adapter track independent. Native 8.3 remains NOT_RUN. Full results/limitations are in the linked dated receipt.
