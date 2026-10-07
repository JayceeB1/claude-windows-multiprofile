# Notice and attribution

This project, **Claude Desktop multi-account (Windows)**, is a fork. It exists because of the work below, and every
upstream copyright notice is kept in [LICENSE](LICENSE) (MIT).

## Lineage

| Project | Author | What this project builds on |
| --- | --- | --- |
| [vodongha/claude-desktop-clone](https://github.com/vodongha/claude-desktop-clone) | vodongha | The original multi-instance launcher: dynamic resolution of the MSIX executable, one `--user-data-dir` per profile, `Setup.ps1` shortcuts, the optional `CLAUDE_CONFIG_DIR` isolation layer. MIT. |
| [fredless/claude-windows-multiprofile](https://github.com/fredless/claude-windows-multiprofile) | Fred Nielsen (fredless) | The `claude://` SSO login router and its protocol-routing documentation, the base of the router in this project. |
| this repository | JayceeB1 and contributors | The shared workspace (preview-first plans, ownership receipts, native candidate), separate taskbar identity, shared configuration and Claude Code sessions, update repair, guided re-login, receipt reconciliation, French and English manuals, tests and CI. |

The full commit history of every ancestor is preserved in this repository, with its original authors.

## Prior art and technique

- [Zoltak-Dev/ai-multi-instance](https://github.com/Zoltak-Dev/ai-multi-instance): origin of the `--user-data-dir`
  technique and of the earlier UserChoice-hash work. This project does not implement UserChoice-hash automation.
- [sypnose-cloud/claude-desktop-multi](https://github.com/sypnose-cloud/claude-desktop-multi): earlier work on running
  several Claude Desktop instances.

## Trademarks and affiliation

"Claude" and "Anthropic" are trademarks of Anthropic, PBC. This project is independent: it is not affiliated with,
endorsed by or sponsored by Anthropic. It starts the officially installed Claude Desktop application as it is, and
does not modify, repackage, redistribute or reverse-engineer it. It ships no Claude logo or artwork; the second
account's icon is supplied by the user.

## Third-party notices

No third-party code is bundled. Python (standard library only), PowerShell and the Windows .NET Framework compiler are
used from the user's own machine.
