"""Drawing primitives (tools/drawing.py), legacy and *_at variants.

The legacy tools paint the active cel of the first layer; the *_at tools
take an explicit layer and frame. Both families are checked by reading the
painted pixels back.
"""
import pytest
from conftest import cel_bounds, new_sprite, ok, pixel, run

from aseprite_mcp.tools import animation, canvas, drawing


@pytest.fixture(scope="module")
def legacy():
    """A single-layer sprite: the legacy tools target its active cel."""
    return new_sprite("draw_legacy", layer=None)


@pytest.fixture(scope="module")
def layered():
    path = new_sprite("draw_layered")
    ok(run(animation.add_frames(path, 1)))
    return path


ACTIVE = "Layer 1"


# ── legacy (active-cel) family ────────────────────────────────────────

def test_draw_pixels_paints_each_requested_point(legacy):
    ok(run(drawing.draw_pixels(legacy, [
        {"x": 1, "y": 1, "color": "#FF0000"},
        {"x": 2, "y": 2, "color": "#00FF00"},
    ])))
    assert pixel(legacy, 1, 1, ACTIVE) == "#ff0000"
    assert pixel(legacy, 2, 2, ACTIVE) == "#00ff00"


def test_draw_pixels_defaults_to_black(legacy):
    ok(run(drawing.draw_pixels(legacy, [{"x": 3, "y": 3}])))
    assert pixel(legacy, 3, 3, ACTIVE) == "#000000"


def test_draw_pixels_accepts_an_empty_list(legacy):
    ok(run(drawing.draw_pixels(legacy, [])))


def test_draw_line_connects_both_endpoints(legacy):
    ok(run(drawing.draw_line(legacy, 0, 10, 10, 10, "#0000FF")))
    assert pixel(legacy, 0, 10, ACTIVE) == "#0000ff"
    assert pixel(legacy, 5, 10, ACTIVE) == "#0000ff"
    assert pixel(legacy, 10, 10, ACTIVE) == "#0000ff"


def test_draw_line_thickness_widens_the_stroke(legacy):
    ok(run(drawing.draw_line(legacy, 0, 20, 10, 20, "#FFFF00", thickness=3)))
    assert pixel(legacy, 5, 19, ACTIVE) == "#ffff00"
    assert pixel(legacy, 5, 21, ACTIVE) == "#ffff00"


def test_draw_line_rejects_a_bad_colour(legacy):
    assert run(drawing.draw_line(legacy, 0, 0, 1, 1, "not-a-colour")) == \
        "Invalid color value: not-a-colour"


def test_draw_rectangle_outline_is_hollow(legacy):
    ok(run(drawing.draw_rectangle(legacy, 20, 0, 8, 8, "#FF00FF")))
    assert pixel(legacy, 20, 0, ACTIVE) == "#ff00ff"
    assert pixel(legacy, 27, 7, ACTIVE) == "#ff00ff"
    assert pixel(legacy, 24, 4, ACTIVE) != "#ff00ff"


def test_draw_rectangle_filled_covers_the_interior(legacy):
    ok(run(drawing.draw_rectangle(legacy, 20, 20, 6, 6, "#00FFFF", fill=True)))
    assert pixel(legacy, 22, 22, ACTIVE) == "#00ffff"


@pytest.mark.parametrize("width,height", [(0, 4), (4, 0), (-1, 4)])
def test_draw_rectangle_rejects_a_degenerate_size(legacy, width, height):
    assert run(drawing.draw_rectangle(legacy, 0, 0, width, height)) == \
        "Width and height must be > 0"


def test_draw_rectangle_rejects_a_bad_colour(legacy):
    assert "Invalid color value" in run(
        drawing.draw_rectangle(legacy, 0, 0, 2, 2, "#12345"))


def test_draw_circle_outline_and_fill(legacy):
    path = new_sprite("draw_circle_legacy", layer=None)
    ok(run(drawing.draw_circle(path, 16, 16, 6, "#123456", fill=True)))
    assert pixel(path, 16, 16, ACTIVE) == "#123456"
    ok(run(drawing.draw_circle(path, 16, 16, 10, "#654321")))
    assert pixel(path, 6, 16, ACTIVE) == "#654321"


