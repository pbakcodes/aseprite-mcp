"""Canvas, layer-stack and transform tools.

Covers tools/canvas.py and tools/transform.py: sprite creation, the frame
and layer cursors, and geometry changes verified by reading the resulting
size and pixels back.
"""
import json
import os

import pytest
from conftest import BASE, new_sprite, ok, pixel, run

from aseprite_mcp.tools import animation, canvas, drawing, transform


def info(path):
    return json.loads(ok(run(animation.get_sprite_info(path))))


# ── create_canvas ─────────────────────────────────────────────────────

def test_create_canvas_writes_a_file_of_the_requested_size():
    path = f"{BASE}/canvas_size.aseprite"
    ok(run(canvas.create_canvas(24, 12, path)))
    assert os.path.exists(path)
    data = info(path)
    assert (data["width"], data["height"]) == (24, 12)
    assert data["color_mode"] == "rgb"
    assert data["frames"] == 1


@pytest.mark.parametrize("width,height", [(0, 4), (4, 0), (-8, 8)])
def test_create_canvas_rejects_a_degenerate_size(width, height):
    assert run(canvas.create_canvas(width, height)) == "Width and height must be > 0"


def test_create_canvas_reports_an_unwritable_destination():
    result = run(canvas.create_canvas(8, 8, "/proc/1/no-such-dir/out.aseprite"))
    assert not os.path.exists("/proc/1/no-such-dir/out.aseprite")
    assert result.startswith(("Failed", "Invalid")), result


# ── layers and groups ─────────────────────────────────────────────────

def test_add_layer_appends_to_the_stack():
    path = new_sprite("canvas_layers")
    ok(run(canvas.add_layer(path, "fx")))
    names = [layer["name"] for layer in info(path)["layers"]]
    assert names[-1] == "fx"


def test_add_layer_allows_a_repeated_name_at_top_level():
    """Aseprite itself permits duplicate layer names; the tool does not add
    a guard, so the second layer must simply appear alongside the first."""
    path = new_sprite("canvas_dupe")
    ok(run(canvas.add_layer(path, "body")))
    names = [layer["name"] for layer in info(path)["layers"]]
    assert names.count("body") == 2


def test_add_group_and_nested_layer():
    path = new_sprite("canvas_group")
    ok(run(canvas.add_group(path, "chars")))
    ok(run(canvas.add_layer(path, "hero", group="chars")))
    layers = {layer["name"]: layer for layer in info(path)["layers"]}
    assert layers["chars"]["is_group"] is True
    assert layers["hero"]["parent"] == "chars"


def test_add_group_inside_a_group():
    path = new_sprite("canvas_nested_group")
    ok(run(canvas.add_group(path, "outer")))
    ok(run(canvas.add_group(path, "inner", parent_group="outer")))
    layers = {layer["name"]: layer for layer in info(path)["layers"]}
    assert layers["inner"]["parent"] == "outer"


def test_add_layer_into_an_unknown_group_fails():
    path = new_sprite("canvas_bad_group")
    assert "Failed" in run(canvas.add_layer(path, "x", group="nope"))


# ── frame and layer cursors ───────────────────────────────────────────

def test_add_frame_extends_the_timeline():
    path = new_sprite("canvas_add_frame")
    ok(run(canvas.add_frame(path)))
    assert info(path)["frames"] == 2


def test_set_frame_moves_the_cursor():
    path = new_sprite("canvas_set_frame")
    ok(run(canvas.add_frame(path)))
    ok(run(canvas.set_frame(path, 2)))


def test_set_frame_rejects_an_index_past_the_end():
    path = new_sprite("canvas_set_frame_bad")
    assert "Failed" in run(canvas.set_frame(path, 7))


def test_set_frame_rejects_zero():
    path = new_sprite("canvas_set_frame_zero")
    assert "Failed" in run(canvas.set_frame(path, 0))


def test_set_frame_duration_only_touches_one_frame():
    path = new_sprite("canvas_duration")
    ok(run(canvas.add_frame(path)))
    ok(run(canvas.set_frame_duration(path, 2, 400)))
    durations = info(path)["durations_ms"]
    assert durations[1] == 400 and durations[0] != 400


def test_set_frame_duration_rejects_a_non_positive_value():
    path = new_sprite("canvas_duration_bad")
    assert run(canvas.set_frame_duration(path, 1, 0)) == "Duration must be > 0"


def test_set_layer_activates_an_existing_layer():
    path = new_sprite("canvas_set_layer")
    ok(run(canvas.set_layer(path, "body")))


