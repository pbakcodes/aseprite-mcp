"""Remaining tool surfaces: guide, readers, palette, filters and layer ops.

These close the error and option branches the behavioural suites do not
reach on their own, still through real Aseprite. The only mocked seam is
AsepriteCommand.run_command, used where the branch under test is a
subprocess failure that cannot be induced safely.
"""
import json

import pytest
from conftest import BASE, new_sprite, ok, pixel, run

from aseprite_mcp.core.commands import AsepriteCommand
from aseprite_mcp.tools import (
    analysis,
    animation,
    canvas,
    drawing,
    fx,
    guide,
    layers,
    native_fx,
    palette,
    pixel_read,
    scene,
    script,
    slices,
    tilemap,
)


@pytest.fixture(scope="module")
def art():
    """A 16x16 sprite with a painted block and a second layer."""
    path = new_sprite("misc_art", 16, 16)
    ok(run(canvas.add_layer(path, "fx")))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 2, 2, 8, 8, "#D04648", True)))
    ok(run(drawing.draw_rectangle_at(path, "fx", 1, 6, 6, 4, 4, "#306230", True)))
    return path


@pytest.fixture()
def failing_command(monkeypatch):
    """Force AsepriteCommand to report a subprocess failure.

    A CalledProcessError from a real Aseprite cannot be produced on demand
    without breaking the binary, so the seam is mocked; the branch it guards
    is the one that turns a non-zero exit into a readable message.
    """
    monkeypatch.setattr(
        AsepriteCommand, "run_command",
        staticmethod(lambda args: (False, "aseprite: simulated failure")),
    )


# ── guide ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("use_case", ["character", "environment", "prop"])
def test_the_guide_answers_for_every_use_case(use_case):
    out = ok(run(guide.animation_workflow_guide(use_case)))
    assert out.startswith("Animation Workflow Guide")
    assert f"Use case: {use_case}" in out
    assert out.count("\n- ") >= 6


def test_the_guide_defaults_to_the_character_workflow():
    assert run(guide.animation_workflow_guide()) == \
        run(guide.animation_workflow_guide("character"))


def test_the_guide_normalises_the_use_case():
    assert run(guide.animation_workflow_guide("  ENVIRONMENT  ")) == \
        run(guide.animation_workflow_guide("environment"))


def test_an_unknown_use_case_falls_back_to_the_generic_advice():
    generic = run(guide.animation_workflow_guide("spaceship"))
    assert "Use case: spaceship" in generic
    assert generic.split("\n")[2:] == \
        run(guide.animation_workflow_guide("anything-else")).split("\n")[2:]


def test_an_empty_use_case_is_treated_as_the_default():
    assert run(guide.animation_workflow_guide("")) == \
        run(guide.animation_workflow_guide("character"))


def test_every_guide_variant_points_at_the_audit_tools():
    for use_case in ("character", "environment", "other"):
        assert "audit_animation" in run(guide.animation_workflow_guide(use_case))


# ── pixel readers ─────────────────────────────────────────────────────

def test_reading_outside_the_canvas_returns_transparent(art):
    assert pixel(art, 99, 99, "body") == "#000000"


def test_a_rect_read_returns_one_entry_per_pixel(art):
    data = json.loads(ok(run(pixel_read.get_pixels_rect(art, 2, 2, 3, 3, "body"))))
    assert len(data) == 9
    assert all(entry["hex"] == "#d04648" for entry in data)
    assert data[0]["x"] == 2 and data[0]["y"] == 2


def test_a_rect_read_reports_the_alpha_channel(art):
    data = json.loads(ok(run(pixel_read.get_pixels_rect(art, 12, 12, 2, 2, "body"))))
    assert all(entry["a"] == 0 for entry in data)


def test_the_composite_read_sees_the_upper_layer(art):
    """get_pixel_color reads one cel; the composite flattens the stack."""
    assert pixel(art, 7, 7, "body") == "#d04648"
    composite = ok(run(pixel_read.get_composite_pixel(art, 7, 7)))
    assert "#306230" in composite


def test_the_composite_rect_read_returns_the_flattened_block(art):
    data = json.loads(ok(run(pixel_read.get_composite_rect(art, 6, 6, 2, 2))))
    assert len(data) == 4
    assert all(entry["hex"] == "#306230" for entry in data)