def test_draw_circle_rejects_a_bad_colour(legacy):
    assert "Invalid color value" in run(drawing.draw_circle(legacy, 1, 1, 2, "zzz"))


def test_fill_area_floods_a_closed_region(legacy):
    path = new_sprite("draw_fill_legacy", layer=None)
    ok(run(drawing.draw_rectangle(path, 4, 4, 12, 12, "#FF0000")))
    ok(run(drawing.fill_area(path, 10, 10, "#00FF00")))
    assert pixel(path, 10, 10, ACTIVE) == "#00ff00"
    assert pixel(path, 4, 4, ACTIVE) == "#ff0000"


def test_fill_area_rejects_a_bad_colour(legacy):
    assert "Invalid color value" in run(drawing.fill_area(legacy, 0, 0, "#XYZXYZ"))


# ── *_at family: explicit layer and frame ─────────────────────────────

def test_draw_pixels_at_targets_the_named_frame(layered):
    ok(run(drawing.draw_pixels_at(layered, "body", 2, [
        {"x": 5, "y": 5, "color": "#AA0000"},
    ])))
    assert pixel(layered, 5, 5, "body", 2) == "#aa0000"
    assert cel_bounds(layered, "body", 1) is None


def test_draw_pixels_at_can_refuse_to_create_the_cel(layered):
    path = new_sprite("draw_no_create")
    ok(run(drawing.draw_pixels_at(
        path, "body", 1, [{"x": 1, "y": 1, "color": "#FFFFFF"}],
        create_if_missing=False)))
    assert cel_bounds(path, "body", 1) is None


def test_draw_pixels_at_rejects_a_frame_past_the_end(layered):
    assert "Failed" in run(drawing.draw_pixels_at(
        layered, "body", 99, [{"x": 0, "y": 0}]))


def test_draw_pixels_at_rejects_an_unknown_layer(layered):
    assert "Layer not found" in run(drawing.draw_pixels_at(
        layered, "ghost", 1, [{"x": 0, "y": 0}]))


def test_draw_line_at_is_bresenham_exact(layered):
    path = new_sprite("draw_line_at")
    ok(run(drawing.draw_line_at(path, "body", 1, 0, 0, 6, 6, "#FF0000")))
    for step in range(7):
        assert pixel(path, step, step, "body") == "#ff0000"


def test_draw_line_at_thickness_widens_the_stroke():
    path = new_sprite("draw_line_thick")
    ok(run(drawing.draw_line_at(path, "body", 1, 2, 10, 12, 10, "#00FF00",
                                thickness=3)))
    assert pixel(path, 7, 9, "body") == "#00ff00"
    assert pixel(path, 7, 11, "body") == "#00ff00"


def test_draw_line_at_rejects_a_bad_colour(layered):
    assert "Invalid color value" in run(
        drawing.draw_line_at(layered, "body", 1, 0, 0, 1, 1, "#GGGGGG"))


def test_draw_rectangle_at_outline_and_fill():
    path = new_sprite("draw_rect_at")
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 2, 2, 10, 10, "#0000FF")))
    assert pixel(path, 2, 2, "body") == "#0000ff"
    assert pixel(path, 6, 6, "body") != "#0000ff"
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 14, 14, 8, 8, "#00FF00", True)))
    assert pixel(path, 18, 18, "body") == "#00ff00"


def test_draw_rectangle_at_rejects_a_degenerate_size(layered):
    assert run(drawing.draw_rectangle_at(layered, "body", 1, 0, 0, 0, 4)) == \
        "Width and height must be > 0"


def test_draw_circle_at_outline_and_fill():
    path = new_sprite("draw_circle_at")
    ok(run(drawing.draw_circle_at(path, "body", 1, 16, 16, 8, "#D04648")))
    assert pixel(path, 8, 16, "body") == "#d04648"
    assert pixel(path, 16, 16, "body") != "#d04648"
    ok(run(drawing.draw_circle_at(path, "body", 1, 16, 16, 5, "#306230", True)))
    assert pixel(path, 16, 16, "body") == "#306230"


