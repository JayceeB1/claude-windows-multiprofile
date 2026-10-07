# Authors and acknowledgements

This project stands on the work of several people. Each is listed here with what they built, in order of lineage.

## vodongha: the original launcher

[vodongha/claude-desktop-clone](https://github.com/vodongha/claude-desktop-clone), June 2026.

Created the idea and the first working tool: resolving the installed MSIX executable dynamically, one `--user-data-dir` per
profile, shortcuts with stable icons, and the optional `CLAUDE_CONFIG_DIR` isolation layer. Everything else rests on it.

## Fred Nielsen (fredless): the login router

[fredless/claude-windows-multiprofile](https://github.com/fredless/claude-windows-multiprofile), July 2026.

Solved the hardest part of running several Claude Desktop accounts: making a browser sign-in callback (`claude://`)
land in the intended profile. He designed and shipped:

- the `claude://` handler with a one-shot, explicit intent and no silent fallback (`ClaudeOpenShim.ps1`);
- `Arm-ClaudeLogin.ps1`, to arm one profile for the next login;
- `Test-ClaudeRouting.ps1` diagnostics and the argument-quoting fix, with its unit test;
- the `profiles.json` contract shared by Setup, Uninstall and the router, and the reworked `Setup.ps1` / `Uninstall.ps1`;
- the protocol-routing guide, which documents the delivery chain and the traps found on the way.

Without this work there would be no reliable way to sign the second account in. The router in this project, and the guided
re-login built on it, descend directly from his design. Many thanks.

## JayceeB1 and contributors: this fork

Shared workspace (preview-first plans, ownership receipts, native candidate), separate taskbar identity for the second
account, shared configuration and Claude Code sessions, update repair and guided re-login, receipt reconciliation, the
English and French manuals, tests and CI.

## Technique and prior art

- [Zoltak-Dev/ai-multi-instance](https://github.com/Zoltak-Dev/ai-multi-instance): the `--user-data-dir` technique and the
  earlier UserChoice-hash work.
- [sypnose-cloud/claude-desktop-multi](https://github.com/sypnose-cloud/claude-desktop-multi): earlier work on running
  several instances.

## Licence

The project is under the [MIT License](LICENSE), which carries each copyright holder above. The full commit history, with
every original author, is preserved in this repository.
