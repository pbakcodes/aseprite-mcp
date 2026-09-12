"""Resource bounds on caller-supplied counts and extents.

Every one of these arguments used to drive an unbounded loop or allocation
inside Aseprite, so a single MCP call could wedge the editor for hours or
exhaust memory. The bounds below are the fix; these tests pin them down and
prove the legitimate range still works.
"""
import pytest
from conftest import new_sprite, ok, pixel, run

from aseprite_mcp.core.inputs import (
    MAX_BRUSH,
    MAX_CANVAS_PIXELS,
    MAX_CANVAS_SIDE,
    check_extent,
    check_thickness,
)
from aseprite_mcp.tools import (
    animation,
    canvas,
    drawing,
    fx,
    pixel_read,
    selection,
    slices,
    transform,
)

HUGE = 2 ** 31


@pytest.fixture(scope="module")
def target():
    return new_sprite("limits")


# ── the shared helpers ────────────────────────────────────────────────

@pytest.mark.parametrize("width,height", [(0, 4), (4, 0), (-1, 4), (4, -1)])
def test_check_extent_keeps_the_original_lower_bound_message(width, height):
    assert check_extent(width, height) == "Width and height must be > 0"


@pytest.mark.parametrize("width,height", [
    (MAX_CANVAS_SIDE + 1, 4),
    (4, MAX_CANVAS_SIDE + 1),
    (HUGE, HUGE),
])
def test_check_extent_rejects_an_oversized_side(width, height):
    assert check_extent(width, height) == \
        f"Width and height must be <= {MAX_CANVAS_SIDE}"


def test_check_extent_accepts_the_largest_legal_canvas():
    assert check_extent(MAX_CANVAS_SIDE, MAX_CANVAS_SIDE) is None
    assert MAX_CANVAS_SIDE * MAX_CANVAS_SIDE == MAX_CANVAS_PIXELS


@pytest.mark.parametrize("value", [1, 8, 64, MAX_BRUSH])
def test_check_thickness_accepts_the_usable_range(value):
    assert check_thickness(value) is None


@pytest.mark.parametrize("value,expected", [
    (0, "thickness must be >= 1"),
    (-3, "thickness must be >= 1"),
    (MAX_BRUSH + 1, f"thickness must be <= {MAX_BRUSH}"),
    (HUGE, f"thickness must be <= {MAX_BRUSH}"),
])
def test_check_thickness_rejects_the_rest(value, expected):
    assert check_thickness(value) == expected


# ── frame-creation loops ──────────────────────────────────────────────

def test_add_frames_refuses_an_unbounded_count(target):
    assert run(animation.add_frames(target, HUGE)) == "Count must be <= 4096"


def test_add_frames_still_accepts_an_ordinary_count():
    path = new_sprite("limits_frames")
    ok(run(animation.add_frames(path, 3)))


def test_duplicate_frame_range_refuses_an_unbounded_repeat(target):
    assert run(animation.duplicate_frame_range(target, 1, 1, HUGE)) == \
        "Times must be <= 4096"


# ── canvas allocation ─────────────────────────────────────────────────

@pytest.mark.parametrize("width,height", [(HUGE, HUGE), (MAX_CANVAS_SIDE + 1, 8)])
def test_create_canvas_refuses_an_oversized_request(width, height):
    assert run(canvas.create_canvas(width, height)) == \
        f"Width and height must be <= {MAX_CANVAS_SIDE}"


def test_resize_canvas_refuses_an_oversized_request(target):
    assert run(transform.resize_canvas(target, HUGE, HUGE)) == \
        f"Width and height must be <= {MAX_CANVAS_SIDE}"


def test_crop_canvas_refuses_an_oversized_request(target):
    assert run(transform.crop_canvas(target, 0, 0, HUGE, HUGE)) == \
        f"Width and height must be <= {MAX_CANVAS_SIDE}"


