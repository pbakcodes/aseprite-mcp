"""Failure paths on the export tools (tools/export.py).

These are the branches that fire when Aseprite exits 0 without producing a
file, when a subprocess genuinely fails, or when the produced name differs
from the one asked for. A working Aseprite will not do the first two on
demand, so `AsepriteCommand` is the mocked seam; the third is real.
"""
import glob
import os

import pytest
from conftest import BASE, new_sprite, ok, run

from aseprite_mcp.core.commands import AsepriteCommand
from aseprite_mcp.tools import animation, drawing, export


@pytest.fixture(scope="module")
def source():
    path = new_sprite("export_fail_src", 8, 8)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 8, 8, "#D04648", True)))
    ok(run(animation.set_tag(path, "loop", 1, 1)))
    return path


@pytest.fixture(scope="module")
def outdir():
    path = f"{BASE}/export-fail"
    os.makedirs(path, exist_ok=True)
    return path


@pytest.fixture()
def failing(monkeypatch):
    """Every Aseprite invocation reports a non-zero exit."""
    monkeypatch.setattr(
        AsepriteCommand, "run_command",
        staticmethod(lambda args: (False, "aseprite: simulated failure")),
    )


@pytest.fixture()
def silently_empty(monkeypatch):
    """Aseprite exits 0 but writes nothing, its worst failure mode."""
    monkeypatch.setattr(
        AsepriteCommand, "run_command", staticmethod(lambda args: (True, "")))


# ── a non-zero exit is surfaced ───────────────────────────────────────

@pytest.mark.parametrize("call,expected", [
    (lambda p, d: export.export_sprite(p, f"{d}/x.png"), "Failed to export sprite"),
    (lambda p, d: export.export_frame(p, 1, f"{d}/x.png"), "Failed to export frame"),
    (lambda p, d: export.export_spritesheet(p, f"{d}/x.png"),
     "Failed to export sprite sheet"),
    (lambda p, d: export.export_layers(p, f"{d}/layers"), "Failed to export layers"),
    (lambda p, d: export.export_tag(p, "loop", f"{d}/x.gif"), "Failed to export tag"),
])
def test_a_subprocess_failure_is_reported(source, outdir, failing, call, expected):
    result = run(call(source, outdir))
    assert result.startswith(expected)
    assert "simulated failure" in result


def test_copy_sprite_reports_a_script_failure(source, outdir, failing):
    assert run(export.copy_sprite(source, f"{outdir}/copy.aseprite")).startswith(
        "Failed to copy sprite")


def test_import_image_reports_a_script_failure(source, outdir, failing):
    image = f"{outdir}/import.png"
    from PIL import Image
    Image.new("RGBA", (2, 2), (1, 2, 3, 255)).save(image)
    assert run(export.import_image_as_layer(source, image, "x")).startswith(
        "Failed to import image")


# ── exit 0 with no output file ────────────────────────────────────────

def test_export_sprite_rejects_a_silent_no_op(source, outdir, silently_empty):
    result = run(export.export_sprite(source, f"{outdir}/silent.png"))
    assert result.startswith("Failed to export sprite")
    assert "wrote no file" in result


def test_export_frame_rejects_a_silent_no_op(source, outdir, silently_empty):
    result = run(export.export_frame(source, 1, f"{outdir}/silent_frame.png"))
    assert "was not created" in result


def test_export_spritesheet_rejects_a_silent_no_op(source, outdir, silently_empty):
    result = run(export.export_spritesheet(source, f"{outdir}/silent_sheet.png"))
    assert "wrote no sheet file" in result


def test_export_spritesheet_notices_a_missing_data_file(source, outdir, monkeypatch):
    """The sheet may appear while the JSON does not; both are required."""
    sheet = f"{outdir}/half.png"
    ok(run(export.export_spritesheet(source, sheet)))
    monkeypatch.setattr(AsepriteCommand, "run_command",
                        staticmethod(lambda args: (True, "")))
    result = run(export.export_spritesheet(source, sheet,
                                           data_filename=f"{outdir}/absent.json"))
    assert "wrote no data file" in result


def test_export_layers_rejects_an_empty_output(source, outdir, silently_empty):
    result = run(export.export_layers(source, f"{outdir}/silent_layers"))
    assert "wrote no PNG files" in result


def test_export_tag_rejects_a_silent_no_op(source, outdir, silently_empty):
    result = run(export.export_tag(source, "loop", f"{outdir}/silent_tag.gif"))
    assert result.startswith("Failed to export tag")
    assert "wrote no file" in result


def test_copy_sprite_rejects_a_silent_no_op(source, outdir, monkeypatch):
    monkeypatch.setattr(AsepriteCommand, "run_command",
                        staticmethod(lambda args: (True, "OK")))
    result = run(export.copy_sprite(source, f"{outdir}/silent_copy.aseprite"))
    assert "wrote no file" in result


def test_export_layers_rejects_an_empty_output_directory(source):
    assert run(export.export_layers(source, "")) == \
        "Output directory cannot be empty"


# ── frame-numbered siblings ───────────────────────────────────────────

def test_export_frame_renames_a_frame_numbered_sibling():
    """Aseprite appends the frame number for a multi-frame sprite; the tool
    renames the result back to the name the caller asked for."""
    path = new_sprite("export_fail_multi", 8, 8)
    ok(run(animation.add_frames(path, 2)))
    ok(run(drawing.draw_rectangle_at(path, "body", 2, 0, 0, 8, 8, "#D04648", True)))
    target = f"{BASE}/export-fail/numbered.png"
    for stale in glob.glob(f"{BASE}/export-fail/numbered*.png"):
        os.remove(stale)
    ok(run(export.export_frame(path, 2, target)))
    assert os.path.exists(target)


def test_export_sprite_accepts_frame_numbered_siblings():
    """export_sprite does not rename; it accepts the numbered siblings as
    proof the export happened."""
    path = new_sprite("export_fail_multi_sprite", 8, 8)
    ok(run(animation.add_frames(path, 2)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 8, 8, "#D04648", True)))
    base = f"{BASE}/export-fail/multi"
    for stale in glob.glob(f"{base}*.png"):
        os.remove(stale)
    ok(run(export.export_sprite(path, f"{base}.png")))
    assert glob.glob(f"{base}*.png")


# ── tag resolution ────────────────────────────────────────────────────

def test_a_spritesheet_tag_filter_reports_an_unknown_tag(source, outdir):
    result = run(export.export_spritesheet(source, f"{outdir}/notag.png",
                                           tag_name="nope"))
    assert result.startswith("Failed to resolve tag")


def test_a_spritesheet_tag_filter_reports_a_missing_range(source, outdir, monkeypatch):
    """Aseprite answering without a RANGE: line must not be read as success."""
    monkeypatch.setattr(AsepriteCommand, "run_command",
                        staticmethod(lambda args: (True, "OK")))
    assert run(export.export_spritesheet(source, f"{outdir}/norange.png",
                                         tag_name="loop")) == \
        "Failed to resolve tag: no range returned"


def test_export_tag_reports_an_unknown_tag(source, outdir):
    assert "Failed" in run(export.export_tag(source, "nope", f"{outdir}/nope.gif"))