def test_the_composite_read_respects_layer_visibility():
    """Sprite:flatten() merges hidden layers too, so the composite used to
    report the colour of a layer nobody can see."""
    hidden = new_sprite("misc_hidden", 16, 16)
    ok(run(canvas.add_layer(hidden, "fx")))
    ok(run(drawing.draw_rectangle_at(hidden, "body", 1, 0, 0, 8, 8, "#D04648", True)))
    ok(run(drawing.draw_rectangle_at(hidden, "fx", 1, 0, 0, 8, 8, "#306230", True)))
    ok(run(animation.set_layer_visibility(hidden, "fx", False)))
    assert "#d04648" in ok(run(pixel_read.get_composite_pixel(hidden, 2, 2)))


def test_a_composite_read_rejects_a_frame_past_the_end(art):
    assert "Failed" in run(pixel_read.get_composite_pixel(art, 0, 0, 9))
    assert "Failed" in run(pixel_read.get_composite_rect(art, 0, 0, 2, 2, 9))


@pytest.mark.parametrize("call", [
    lambda p: pixel_read.get_pixel_color(p, 0, 0),
    lambda p: pixel_read.get_pixels_rect(p, 0, 0, 2, 2),
    lambda p: pixel_read.get_composite_pixel(p, 0, 0),
    lambda p: pixel_read.get_composite_rect(p, 0, 0, 2, 2),
])
def test_every_reader_reports_a_subprocess_failure(art, failing_command, call):
    result = run(call(art))
    assert result.startswith("Failed to read")
    assert "simulated failure" in result


@pytest.mark.parametrize("call,expected", [
    (lambda p: pixel_read.get_pixel_color(p, 0, 0), "No pixel data returned"),
    (lambda p: pixel_read.get_pixels_rect(p, 0, 0, 2, 2), "No pixel data returned"),
    (lambda p: pixel_read.get_composite_pixel(p, 0, 0), "No pixel data returned"),
    (lambda p: pixel_read.get_composite_rect(p, 0, 0, 2, 2), "No pixel data returned"),
])
def test_every_reader_reports_an_empty_response(art, monkeypatch, call, expected):
    """Aseprite exiting 0 with no PIXEL: line must not be read as data."""
    monkeypatch.setattr(AsepriteCommand, "run_command",
                        staticmethod(lambda args: (True, "")))
    assert run(call(art)) == expected


# ── analysis ──────────────────────────────────────────────────────────

def test_compare_frames_reports_no_change_for_identical_frames():
    path = new_sprite("misc_compare", 16, 16)
    ok(run(animation.add_frames(path, 1)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 2, 2, 4, 4, "#D04648", True)))
    ok(run(animation.copy_frame(path, 1, 2)))
    data = json.loads(ok(run(analysis.compare_frames(path, 1, 2))))
    assert data["changed_pixels"] == 0
    assert data["percent_changed"] == 0
    assert "changed_bounds" not in data


def test_compare_frames_reports_the_changed_bounds():
    path = new_sprite("misc_compare_diff", 16, 16)
    ok(run(animation.add_frames(path, 1)))
    ok(run(drawing.draw_rectangle_at(path, "body", 2, 4, 4, 3, 3, "#00FF00", True)))
    data = json.loads(ok(run(analysis.compare_frames(path, 1, 2))))
    assert data["changed_pixels"] == 9
    assert data["changed_bounds"] == {"x": 4, "y": 4, "width": 3, "height": 3}


def test_compare_frames_rejects_a_frame_past_the_end(art):
    assert "Failed" in run(analysis.compare_frames(art, 1, 9))


def test_color_stats_counts_the_painted_pixels(art):
    data = json.loads(ok(run(analysis.get_color_stats(art))))
    assert data["opaque_pixels"] > 0
    assert data["unique_colors"] >= 2
    assert {"color": "#306230", "count": 16} in data["top_colors"]


def test_color_stats_honours_the_top_limit(art):
    data = json.loads(ok(run(analysis.get_color_stats(art, top=1))))
    assert len(data["top_colors"]) == 1
    assert data["unique_colors"] == 2, "the cap trims the list, not the census"


def test_color_stats_rejects_a_zero_limit(art):
    assert run(analysis.get_color_stats(art, top=0)) == "top must be >= 1"


def test_color_stats_reports_a_subprocess_failure(art, failing_command):
    assert "Failed to get color stats" in run(analysis.get_color_stats(art))


def test_onion_skin_render_writes_a_scaled_png(art):
    out = f"{BASE}/misc_onion.png"
    ok(run(analysis.render_onion_skin(art, 1, out, before=1, after=1, scale=4)))
    from PIL import Image
    assert Image.open(out).size == (64, 64)


