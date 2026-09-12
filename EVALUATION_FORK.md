# Evaluation Fork

This fork is for isolated local evaluation of upstream
[`diivi/aseprite-mcp`](https://github.com/diivi/aseprite-mcp).

Functional source remains unmodified at the pinned upstream commit
`90d1696a7e41edff89bbd0823ae6a5f86c114bcc`, except that CI is disabled.
Do not run this fork outside a sandbox.

The external launcher must clear the environment, deny network access, hide
`HOME` and repositories, and expose only a disposable art workspace.

GitHub Actions CI is intentionally disabled pending a decision on adoption and
security hardening.