def test_resize_canvas_reports_a_size_aseprite_did_not_apply():
    """Aseprite silently ignores a resize it cannot perform and still exits 0,
    so the tool verifies the sprite really changed."""
    path = new_sprite("limits_resize")
    ok(run(transform.resize_canvas(path, 40, 24)))
    import json
    data = json.loads(ok(run(animation.get_sprite_info(path))))
    assert (data["width"], data["height"]) == (40, 24)


# ── drawn extents ─────────────────────────────────────────────────────

@pytest.mark.parametrize("call", [
    lambda p: drawing.draw_rectangle(p, 0, 0, HUGE, HUGE),
    lambda p: drawing.draw_rectangle_at(p, "body", 1, 0, 0, HUGE, HUGE),
    lambda p: drawing.apply_gradient_rect(
        p, "body", 1, 0, 0, HUGE, HUGE, "#000000", "#FFFFFF"),
    lambda p: fx.apply_dither_gradient(
        p, "body", 1, 0, 0, HUGE, HUGE, "#000000", "#FFFFFF"),
    lambda p: fx.apply_dither_pattern(
        p, "body", 1, 0, 0, HUGE, HUGE, "#000000", "#FFFFFF"),
    lambda p: selection.move_region(p, "body", 1, 0, 0, HUGE, HUGE, 1, 1),
    lambda p: selection.copy_region(p, "body", 1, 0, 0, HUGE, HUGE, 1, 1),
    lambda p: selection.erase_region(p, "body", 1, 0, 0, HUGE, HUGE),
    lambda p: pixel_read.get_pixels_rect(p, 0, 0, HUGE, HUGE),
    lambda p: pixel_read.get_composite_rect(p, 0, 0, HUGE, HUGE),
    lambda p: slices.create_slice(p, "s", 0, 0, HUGE, HUGE),
    lambda p: slices.set_slice_center(p, "s", 0, 0, HUGE, HUGE),
])
def test_every_extent_taking_tool_refuses_an_unbounded_region(target, call):
    assert run(call(target)) == f"Width and height must be <= {MAX_CANVAS_SIDE}"


def test_ellipse_radii_are_bounded(target):
    assert run(drawing.draw_ellipse_at(target, "body", 1, 0, 0, HUGE, HUGE)) == \
        f"radius_x and radius_y must be <= {MAX_CANVAS_SIDE}"


@pytest.mark.parametrize("call", [
    lambda p: drawing.draw_line(p, 0, 0, 4, 4, "#FFFFFF", HUGE),
    lambda p: drawing.draw_line_at(p, "body", 1, 0, 0, 4, 4, "#FFFFFF", HUGE),
    lambda p: drawing.draw_path(
        p, "body", 1, [{"x": 0, "y": 0}, {"x": 4, "y": 4}], "#FFFFFF", HUGE),
])
def test_every_stroke_tool_refuses_an_unbounded_thickness(target, call):
    assert run(call(target)) == f"thickness must be <= {MAX_BRUSH}"


# ── the legitimate range still works ──────────────────────────────────

def test_a_normal_rectangle_is_unaffected():
    path = new_sprite("limits_rect")
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 2, 2, 6, 6, "#D04648", True)))
    assert pixel(path, 4, 4, "body") == "#d04648"


def test_a_normal_thickness_is_unaffected():
    path = new_sprite("limits_thickness")
    ok(run(drawing.draw_line_at(path, "body", 1, 4, 16, 28, 16, "#FFFFFF", 5)))
    assert pixel(path, 16, 14, "body") == "#ffffff"
    assert pixel(path, 16, 18, "body") == "#ffffff"


def test_a_region_larger_than_the_canvas_is_still_allowed():
    """The bound is a ceiling on allocation, not a canvas-fitting rule: a
    rectangle may legitimately extend past the edges and be clipped."""
    path = new_sprite("limits_overhang")
    ok(run(drawing.draw_rectangle_at(path, "body", 1, -8, -8, 64, 64, "#00FF00", True)))
    assert pixel(path, 0, 0, "body") == "#00ff00"
    assert pixel(path, 31, 31, "body") == "#00ff00"