def test_onion_skin_render_accepts_a_zero_window(art):
    ok(run(analysis.render_onion_skin(art, 1, f"{BASE}/misc_onion0.png",
                                      before=0, after=0)))


@pytest.mark.parametrize("kwargs,expected", [
    ({"scale": 0}, "scale must be between 1 and 64"),
    ({"scale": 99}, "scale must be between 1 and 64"),
    ({"ghost_opacity": -1}, "ghost_opacity must be between 0 and 255"),
    ({"ghost_opacity": 256}, "ghost_opacity must be between 0 and 255"),
    ({"before": -1}, "before and after must be >= 0"),
    ({"after": -1}, "before and after must be >= 0"),
])
def test_onion_skin_validates_its_arguments(art, kwargs, expected):
    assert run(analysis.render_onion_skin(art, 1, f"{BASE}/x.png", **kwargs)) == expected


# ── palette ───────────────────────────────────────────────────────────

def test_a_palette_round_trips():
    path = new_sprite("misc_palette", 8, 8)
    ok(run(palette.set_palette(path, ["#000000", "#FF0000", "#00FF00"])))
    colors = json.loads(ok(run(palette.get_palette(path))))
    assert [c.lower() for c in colors[:3]] == ["#000000", "#ff0000", "#00ff00"]


def test_set_palette_rejects_an_empty_list(art):
    assert run(palette.set_palette(art, [])) == "Colors list cannot be empty"


def test_set_palette_rejects_a_bad_colour(art):
    assert run(palette.set_palette(art, ["#GGGGGG"])) == \
        "Colors must use #RRGGBB values"


def test_every_preset_is_listed_and_applicable():
    listed = json.loads(ok(run(palette.list_palette_presets())))
    assert "gameboy" in listed and "pico8" in listed
    path = new_sprite("misc_preset", 8, 8)
    for preset in listed:
        out = ok(run(palette.apply_palette_preset(path, preset)))
        assert f"preset '{preset}'" in out


def test_a_preset_name_is_case_insensitive():
    path = new_sprite("misc_preset_case", 8, 8)
    ok(run(palette.apply_palette_preset(path, "GameBoy")))


def test_an_unknown_preset_lists_the_valid_ones(art):
    out = run(palette.apply_palette_preset(art, "nintendo64"))
    assert out.startswith("Unknown preset 'nintendo64'")
    assert "gameboy" in out


def test_a_colour_ramp_spans_dark_to_light():
    ramp = json.loads(ok(run(palette.generate_color_ramp("#D04648", steps=5))))
    assert len(ramp) == 5
    brightness = [sum(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in ramp]
    assert brightness == sorted(brightness)


@pytest.mark.parametrize("kwargs,expected", [
    ({"base_color": "#GG0000"}, "Invalid color value: #GG0000"),
    ({"base_color": "#D04648", "steps": 1}, "steps must be between 2 and 16"),
    ({"base_color": "#D04648", "steps": 99}, "steps must be between 2 and 16"),
    ({"base_color": "#D04648", "lightness_range": 2},
     "lightness_range must be between 0 and 1"),
    ({"base_color": "#D04648", "lightness_range": -1},
     "lightness_range must be between 0 and 1"),
])
def test_colour_ramp_validates_its_arguments(kwargs, expected):
    assert run(palette.generate_color_ramp(**kwargs)) == expected


def test_remap_colours_rewrites_the_range():
    path = new_sprite("misc_remap", 16, 16)
    ok(run(animation.add_frames(path, 1)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 6, 6, "#D04648", True)))
    ok(run(animation.copy_cel(path, "body", 1, 2)))
    ok(run(palette.remap_colors_in_cel_range(
        path, "body", 1, 2, [{"from": "#D04648", "to": "#0000FF"}])))
    assert pixel(path, 1, 1, "body", 1) == "#0000ff"
    assert pixel(path, 1, 1, "body", 2) == "#0000ff"


def test_remap_colours_rejects_an_empty_mapping_list(art):
    assert run(palette.remap_colors_in_cel_range(art, "body", 1, 1, [])) == \
        "Mappings list cannot be empty"


def test_remap_colours_rejects_a_bad_colour(art):
    assert run(palette.remap_colors_in_cel_range(
        art, "body", 1, 1, [{"from": "#GG0000", "to": "#000000"}])) == \
        "Mappings must use #RRGGBB colors"


