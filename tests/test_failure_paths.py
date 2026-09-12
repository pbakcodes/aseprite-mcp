"""Failure and empty-response paths on the remaining readers and writers.

A tool that parses Aseprite's stdout has two ways to go wrong that a working
binary will not produce on demand: a non-zero exit, and an exit-0 answer with
no data line in it. Both must come back as a message rather than as a
fabricated success, so `AsepriteCommand` is mocked for exactly those two
shapes and for nothing else.
"""
import pytest
from conftest import new_sprite, ok, run

from aseprite_mcp.core.commands import AsepriteCommand
from aseprite_mcp.tools import canvas, fx, layers, palette, quality, tilemap


@pytest.fixture(scope="module")
def target():
    path = new_sprite("failpaths", 16, 16)
    ok(run(tilemap.create_tilemap_layer(path, "tiles", 8, 8)))
    return path


@pytest.fixture()
def failing(monkeypatch):
    monkeypatch.setattr(
        AsepriteCommand, "run_command",
        staticmethod(lambda args: (False, "aseprite: simulated failure")),
    )


@pytest.fixture()
def empty_output(monkeypatch):
    """Aseprite exits 0 having printed nothing useful."""
    monkeypatch.setattr(
        AsepriteCommand, "run_command", staticmethod(lambda args: (True, "")))


# ── a non-zero exit is surfaced, never swallowed ──────────────────────

@pytest.mark.parametrize("call,expected", [
    (lambda p: canvas.create_canvas(8, 8, p), "Failed to create canvas"),
    (lambda p: canvas.add_layer(p, "x"), "Failed to add layer"),
    (lambda p: canvas.add_frame(p), "Failed to add frame"),
    (lambda p: canvas.set_frame(p, 1), "Failed to set frame"),
    (lambda p: canvas.set_frame_duration(p, 1, 10), "Failed to set frame duration"),
    (lambda p: canvas.set_layer(p, "body"), "Failed to set layer"),
    (lambda p: palette.set_palette(p, ["#000000"]), "Failed to set palette"),
    (lambda p: palette.get_palette(p), "Failed to get palette"),
    (lambda p: palette.set_color_mode(p, "rgb"), "Failed to set color mode"),
    (lambda p: palette.quantize_to_palette(p), "Failed to quantize"),
    (lambda p: layers.delete_layer(p, "body"), "Failed to delete layer"),
    (lambda p: layers.flatten_sprite(p), "Failed to flatten sprite"),
    (lambda p: fx.replace_color(p, "body", 1, "#000000", "#FFFFFF"),
     "Failed to replace color"),
    (lambda p: tilemap.get_tile_at(p, "tiles", 1, 0, 0), "Failed to read tile"),
    (lambda p: tilemap.get_tilemap_info(p, "tiles"), "Failed to get tilemap info"),
    (lambda p: quality.validate_scene(p, ["body"]), "Failed to validate scene"),
    (lambda p: quality.audit_animation(p), "Failed to audit animation"),
    (lambda p: quality.animation_sanitize(p), "Failed to sanitize animation"),
    (lambda p: quality.ensure_layers_present(p, ["body"]), "Failed to ensure cels"),
])
def test_a_subprocess_failure_is_reported(target, failing, call, expected):
    result = run(call(target))
    assert result.startswith(expected), result
    assert "simulated failure" in result


# ── exit 0 with no data line ──────────────────────────────────────────

@pytest.mark.parametrize("call,expected", [
    (lambda p: tilemap.get_tile_at(p, "tiles", 1, 0, 0), "No tile data returned"),
    (lambda p: tilemap.get_tilemap_info(p, "tiles"), "No tilemap data returned"),
])
def test_a_missing_data_line_is_not_read_as_data(target, empty_output, call, expected):
    assert run(call(target)) == expected


def test_a_quantize_without_a_count_still_answers(target, empty_output):
    """The count is cosmetic, so its absence must not fail the operation."""
    assert run(palette.quantize_to_palette(target)) == \
        f"Quantized ? pixels to the palette in {target}"


def test_a_replace_without_a_count_still_answers(target, empty_output):
    assert "Replaced ? pixels" in run(
        fx.replace_color(target, "body", 1, "#000000", "#FFFFFF"))


def test_a_preset_reports_the_underlying_palette_failure(target, failing):
    """apply_palette_preset delegates to set_palette and must pass its error
    through rather than claiming the preset was applied."""
    result = run(palette.apply_palette_preset(target, "gameboy"))
    assert result.startswith("Failed to set palette")


# ── malformed list arguments on the quality tools ─────────────────────

@pytest.mark.parametrize("call", [
    lambda p, bad: quality.ensure_layers_present(p, bad),
    lambda p, bad: quality.validate_scene(p, bad),
    lambda p, bad: quality.audit_animation(p, layer_names=bad),
    lambda p, bad: quality.animation_sanitize(p, layer_names=bad),
    lambda p, bad: quality.animation_sanitize(p, layer_order=bad),
    lambda p, bad: quality.animation_sanitize(p, ensure_layers=bad),
])
@pytest.mark.parametrize("bad", [[1], [None], [{"name": "x"}], [["nested"]]])
def test_a_non_string_layer_name_is_a_controlled_error(target, call, bad):
    result = run(call(target, bad))
    assert "must be a string" in result, result


def test_the_layer_name_error_says_which_entry(target):
    result = run(quality.validate_scene(target, ["body", 7]))
    assert "layer name #2" in result
