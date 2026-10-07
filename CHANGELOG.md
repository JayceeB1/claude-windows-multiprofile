# Changelog

All notable changes. Format based on [Keep a Changelog](https://keepachangelog.com/); versions follow
[Semantic Versioning](https://semver.org/). `0.x` releases are experimental.

## [Unreleased]

### Changed
- Project presented as a standalone fork: new README, `NOTICE.md` crediting the lineage, English manual
  ([docs/MANUAL.md](docs/MANUAL.md)), French manual moved to `docs/fr/` with generic paths, technical reference moved to
  `docs/reference/`, dated reports moved to `docs/dev-log/`, `CLAUDE.md` rewritten, `CONTRIBUTING.md` added.
- Single trunk (`master`); the `develop` sync workflow is removed.
- `AUTHORS.md` added; Fred Nielsen is credited in `LICENSE`, `NOTICE.md`, the README and AUTHORS for the `claude://` routing design.

### Fixed
- The repair check words a detected Claude package update as information ("Claude was updated since the last check, 2.26454.0.0 -> 2.26454.2.0"), no longer as if an update were pending. It compares the Windows package version, not the version in Claude's About box and not Claude Code.
- Receipt reconciliation compares B's root to its canonical parent plus its name, so 8.3 short or aliased path prefixes
  (as on CI runners) are no longer read as a redirection.
- A routing marker that is `consumed` or `disarmed` no longer blocks receipt reconciliation, B removal or registration
  repair; only an `armed`, legacy or unreadable one does.

## [0.1.0] - not yet released

First experimental release of this fork's feature set, validated on one machine with two real accounts:

- Two accounts side by side, B with its own taskbar button and icon (explicit AppUserModelID).
- `claude://` login router visible in the Windows default-apps picker, guarded against MSIX registry/AppData
  virtualization (the guard walks the ancestor process chain).
- Shared configuration and Claude Code session list between A and B through junctions and file symlinks; credentials and
  identity never shared.
- `Repair-ClaudeProfiles.ps1` (check, update detection, repair), `Connect-ClaudeProfile.ps1` (guided re-login of B),
  `Install-ClaudeTools.ps1` (desktop shortcuts).
- Ownership-receipt reconciliation (`native-reconcile`) for B roots recreated outside the receipt's view.
- English and French manuals, fixture test suites and CI on Windows PowerShell 5.1 and PowerShell 7.

Known gaps: a real Claude update and a real guided re-login have not been exercised yet (fixtures only); the base install
is still a multi-step, preview-first procedure rather than a single installer.