def test_quantize_snaps_pixels_to_the_palette():
    path = new_sprite("misc_quantize", 16, 16)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 8, 8, "#D14749", True)))
    ok(run(palette.set_palette(path, ["#000000", "#D04648"])))
    ok(run(palette.quantize_to_palette(path, "body")))
    assert pixel(path, 2, 2, "body") == "#d04648"


def test_quantize_reports_an_unknown_layer(art):
    assert "Failed" in run(palette.quantize_to_palette(art, "ghost"))


@pytest.mark.parametrize("mode", ["rgb", "grayscale", "indexed"])
def test_every_colour_mode_is_settable(mode):
    path = new_sprite(f"misc_mode_{mode}", 8, 8)
    ok(run(palette.set_color_mode(path, mode)))
    info = json.loads(ok(run(animation.get_sprite_info(path))))
    assert info["color_mode"] in (mode, "gray" if mode == "grayscale" else mode)


def test_an_unknown_colour_mode_is_rejected(art):
    assert run(palette.set_color_mode(art, "cmyk")) == \
        "mode must be 'rgb', 'grayscale', or 'indexed'"


# ── fx ────────────────────────────────────────────────────────────────

def test_outline_cel_rings_the_painted_block():
    path = new_sprite("misc_outline", 16, 16)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 4, 4, 4, 4, "#D04648", True)))
    ok(run(fx.outline_cel(path, "body", 1, "#000000")))
    assert pixel(path, 3, 5, "body") == "#000000"
    assert pixel(path, 5, 5, "body") == "#d04648"


def test_outline_cel_can_include_the_diagonals():
    path = new_sprite("misc_outline_diag", 16, 16)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 4, 4, 4, 4, "#D04648", True)))
    ok(run(fx.outline_cel(path, "body", 1, "#00FF00", include_diagonals=True)))
    assert pixel(path, 3, 3, "body") == "#00ff00"


def test_outline_cel_rejects_a_bad_colour(art):
    assert "Invalid color value" in run(fx.outline_cel(art, "body", 1, "#GG0000"))


def test_replace_colour_reports_how_many_pixels_changed():
    path = new_sprite("misc_replace", 16, 16)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 4, 4, "#D04648", True)))
    out = ok(run(fx.replace_color(path, "body", 1, "#D04648", "#0000FF")))
    assert "Replaced 16 pixels" in out
    assert pixel(path, 1, 1, "body") == "#0000ff"


def test_replace_colour_honours_the_tolerance():
    path = new_sprite("misc_tolerance", 16, 16)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 4, 4, "#D04648", True)))
    ok(run(fx.replace_color(path, "body", 1, "#D24A4C", "#00FF00", tolerance=8)))
    assert pixel(path, 1, 1, "body") == "#00ff00"


@pytest.mark.parametrize("kwargs,expected", [
    ({"from_color": "#GG0000"}, "Colors must use #RRGGBB values"),
    ({"to_color": "#GG0000"}, "Colors must use #RRGGBB values"),
    ({"tolerance": -1}, "Tolerance must be between 0 and 255"),
    ({"tolerance": 256}, "Tolerance must be between 0 and 255"),
])
def test_replace_colour_validates_its_arguments(art, kwargs, expected):
    call = {"from_color": "#D04648", "to_color": "#000000"}
    call.update(kwargs)
    assert run(fx.replace_color(art, "body", 1, **call)) == expected


def test_adjust_hsl_shifts_the_hue():
    path = new_sprite("misc_hsl", 16, 16)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 4, 4, "#FF0000", True)))
    ok(run(fx.adjust_hsl(path, "body", 1, hue_shift=120)))
    assert pixel(path, 1, 1, "body") == "#00ff00"


def test_adjust_hsl_can_darken():
    path = new_sprite("misc_hsl_dark", 16, 16)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 4, 4, "#808080", True)))
    ok(run(fx.adjust_hsl(path, "body", 1, lightness_shift=-25)))
    assert pixel(path, 1, 1, "body") < "#808080"


@pytest.mark.parametrize("kwargs,expected", [
    ({"hue_shift": 400}, "hue_shift must be between -360 and 360"),
    ({"hue_shift": -400}, "hue_shift must be between -360 and 360"),
    ({"saturation_shift": 200}, "saturation_shift must be between -100 and 100"),
    ({"lightness_shift": -200}, "lightness_shift must be between -100 and 100"),
])
def test_adjust_hsl_validates_its_arguments(art, kwargs, expected):
    assert run(fx.adjust_hsl(art, "body", 1, **kwargs)) == expected


