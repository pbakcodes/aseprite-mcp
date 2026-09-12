"""Path handling on the write-facing tools.

The server has no workspace root, so these tests pin down what it actually
guarantees rather than implying a confinement it does not implement:

* a path that still contains a `..` component *after normalisation* is
  rejected on every tool that writes to a caller-named path, before
  Aseprite is ever started. That is exactly the guarantee "a relative path
  can never resolve above the working directory";
* an interior `..` that cancels out (`a/../b.png`) normalises to a path
  that escapes nothing and is therefore allowed;
* absolute paths are accepted by design. This server has no workspace root
  and the caller names the file, so `/etc/x` is a legal request and
  `/tmp/../etc/x` is merely a longer spelling of it. These tests record
  that, rather than implying a confinement the architecture does not have;
* the check is component-based, so `foo..bar.png` is not a false positive;
* nothing is written when the guard fires.
"""
import os

import pytest
from conftest import BASE, new_sprite, ok, run

from aseprite_mcp.core.commands import reject_traversal
from aseprite_mcp.tools import analysis, canvas, export, scene

TRAVERSAL = "Invalid filename: parent directory traversal not allowed"


@pytest.fixture(scope="module")
def source():
    return new_sprite("paths", 8, 8)


@pytest.fixture(scope="module")
def outdir():
    path = f"{BASE}/paths-out"
    os.makedirs(path, exist_ok=True)
    return path


# ── the guard itself ──────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "../escape.png",
    "a/../../escape.png",
    "./../escape.png",
    "..",
    "../",
    "..\\windows.png",
    "dir\\..\\..\\escape.png",
    "a/b/../../../escape.png",
])
def test_traversal_is_rejected(path):
    assert reject_traversal(path) == TRAVERSAL


@pytest.mark.parametrize("path", [
    "plain.png",
    "dir/plain.png",
    "/tmp/abs.png",
    "foo..bar.png",
    "..hidden.png",
    "trailing..",
    "a/b/c.png",
    "./same.png",
    "",
    "a/../b.png",
    "dir/..",
])
def test_ordinary_paths_are_accepted(path):
    assert reject_traversal(path) is None


@pytest.mark.parametrize("path", ["/tmp/../etc/passwd", "/etc/passwd"])
def test_absolute_paths_are_not_scoped(path):
    """Documented limitation: there is no workspace root to confine to, so an
    absolute path is a legal request and an interior `..` in one is just a
    longer spelling of the same destination."""
    assert reject_traversal(path) is None


def test_a_doubled_dot_inside_a_name_is_not_traversal():
    """The old substring check rejected these; the component check must not."""
    assert reject_traversal("sprite..v2.aseprite") is None
    assert reject_traversal("dir../file.png") is None


# ── the tools that consume it ─────────────────────────────────────────

def test_create_canvas_rejects_traversal():
    assert run(canvas.create_canvas(8, 8, "../escaped.aseprite")) == TRAVERSAL
    assert not os.path.exists(
        os.path.join(os.path.dirname(os.getcwd()), "escaped.aseprite"))


def test_export_frame_rejects_traversal(source):
    assert run(export.export_frame(source, 1, "../escaped.png")) == TRAVERSAL


def test_export_spritesheet_rejects_traversal_in_both_paths(source, outdir):
    assert run(export.export_spritesheet(source, "../sheet.png")) == TRAVERSAL
    assert run(export.export_spritesheet(
        source, f"{outdir}/ok.png", data_filename="../data.json")) == TRAVERSAL


def test_export_layers_rejects_traversal(source):
    assert run(export.export_layers(source, "../layers")) == TRAVERSAL


def test_export_tag_rejects_traversal(source):
    assert run(export.export_tag(source, "walk", "../tag.gif")) == TRAVERSAL


def test_copy_sprite_rejects_traversal(source):
    assert run(export.copy_sprite(source, "../copy.aseprite")) == TRAVERSAL


def test_onion_skin_render_rejects_traversal(source):
    assert run(analysis.render_onion_skin(source, 1, "../onion.png")) == TRAVERSAL


def test_copy_layers_rejects_traversal_in_either_sprite(source, outdir, monkeypatch):
    """Existence is checked first, so run from a subdirectory where the
    escaping spelling both exists and keeps its `..` after normalisation."""
    monkeypatch.chdir(outdir)
    escaping = f"../{os.path.basename(source)}"
    assert os.path.exists(escaping)
    assert run(scene.copy_layers_between_sprites(
        escaping, source, ["body"])) == TRAVERSAL
    assert run(scene.copy_layers_between_sprites(
        source, escaping, ["body"])) == TRAVERSAL


# ── absolute paths and symlinks: documented, not confined ─────────────

def test_absolute_paths_are_accepted_by_design(source, outdir):
    """There is no workspace root, so an absolute path is a valid request."""
    out = f"{outdir}/absolute.png"
    ok(run(export.export_frame(source, 1, out)))
    assert os.path.isabs(out) and os.path.exists(out)


def test_a_symlinked_output_directory_writes_through_the_link(source, outdir):
    """Writes follow a symlink; this is the OS behaviour, recorded here so a
    future confinement change has a test to update rather than a surprise."""
    real = f"{outdir}/real-target"
    link = f"{outdir}/linked"
    os.makedirs(real, exist_ok=True)
    if not os.path.islink(link):
        os.symlink(real, link)
    ok(run(export.export_frame(source, 1, f"{link}/through-link.png")))
    assert os.path.exists(f"{real}/through-link.png")


def test_a_dotdot_that_cancels_out_is_normalised_not_rejected(source, outdir):
    """`<dir>/linked/../x.png` resolves inside the same directory, so it is
    allowed; the guard only fires when a `..` survives normalisation."""
    link = f"{outdir}/linked"
    ok(run(export.export_frame(source, 1, f"{link}/../cancelled.png")))
    assert os.path.exists(f"{outdir}/cancelled.png")


# ── shell/Lua metacharacters in a path are inert ──────────────────────

@pytest.mark.parametrize("name", [
    "semi;colon.png",
    "pipe|char.png",
    "dollar$brace.png",
    "back`tick.png",
    "space in name.png",
    "amp&ersand.png",
    "star*.png",
])
def test_metacharacters_in_an_output_name_are_literal(source, outdir, name):
    """Arguments go to Aseprite through argv, never through a shell, and the
    name is escaped before it reaches Lua, so the file is named verbatim."""
    out = f"{outdir}/{name}"
    ok(run(export.export_frame(source, 1, out)))
    assert os.path.exists(out)


def test_a_brace_template_is_not_expanded_into_extra_files(source, outdir):
    """Aseprite understands {frame}-style templates in --save-as; export_frame
    exports a single frame, so exactly one file must appear."""
    target = f"{outdir}/braces"
    os.makedirs(target, exist_ok=True)
    ok(run(export.export_frame(source, 1, f"{target}/shot.png")))
    assert os.listdir(target) == ["shot.png"]


def test_output_paths_are_not_evaluated_as_lua(source, outdir):
    name = 'quote"in]]name.png'
    out = f"{outdir}/{name}"
    result = run(export.export_frame(source, 1, out))
    assert not result.startswith("Failed"), result
    assert os.path.exists(out)