def test_draw_circle_at_rejects_a_bad_colour(layered):
    assert "Invalid color value" in run(
        drawing.draw_circle_at(layered, "body", 1, 4, 4, 2, "nope"))


def test_fill_area_at_respects_a_drawn_border():
    path = new_sprite("draw_fill_at")
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 4, 4, 10, 10, "#FF0000")))
    ok(run(drawing.fill_area_at(path, "body", 1, 8, 8, "#0000FF")))
    assert pixel(path, 8, 8, "body") == "#0000ff"
    assert pixel(path, 4, 4, "body") == "#ff0000"
    assert pixel(path, 0, 0, "body") != "#0000ff"


def test_fill_area_at_rejects_a_bad_colour(layered):
    assert "Invalid color value" in run(
        drawing.fill_area_at(layered, "body", 1, 0, 0, "#1"))


def test_draw_ellipse_at_is_wider_than_it_is_tall():
    path = new_sprite("draw_ellipse")
    ok(run(drawing.draw_ellipse_at(path, "body", 1, 16, 16, 10, 4, "#FFAA00")))
    assert pixel(path, 6, 16, "body") == "#ffaa00"
    assert pixel(path, 16, 12, "body") == "#ffaa00"
    assert pixel(path, 6, 12, "body") != "#ffaa00"


def test_draw_ellipse_at_filled_covers_the_centre():
    path = new_sprite("draw_ellipse_fill")
    ok(run(drawing.draw_ellipse_at(path, "body", 1, 16, 16, 8, 5, "#00AAFF", True)))
    assert pixel(path, 16, 16, "body") == "#00aaff"
    assert pixel(path, 12, 16, "body") == "#00aaff"


@pytest.mark.parametrize("rx,ry", [(0, 4), (4, 0), (-2, 4)])
def test_draw_ellipse_at_rejects_a_degenerate_radius(layered, rx, ry):
    assert run(drawing.draw_ellipse_at(layered, "body", 1, 4, 4, rx, ry)) == \
        "radius_x and radius_y must be > 0"


def test_draw_ellipse_at_rejects_a_bad_colour(layered):
    assert "Invalid color value" in run(
        drawing.draw_ellipse_at(layered, "body", 1, 4, 4, 2, 2, "#ZZ"))


# ── polygon / path / gradient ─────────────────────────────────────────

def test_draw_polygon_closes_the_last_edge():
    path = new_sprite("draw_polygon")
    ok(run(drawing.draw_polygon(path, "body", 1, [
        {"x": 4, "y": 4}, {"x": 20, "y": 4}, {"x": 12, "y": 20},
    ], "#FF0000")))
    assert pixel(path, 12, 4, "body") == "#ff0000"
    # the closing edge from the last vertex back to the first must be drawn
    assert pixel(path, 8, 12, "body") == "#ff0000"


def test_draw_polygon_filled_covers_the_interior():
    path = new_sprite("draw_polygon_fill")
    ok(run(drawing.draw_polygon(path, "body", 1, [
        {"x": 2, "y": 2}, {"x": 28, "y": 2}, {"x": 28, "y": 28}, {"x": 2, "y": 28},
    ], "#00FF00", fill=True)))
    assert pixel(path, 15, 15, "body") == "#00ff00"


def test_draw_polygon_rejects_too_few_points(layered):
    assert run(drawing.draw_polygon(layered, "body", 1, [{"x": 0, "y": 0}])) == \
        "Polygon requires at least 3 points"


def test_draw_polygon_rejects_a_bad_colour(layered):
    points = [{"x": 0, "y": 0}, {"x": 2, "y": 0}, {"x": 1, "y": 2}]
    assert "Invalid color value" in run(
        drawing.draw_polygon(layered, "body", 1, points, "#QQ0000"))