def test_dither_gradient_mixes_both_colours():
    path = new_sprite("misc_dither", 16, 16)
    ok(run(fx.apply_dither_gradient(path, "body", 1, 0, 0, 16, 16,
                                    "#000000", "#FFFFFF")))
    seen = {pixel(path, x, y, "body") for x in range(0, 16, 4) for y in range(0, 16, 4)}
    assert {"#000000", "#ffffff"} <= seen


def test_dither_gradient_can_run_horizontally():
    path = new_sprite("misc_dither_h", 16, 16)
    ok(run(fx.apply_dither_gradient(path, "body", 1, 0, 0, 16, 16,
                                    "#000000", "#FFFFFF", horizontal=True)))
    assert pixel(path, 0, 8, "body") == "#000000"


def test_dither_gradient_rejects_a_bad_colour(art):
    assert run(fx.apply_dither_gradient(
        art, "body", 1, 0, 0, 4, 4, "#GG0000", "#FFFFFF")) == \
        "Colors must use #RRGGBB values"


@pytest.mark.parametrize("density,expected_dominant", [(0.0, "#ff0000"), (1.0, "#0000ff")])
def test_dither_pattern_density_picks_the_dominant_colour(density, expected_dominant):
    """density is the share of color_b, so 0.0 is all color_a."""
    path = new_sprite(f"misc_pattern_{density}", 16, 16)
    ok(run(fx.apply_dither_pattern(path, "body", 1, 0, 0, 16, 16,
                                   "#FF0000", "#0000FF", density=density)))
    assert pixel(path, 3, 3, "body") == expected_dominant


@pytest.mark.parametrize("kwargs,expected", [
    ({"density": -0.5}, "density must be between 0.0 and 1.0"),
    ({"density": 1.5}, "density must be between 0.0 and 1.0"),
    ({"color_a": "#GG0000"}, "Colors must use #RRGGBB values"),
])
def test_dither_pattern_validates_its_arguments(art, kwargs, expected):
    call = {"color_a": "#FF0000", "color_b": "#0000FF"}
    call.update(kwargs)
    assert run(fx.apply_dither_pattern(art, "body", 1, 0, 0, 4, 4, **call)) == expected


# ── native filters ────────────────────────────────────────────────────

def test_invert_colours_flips_every_channel():
    path = new_sprite("misc_invert", 16, 16)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 16, 16, "#FF0000", True)))
    ok(run(native_fx.invert_colors(path, "body", 1)))
    assert pixel(path, 1, 1, "body") == "#00ffff"


def test_invert_can_be_scoped_to_a_region():
    path = new_sprite("misc_invert_region", 16, 16)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 16, 16, "#FF0000", True)))
    ok(run(native_fx.invert_colors(path, "body", 1, 0, 0, 4, 4)))
    assert pixel(path, 1, 1, "body") == "#00ffff"
    assert pixel(path, 10, 10, "body") == "#ff0000"


def test_outline_native_draws_a_ring():
    path = new_sprite("misc_outline_native", 16, 16)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 4, 4, 6, 6, "#D04648", True)))
    ok(run(native_fx.outline_native(path, "body", 1, "#0000FF")))
    assert pixel(path, 3, 6, "body") == "#0000ff"


@pytest.mark.parametrize("kwargs,expected", [
    ({"color": "#GG0000"}, "Invalid color (expected #RRGGBB)"),
    ({"place": "around"}, "place must be 'outside' or 'inside'"),
    ({"matrix": "hex"}, "matrix must be 'circle' or 'square'"),
])
def test_outline_native_validates_its_arguments(art, kwargs, expected):
    assert run(native_fx.outline_native(art, "body", 1, **kwargs)) == expected


def test_native_hsl_shifts_the_hue():
    path = new_sprite("misc_native_hsl", 16, 16)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 16, 16, "#FF0000", True)))
    ok(run(native_fx.adjust_hsl_native(path, "body", 1, hue=120)))
    assert pixel(path, 1, 1, "body") != "#ff0000"


@pytest.mark.parametrize("kwargs,expected", [
    ({"hue": 200}, "hue must be -180..180"),
    ({"saturation": 200}, "saturation and lightness must be -100..100"),
    ({"lightness": -200}, "saturation and lightness must be -100..100"),
])
def test_native_hsl_validates_its_arguments(art, kwargs, expected):
    assert run(native_fx.adjust_hsl_native(art, "body", 1, **kwargs)) == expected


