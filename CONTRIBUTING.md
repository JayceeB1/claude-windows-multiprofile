# Contributing

Thanks for your interest. This is a small Windows tool, so a few ground rules keep it safe.

## Ground rules

- **Never touch credentials.** No script may read, log, copy or print a token, a login store or an identity file; compare
  hashes only. Credentials and account identity are never linked or copied between accounts, and a test asserts it.
- **Preview first.** Anything that writes needs explicit approval flags, a journal, and a rollback.
- **No admin rights, no dependencies.** PowerShell built-ins and the Python standard library only.
- **No personal data in the repository.** No `C:\Users\<name>` paths, no drive letters, no account names or e-mail
  addresses. Machine-specific notes go in `*.local.md` (git-ignored).
- **No Claude artwork.** Do not add Claude logos or icons; users supply their own.
- Keep the credits in [NOTICE.md](NOTICE.md) and the notices in [LICENSE](LICENSE).

## Workflow

1. Branch from `master`: `feature/...`, `fix/...`, `docs/...` or `chore/...`.
2. Run the checks (see [CLAUDE.md](CLAUDE.md#testing-changes)). Run the Python suite from a normal PowerShell, not from
   inside Claude or Codex: some tests skip inside a packaged process tree.
3. Open a pull request against `master`. CI (PSScriptAnalyzer plus the fixture matrix on Windows PowerShell 5.1 and
   PowerShell 7) must be green. Merge commits only.
4. Commit messages describe the change only: no tool or assistant attribution footers.

## Reporting a problem

State your Claude version (`Get-AppxPackage *Claude*`), Windows build, and what "Réparer Claude (A+B)" printed. Do not
paste logs, registry values or process command lines: they can contain secrets.