def test_draw_path_leaves_the_polyline_open():
    path = new_sprite("draw_path")
    ok(run(drawing.draw_path(path, "body", 1, [
        {"x": 2, "y": 2}, {"x": 2, "y": 20}, {"x": 20, "y": 20},
    ], "#0000FF")))
    assert pixel(path, 2, 10, "body") == "#0000ff"
    assert pixel(path, 10, 20, "body") == "#0000ff"
    # an open path must not draw the diagonal back to the start
    assert pixel(path, 11, 11, "body") != "#0000ff"


def test_draw_path_thickness_widens_the_stroke():
    path = new_sprite("draw_path_thick")
    ok(run(drawing.draw_path(path, "body", 1, [
        {"x": 2, "y": 16}, {"x": 28, "y": 16},
    ], "#FFFFFF", thickness=3)))
    assert pixel(path, 15, 15, "body") == "#ffffff"
    assert pixel(path, 15, 17, "body") == "#ffffff"


def test_draw_path_rejects_a_single_point(layered):
    assert run(drawing.draw_path(layered, "body", 1, [{"x": 0, "y": 0}])) == \
        "Path requires at least 2 points"


def test_draw_path_rejects_a_bad_colour(layered):
    points = [{"x": 0, "y": 0}, {"x": 4, "y": 4}]
    assert "Invalid color value" in run(
        drawing.draw_path(layered, "body", 1, points, "#Q"))


def test_gradient_rect_interpolates_between_the_two_colours():
    path = new_sprite("draw_gradient")
    ok(run(drawing.apply_gradient_rect(
        path, "body", 1, 0, 0, 32, 8, "#000000", "#FFFFFF", horizontal=True)))
    assert pixel(path, 0, 4, "body") == "#000000"
    assert pixel(path, 31, 4, "body") == "#ffffff"
    middle = pixel(path, 16, 4, "body")
    assert middle not in ("#000000", "#ffffff")


def test_gradient_rect_can_run_vertically():
    path = new_sprite("draw_gradient_v")
    ok(run(drawing.apply_gradient_rect(
        path, "body", 1, 0, 0, 8, 32, "#FF0000", "#0000FF", horizontal=False)))
    assert pixel(path, 4, 0, "body") == "#ff0000"
    assert pixel(path, 4, 31, "body") == "#0000ff"


def test_gradient_rect_rejects_a_degenerate_size(layered):
    assert run(drawing.apply_gradient_rect(
        layered, "body", 1, 0, 0, 0, 4, "#000000", "#FFFFFF")) == \
        "Width and height must be > 0"


def test_gradient_rect_reports_which_colour_is_bad(layered):
    # "bad" is a valid #RGB spelling (#bbaadd), so use something that is not.
    assert "color_start" in run(drawing.apply_gradient_rect(
        layered, "body", 1, 0, 0, 4, 4, "#GG0000", "#FFFFFF"))
    assert "color_end" in run(drawing.apply_gradient_rect(
        layered, "body", 1, 0, 0, 4, 4, "#FFFFFF", "#GG0000"))


# ── alpha and clipping ────────────────────────────────────────────────

def test_rgba_colours_keep_their_alpha():
    path = new_sprite("draw_alpha")
    ok(run(drawing.draw_pixels_at(path, "body", 1, [
        {"x": 4, "y": 4, "color": "#FF000080"},
    ])))
    from conftest import alpha
    assert alpha(path, 4, 4, "body") == 0x80


def test_short_hex_spellings_are_accepted():
    path = new_sprite("draw_short_hex")
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 4, 4, "#F00", True)))
    assert pixel(path, 1, 1, "body") == "#ff0000"


def test_pixels_outside_the_canvas_are_discarded():
    path = new_sprite("draw_clip")
    ok(run(drawing.draw_line_at(path, "body", 1, -10, 16, 40, 16, "#FFFFFF")))
    assert pixel(path, 0, 16, "body") == "#ffffff"
    assert pixel(path, 31, 16, "body") == "#ffffff"