def test_brightness_contrast_changes_the_pixels():
    path = new_sprite("misc_brightness", 16, 16)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 16, 16, "#808080", True)))
    ok(run(native_fx.adjust_brightness_contrast(path, "body", 1, brightness=50)))
    assert pixel(path, 1, 1, "body") != "#808080"


@pytest.mark.parametrize("kwargs", [{"brightness": 200}, {"contrast": -200}])
def test_brightness_contrast_validates_its_arguments(art, kwargs):
    assert run(native_fx.adjust_brightness_contrast(art, "body", 1, **kwargs)) == \
        "brightness and contrast must be -100..100"


def test_every_convolution_matrix_is_listed_and_applicable():
    listed = json.loads(ok(run(native_fx.list_convolution_matrices())))
    assert listed
    path = new_sprite("misc_convolve", 16, 16)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 2, 2, 8, 8, "#D04648", True)))
    for matrix in listed:
        ok(run(native_fx.apply_convolution(path, matrix, "body", 1)))


def test_an_unknown_convolution_matrix_is_reported(art):
    out = run(native_fx.apply_convolution(art, "quantum"))
    assert out.startswith("Unknown matrix 'quantum'")
    assert "list_convolution_matrices" in out


def test_extract_palette_returns_the_used_colours(art):
    data = json.loads(ok(run(native_fx.extract_palette(art, max_colors=8))))
    assert 0 < data["count"] <= 8
    assert data["count"] == len(data["colors"])
    assert all(len(c) == 7 and c.startswith("#") for c in data["colors"])
    assert "#D04648" in data["colors"]


def test_extract_palette_honours_the_colour_cap():
    path = new_sprite("misc_extract_cap", 16, 16)
    for index, color in enumerate(("#FF0000", "#00FF00", "#0000FF", "#FFFF00")):
        ok(run(drawing.draw_rectangle_at(path, "body", 1, index * 4, 0, 4, 16,
                                        color, True)))
    capped = json.loads(ok(run(native_fx.extract_palette(path, max_colors=2))))
    assert capped["count"] <= 2


def test_extract_palette_can_quantize_with_alpha(art):
    """with_alpha changes how the quantizer treats transparency; the report
    shape stays a list of #RRGGBB entries."""
    data = json.loads(ok(run(native_fx.extract_palette(art, 8, with_alpha=True))))
    assert data["count"] >= 1
    assert all(len(c) == 7 for c in data["colors"])


@pytest.mark.parametrize("value", [0, 257])
def test_extract_palette_bounds_the_colour_count(art, value):
    assert run(native_fx.extract_palette(art, value)) == "max_colors must be 1..256"


def test_extract_palette_reports_a_subprocess_failure(art, failing_command):
    assert "Failed to extract palette" in run(native_fx.extract_palette(art))


# ── layer stack ───────────────────────────────────────────────────────

def test_layers_can_be_renamed_duplicated_and_deleted():
    path = new_sprite("misc_layers", 8, 8)
    ok(run(layers.rename_layer(path, "body", "torso")))
    ok(run(layers.duplicate_layer(path, "torso", "torso copy")))
    names = [l["name"] for l in
             json.loads(ok(run(animation.get_sprite_info(path))))["layers"]]
    assert "torso" in names and "torso copy" in names
    ok(run(layers.delete_layer(path, "torso copy")))
    names = [l["name"] for l in
             json.loads(ok(run(animation.get_sprite_info(path))))["layers"]]
    assert "torso copy" not in names


def test_rename_rejects_an_empty_name(art):
    assert run(layers.rename_layer(art, "body", "")) == "New name cannot be empty"


def test_duplicate_can_place_the_copy_in_a_group():
    path = new_sprite("misc_dup_group", 8, 8)
    ok(run(canvas.add_group(path, "grp")))
    ok(run(layers.duplicate_layer(path, "body", "body copy", group="grp")))
    entry = [l for l in json.loads(ok(run(animation.get_sprite_info(path))))["layers"]
             if l["name"] == "body copy"][0]
    assert entry["parent"] == "grp"


def test_reorder_moves_a_layer_in_the_stack():
    path = new_sprite("misc_reorder", 8, 8)
    ok(run(canvas.add_layer(path, "fx")))
    ok(run(layers.reorder_layer(path, "fx", 1)))
    names = [l["name"] for l in
             json.loads(ok(run(animation.get_sprite_info(path))))["layers"]]
    assert names[0] == "fx"


def test_reorder_rejects_a_position_below_one(art):
    assert run(layers.reorder_layer(art, "body", 0)) == "Position must be >= 1"


