# Evaluation Fork

This fork is for isolated local evaluation of upstream
[`diivi/aseprite-mcp`](https://github.com/diivi/aseprite-mcp).

Functional source started unmodified at the pinned upstream commit
`90d1696a7e41edff89bbd0823ae6a5f86c114bcc`. It has since diverged: building
the behavioural test suite surfaced defects that are fixed here and described
under "Fixes found by the test suite" below. Do not run this fork outside a
sandbox.

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

No X server runs inside the sandbox. `Dockerfile.ci` contains a build-time
smoke check that executes a Lua script through `aseprite --batch` with no
`DISPLAY` at all, so the assumption that the Skia laf backend works headless
is verified on every build rather than assumed.

## Coverage gates

The suite measures combined statement+branch coverage of `aseprite_mcp` in
the same run and enforces two floors, both from data produced inside that
run — no coverage service, no upload, no extra dependency:

- `--cov-fail-under=93` for the project total (mirrored as `fail_under = 93`
  in `pyproject.toml` so a local run fails identically);
- `scripts/check_file_coverage.py` for a per-file floor of 80% on every
  functional module under `aseprite_mcp/core/` and `aseprite_mcp/tools/`,
  with `tools/guide.py` held to 100%. Its exemption list is empty and a test
  asserts it stays that way.

The per-file step runs even when pytest failed, so one run reports both
problems, and it combines its status with pytest's rather than replacing it.

## Fixes found by the test suite

Writing behavioural tests against the real binary surfaced defects in the
upstream code. Each is fixed here with a minimal change and locked by a test.

**Security**

- `tools/quality.py` interpolated caller-supplied layer names straight into
  generated Lua table literals in `_parse_layer_frame_ranges` and
  `_parse_overlap_pairs`. A name carrying a quote could close the literal and
  append arbitrary script. Both now escape through `lua_escape`; the tests
  execute the generated literal inside Aseprite and assert it still holds
  exactly one entry of the expected length, with a canary file proving no
  payload ran.
- Coordinate fields in `draw_pixels`, `draw_pixels_at`, `draw_polygon`,
  `draw_path`, `draw_on_tile` and `set_tiles` were formatted into generated
  Lua without ever being forced to a number, which is the same primitive by
  another route. They now go through a shared `core.inputs` validator.
- The same validator turns a malformed structure (a JSON string, number or
  array where an object was expected) into a controlled error instead of an
  `AttributeError`/`TypeError` escaping the tool. Every `List[str]` argument
  was affected too: those reached `lua_escape`, which is `str.replace`.
- The preview server inherited `http.server`'s `0.0.0.0` default, publishing
  every exported sprite to the LAN, and tracked its child through a
  predictable, world-writable `/tmp/aseprite_mcp_preview_<port>.pid`. Any
  local user could plant a PID there and have `stop_preview_server` deliver
  `SIGTERM` to a process they did not own. It now binds `127.0.0.1`, keeps
  its PID file 0600 inside a per-user 0700 directory, and only signals a PID
  whose live argv still matches the recorded port and served directory.
- Caller-supplied counts and extents drove unbounded loops and allocations:
  `add_frames(count=2**31)` spins inside Aseprite allocating a frame per
  iteration, and a single `draw_rectangle` with a 2**31 side kept Aseprite
  busy for three minutes in testing. Frame counts are capped at 4096, drawn
  extents and canvas sizes at 8192 per side, and stroke width at 256.

**Correctness**

- `copy_frame` and `propagate_frame_to_range` accepted `overwrite=False` but
  still replaced the destination, because `Sprite:newCel` always replaces.
- `copy_frame` silently did nothing for an out-of-range target frame, and
  `copy_cel` for a source frame with no cel; both reported success anyway.
- `animation_sanitize(layer_order=...)` reported `reordered: true` while
  leaving the stack untouched. Its de-duplication table was keyed by the
  Aseprite layer wrapper, and those wrappers compare equal with `==` yet are
  distinct raw table keys, so every layer was appended twice and the second
  pass undid the first.
- The `esc()` helper in the generated quality reports had a quote branch that
  expanded to a no-op, so a layer name containing `"` produced a report the
  caller could not parse as JSON.
- `get_composite_pixel`/`get_composite_rect` and the analysis readers
  documented themselves as compositing every *visible* layer, but
  `Sprite:flatten()` merges hidden layers too, so a sprite with a hidden
  layer reported the colour of a layer nobody can see.
- `create_canvas` reported success when Aseprite exited 0 without writing the
  file, and `resize_canvas` when Aseprite silently ignored the new size.
- System font discovery used a flat `listdir`, so it found nothing on any
  Linux distribution (fonts live under `<type>/<family>/`).
- `tools/tilemap.py` carried its own colour parser that only understood
  `#RRGGBB`; it now shares `core.colors` with every other module.

The Steam/SteamCMD entrypoint in the regular `Dockerfile` is untouched and is
**not** used by CI: no Steam credentials or secrets are involved anywhere in
this workflow.