def test_set_layer_can_create_the_layer():
    path = new_sprite("canvas_set_layer_create")
    ok(run(canvas.set_layer(path, "brand-new", create_if_missing=True)))
    assert "brand-new" in [layer["name"] for layer in info(path)["layers"]]


def test_set_layer_without_create_leaves_the_stack_alone():
    path = new_sprite("canvas_set_layer_nocreate")
    before = [layer["name"] for layer in info(path)["layers"]]
    ok(run(canvas.set_layer(path, "absent")))
    assert [layer["name"] for layer in info(path)["layers"]] == before


# ── transforms ────────────────────────────────────────────────────────

@pytest.fixture()
def marked(request):
    """A canvas-sized cel with a red marker top-left and a blue one bottom-right.

    flip_layer and rotate_layer transform the *cel image*, so the cel has to
    span the whole canvas for canvas coordinates to mean anything.
    """
    path = new_sprite(f"transform_{request.node.name[5:][:24]}")
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 32, 32, "#101010", True)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 4, 4, "#D04648", True)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 28, 28, 4, 4, "#3060D0", True)))
    return path


def test_flip_horizontal_moves_the_marker_to_the_right_edge(marked):
    ok(run(transform.flip_layer(marked, "body", 1, "horizontal")))
    assert pixel(marked, 30, 2, "body") == "#d04648"
    assert pixel(marked, 1, 2, "body") != "#d04648"
    assert pixel(marked, 1, 30, "body") == "#3060d0"


def test_flip_vertical_moves_the_marker_to_the_bottom(marked):
    ok(run(transform.flip_layer(marked, "body", 1, "vertical")))
    assert pixel(marked, 2, 30, "body") == "#d04648"
    assert pixel(marked, 30, 1, "body") == "#3060d0"


def test_flip_rejects_an_unknown_direction(marked):
    assert run(transform.flip_layer(marked, "body", 1, "diagonal")) == \
        "direction must be 'horizontal' or 'vertical'"


def test_flip_rejects_a_frame_past_the_end(marked):
    assert "Failed" in run(transform.flip_layer(marked, "body", 9))


def test_rotate_90_sends_the_top_left_marker_to_the_top_right(marked):
    ok(run(transform.rotate_layer(marked, "body", 1, 90)))
    assert pixel(marked, 29, 2, "body") == "#d04648"


def test_rotate_180_sends_the_marker_to_the_far_corner(marked):
    ok(run(transform.rotate_layer(marked, "body", 1, 180)))
    assert pixel(marked, 29, 29, "body") == "#d04648"


def test_rotate_270_sends_the_marker_to_the_bottom_left(marked):
    ok(run(transform.rotate_layer(marked, "body", 1, 270)))
    assert pixel(marked, 2, 29, "body") == "#d04648"


def test_rotate_rejects_an_unsupported_angle(marked):
    assert run(transform.rotate_layer(marked, "body", 1, 45)) == \
        "angle must be 90, 180, or 270"


def test_rotate_rejects_an_unknown_layer(marked):
    assert "Failed" in run(transform.rotate_layer(marked, "ghost", 1, 90))


def test_resize_canvas_changes_the_reported_size():
    path = new_sprite("transform_resize")
    ok(run(transform.resize_canvas(path, 48, 20)))
    data = info(path)
    assert (data["width"], data["height"]) == (48, 20)


@pytest.mark.parametrize("width,height", [(0, 4), (4, -1)])
def test_resize_canvas_rejects_a_degenerate_size(width, height):
    path = new_sprite("transform_resize_bad")
    assert run(transform.resize_canvas(path, width, height)) == \
        "Width and height must be > 0"


def test_crop_canvas_keeps_the_selected_window():
    path = new_sprite("transform_crop")
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 8, 8, 8, 8, "#00FF00", True)))
    ok(run(transform.crop_canvas(path, 8, 8, 8, 8)))
    data = info(path)
    assert (data["width"], data["height"]) == (8, 8)
    assert pixel(path, 0, 0, "body") == "#00ff00"


def test_crop_canvas_clamps_a_partly_outside_window():
    path = new_sprite("transform_crop_clamp")
    ok(run(transform.crop_canvas(path, 24, 24, 32, 32)))
    data = info(path)
    assert data["width"] <= 32 and data["height"] <= 32


def test_crop_canvas_rejects_a_degenerate_size():
    path = new_sprite("transform_crop_bad")
    assert run(transform.crop_canvas(path, 0, 0, 0, 4)) == \
        "Width and height must be > 0"


def test_crop_canvas_rejects_a_window_fully_outside():
    path = new_sprite("transform_crop_outside")
    assert "Failed" in run(transform.crop_canvas(path, 500, 500, 4, 4))