@pytest.mark.parametrize("mode", ["multiply", "screen", "overlay", "addition"])
def test_common_blend_modes_are_accepted(mode):
    path = new_sprite("misc_blend", 8, 8)
    ok(run(layers.set_layer_blend_mode(path, "body", mode)))


def test_an_unknown_blend_mode_lists_the_valid_ones(art):
    out = run(layers.set_layer_blend_mode(art, "body", "quantum"))
    assert out.startswith("Unknown blend mode 'quantum'")
    assert "multiply" in out


def test_merge_down_combines_two_layers():
    path = new_sprite("misc_merge", 16, 16)
    ok(run(canvas.add_layer(path, "fx")))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 4, 4, "#D04648", True)))
    ok(run(drawing.draw_rectangle_at(path, "fx", 1, 8, 8, 4, 4, "#306230", True)))
    ok(run(layers.merge_layer_down(path, "fx")))
    names = [l["name"] for l in
             json.loads(ok(run(animation.get_sprite_info(path))))["layers"]]
    assert "fx" not in names


def test_flatten_leaves_a_single_layer():
    path = new_sprite("misc_flatten", 16, 16)
    ok(run(canvas.add_layer(path, "fx")))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 4, 4, "#D04648", True)))
    ok(run(layers.flatten_sprite(path)))
    layer_list = json.loads(ok(run(animation.get_sprite_info(path))))["layers"]
    assert len(layer_list) == 1


# ── slices ────────────────────────────────────────────────────────────

def test_slices_round_trip_through_the_listing():
    path = new_sprite("misc_slices", 32, 32)
    ok(run(slices.create_slice(path, "head", 2, 2, 8, 8)))
    ok(run(slices.set_slice_center(path, "head", 1, 1, 4, 4)))
    ok(run(slices.set_slice_pivot(path, "head", 4, 4)))
    listed = json.loads(ok(run(slices.list_slices(path))))
    entry = [s for s in listed if s["name"] == "head"][0]
    assert (entry["x"], entry["y"], entry["width"], entry["height"]) == (2, 2, 8, 8)
    assert entry["center"] == {"x": 1, "y": 1, "width": 4, "height": 4}
    assert entry["pivot"] == {"x": 4, "y": 4}
    ok(run(slices.delete_slice(path, "head")))
    assert json.loads(ok(run(slices.list_slices(path)))) == []


def test_create_slice_rejects_an_empty_name(art):
    assert run(slices.create_slice(art, "", 0, 0, 4, 4)) == \
        "Slice name cannot be empty"


def test_slice_operations_report_an_unknown_slice(art):
    assert "Failed" in run(slices.set_slice_center(art, "ghost", 0, 0, 2, 2))
    assert "Failed" in run(slices.set_slice_pivot(art, "ghost", 1, 1))
    assert "Failed" in run(slices.delete_slice(art, "ghost"))


# ── tilemap ───────────────────────────────────────────────────────────

@pytest.fixture()
def tiles():
    path = new_sprite("misc_tiles", 32, 32)
    ok(run(tilemap.create_tilemap_layer(path, "tiles", 8, 8)))
    return path


def test_a_tilemap_layer_reports_its_geometry(tiles):
    info = json.loads(ok(run(tilemap.get_tilemap_info(tiles, "tiles"))))
    assert info["tile_width"] == 8 and info["tile_height"] == 8


def test_tile_dimensions_must_be_positive(art):
    assert run(tilemap.create_tilemap_layer(art, "t", 0, 8)) == \
        "Tile dimensions must be > 0"


def test_drawing_on_a_tile_then_placing_it_paints_the_grid(tiles):
    ok(run(tilemap.draw_on_tile(tiles, "tiles", 1, [
        {"x": x, "y": y, "color": "#FF0000"} for x in range(8) for y in range(8)
    ])))
    ok(run(tilemap.set_tiles(tiles, "tiles", 1, [{"col": 1, "row": 1, "tile_index": 1}])))
    placed = json.loads(ok(run(tilemap.get_tile_at(tiles, "tiles", 1, 1, 1))))
    assert placed["tile_index"] == 1
    assert json.loads(ok(run(tilemap.get_tilemap_info(tiles, "tiles"))))["tile_count"] == 1
    # a tilemap cel stores tile indices, so the colour is only visible once
    # the frame is composited.
    assert "#ff0000" in ok(run(pixel_read.get_composite_pixel(tiles, 8, 8))).lower()
    assert "#000000" in ok(run(pixel_read.get_composite_pixel(tiles, 0, 0))).lower()


