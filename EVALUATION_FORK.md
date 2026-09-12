# Evaluation Fork

This fork is for isolated local evaluation of upstream
[`diivi/aseprite-mcp`](https://github.com/diivi/aseprite-mcp).

Functional source remains unmodified at the pinned upstream commit
`90d1696a7e41edff89bbd0823ae6a5f86c114bcc`, apart from the CI and test-harness
changes described below. Do not run this fork outside a sandbox.

The external launcher must clear the environment, deny network access, hide
`HOME` and repositories, and expose only a disposable art workspace.

## CI status

GitHub Actions CI is **enabled**. The previous `Build and Push Docker Image`
workflow (which logged into GHCR, pushed multi-arch images and requested
`packages: write`) has been removed and replaced by
`.github/workflows/live-aseprite-integration.yml`.

The replacement runs the full pytest suite against a real, self-compiled
Aseprite and publishes nothing:

- triggers: push to `main` and `workflow_dispatch` (this fork works directly on
  `main`, so there is no pull-request trigger);
- permissions: `contents: read` only — no registry login, no push, no
  `upload-artifact`, no `docker save`, and no Actions cache holding the
  compiled Aseprite binary;
- `actions/checkout` is pinned to a full commit SHA and is the only action
  used; the image build and the test run go through the plain Docker CLI to
  keep the supply-chain surface minimal.

## Ephemeral test image

`Dockerfile.ci` is a multi-stage image built only inside the runner and
discarded with it. It is never tagged for, or pushed to, any registry, and it
does not redistribute Aseprite in any form.

| Pinned input | Value |
| --- | --- |
| Base image (both stages) | `ubuntu@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254` (24.04) |
| uv | `ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1` |
| Aseprite source | `v1.3.18.3`, SHA-256 `268693d1750c4f9f61c9c866f10b993ddfc88424c9dead2a2f66ebb7576b192e` |
| Skia (official prebuilt) | `m124-08a5439a6b` / `Skia-Linux-Release-x64.zip`, SHA-256 `a327e89b244f24cecaa34eb37544bae00d447b96c583d26ed29d6a3ad2e8a8b8` |

Both archive checksums are verified with `sha256sum --check --strict` before
extraction. The Skia tag is not guesswork: `laf/misc/skia-tag.txt` inside the
1.3.18.3 source tree names `m124-08a5439a6b` as the expected build, so using
the official prebuilt archive avoids compiling Skia while staying on the
version combination upstream itself tests. Aseprite is compiled from source
because upstream distributes no prebuilt Linux binary; the build disables the
updater, news and websocket features to cut compile time.

Python dependencies come from the committed `uv.lock` via `uv sync --frozen`
(the dev group is included, so `pytest` is present). Nothing is installed
through `curl | bash`, and the test stage runs as UID 10001.

## Test-run sandbox

The suite runs with:

```
--network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=1g
--cap-drop ALL --security-opt no-new-privileges
HOME=/tmp/home ASEPRITE_PATH=/opt/aseprite/aseprite
```

A short-lived `Xvfb` display is started inside the container because the Skia
laf backend may expect an X connection to be available; it listens on a UNIX
socket only (`-nolisten tcp`) and the container has no network at all.

MCP functionality and the project's security behaviour are unchanged. The only
test-suite addition is `tests/test_mcp_registry.py`, a smoke check that the
FastMCP server still exposes the full, uniquely named, documented tool set.

The Steam/SteamCMD entrypoint in the regular `Dockerfile` is untouched and is
**not** used by CI: no Steam credentials or secrets are involved anywhere in
this workflow.