def test_tilemap_accepts_the_same_hex_spellings_as_the_core_parser(tiles):
    """tilemap used to carry its own #RRGGBB-only parser."""
    ok(run(tilemap.draw_on_tile(tiles, "tiles", 1, [{"x": 0, "y": 0, "color": "#0F0"}])))
    ok(run(tilemap.draw_on_tile(tiles, "tiles", 1,
                                [{"x": 1, "y": 0, "color": "#00FF00FF"}])))
    ok(run(tilemap.draw_on_tile(tiles, "tiles", 1, [{"x": 2, "y": 0, "color": "00FF00"}])))


def test_an_unparseable_tile_colour_is_reported(tiles):
    assert run(tilemap.draw_on_tile(tiles, "tiles", 1,
                                    [{"x": 0, "y": 0, "color": "#GG0000"}])) == \
        "Invalid color value: #GG0000"


def test_tile_index_zero_is_reserved(tiles):
    assert run(tilemap.draw_on_tile(tiles, "tiles", 0, [{"x": 0, "y": 0}])) == \
        "tile_index must be >= 1 (tile 0 is the reserved empty tile)"


def test_an_empty_tile_or_pixel_list_is_rejected(tiles):
    assert run(tilemap.draw_on_tile(tiles, "tiles", 1, [])) == \
        "Pixels list cannot be empty"
    assert run(tilemap.set_tiles(tiles, "tiles", 1, [])) == \
        "Tiles list cannot be empty"


def test_a_tile_index_past_the_end_is_reported(tiles):
    assert "out of range" in run(tilemap.draw_on_tile(
        tiles, "tiles", 99, [{"x": 0, "y": 0, "color": "#FFFFFF"}]))


def test_tilemap_tools_reject_a_plain_layer(art):
    assert "not a tilemap" in run(tilemap.get_tilemap_info(art, "body"))
    assert "not a tilemap" in run(tilemap.draw_on_tile(
        art, "body", 1, [{"x": 0, "y": 0, "color": "#FFFFFF"}]))


# ── scene and script ──────────────────────────────────────────────────

def test_layers_can_be_copied_between_sprites():
    source = new_sprite("misc_scene_src", 16, 16)
    target = new_sprite("misc_scene_dst", 16, 16, layer=None)
    ok(run(drawing.draw_rectangle_at(source, "body", 1, 2, 2, 4, 4, "#D04648", True)))
    ok(run(scene.copy_layers_between_sprites(source, target, ["body"])))
    assert pixel(target, 3, 3, "body") == "#d04648"


def test_copying_can_create_the_missing_frames():
    source = new_sprite("misc_scene_frames_src", 16, 16)
    target = new_sprite("misc_scene_frames_dst", 16, 16, layer=None)
    ok(run(animation.add_frames(source, 2)))
    ok(run(drawing.draw_rectangle_at(source, "body", 3, 0, 0, 4, 4, "#D04648", True)))
    ok(run(scene.copy_layers_between_sprites(source, target, ["body"],
                                             create_missing_frames=True)))
    info = json.loads(ok(run(animation.get_sprite_info(target))))
    assert info["frames"] == 3


def test_copy_layers_rejects_an_empty_layer_list(art):
    assert run(scene.copy_layers_between_sprites(art, art, [])) == \
        "Layer names list cannot be empty"


def test_copy_layers_reports_a_missing_target(art):
    missing = f"{BASE}/misc-no-target.aseprite"
    assert run(scene.copy_layers_between_sprites(art, missing, ["body"])) == \
        f"File {missing} not found"


def test_a_lua_script_can_read_the_sprite(art):
    out = ok(run(script.run_lua_script('print("W:" .. app.activeSprite.width)', art)))
    assert "W:16" in out


def test_a_lua_script_runs_without_a_sprite():
    ok(run(script.run_lua_script('print("standalone")')))


def test_an_empty_lua_script_is_rejected():
    assert run(script.run_lua_script("   ")) == "Script cannot be empty"


def test_a_lua_script_reports_a_missing_file():
    missing = f"{BASE}/misc-no-script-target.aseprite"
    assert run(script.run_lua_script("print(1)", missing)) == \
        f"File {missing} not found"


def test_a_failing_lua_script_is_surfaced(art):
    assert run(script.run_lua_script("error('boom')", art)).startswith(
        ("Failed", "Script failed"))
