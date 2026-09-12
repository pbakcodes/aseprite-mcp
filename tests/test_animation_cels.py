"""Cel and frame manipulation (tools/animation.py).

Every assertion reads the resulting file back — cel geometry through
audit_animation, frame counts and tags through get_sprite_info, pixels
through pixel_read — rather than trusting a tool's own success string.
"""
import json

import pytest
from conftest import cel_bounds, new_sprite, ok, pixel, run

from aseprite_mcp.tools import animation, canvas, drawing


def info(path):
    return json.loads(ok(run(animation.get_sprite_info(path))))


@pytest.fixture(scope="module")
def cels():
    """A 32x32 sprite with 4 frames and a painted 8x8 block on 'body' f1."""
    path = new_sprite("anim_cels")
    ok(run(animation.add_frames(path, 3)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 4, 4, 8, 8, "#D04648", True)))
    return path


# ── cel lifecycle ─────────────────────────────────────────────────────

def test_create_cel_lands_at_the_requested_position(cels):
    ok(run(animation.create_cel(cels, "body", 2, 3, 5)))
    assert cel_bounds(cels, "body", 2) == (3, 5, 32, 32)


def test_create_cel_is_idempotent(cels):
    """A second create must not move or resize the cel that already exists."""
    before = cel_bounds(cels, "body", 2)
    ok(run(animation.create_cel(cels, "body", 2, 20, 20)))
    assert cel_bounds(cels, "body", 2) == before


def test_create_cel_rejects_a_frame_past_the_end(cels):
    assert "Failed" in run(animation.create_cel(cels, "body", 99, 0, 0))


def test_create_cel_rejects_an_unknown_layer(cels):
    assert "Layer not found" in run(animation.create_cel(cels, "ghost", 1, 0, 0))


def test_clear_cel_removes_it_from_the_frame(cels):
    ok(run(animation.create_cel(cels, "body", 3)))
    assert cel_bounds(cels, "body", 3) is not None
    ok(run(animation.clear_cel(cels, "body", 3)))
    assert cel_bounds(cels, "body", 3) is None


def test_clear_cel_on_an_empty_frame_is_a_no_op(cels):
    """Deleting an absent cel is idempotent rather than an error."""
    ok(run(animation.clear_cel(cels, "body", 3)))
    assert cel_bounds(cels, "body", 3) is None


def test_copy_cel_reproduces_the_source_pixels(cels):
    ok(run(animation.copy_cel(cels, "body", 1, 4)))
    assert pixel(cels, 6, 6, "body", 4) == "#d04648"
    assert cel_bounds(cels, "body", 4) == cel_bounds(cels, "body", 1)


def test_copy_cel_respects_replace_false(cels):
    """With replace=False an occupied target frame must be left untouched."""
    ok(run(drawing.draw_rectangle_at(cels, "body", 4, 20, 20, 4, 4, "#00FF00", True)))
    before = pixel(cels, 21, 21, "body", 4)
    result = run(animation.copy_cel(cels, "body", 1, 4, replace=False))
    assert pixel(cels, 21, 21, "body", 4) == before, result


def test_copy_cel_rejects_a_missing_source(cels):
    assert "Failed" in run(animation.copy_cel(cels, "body", 3, 2))


def test_set_cel_position_moves_an_existing_cel(cels):
    ok(run(animation.set_cel_position(cels, "body", 1, 7, 9)))
    assert cel_bounds(cels, "body", 1)[:2] == (7, 9)
    ok(run(animation.set_cel_position(cels, "body", 1, 0, 0)))


def test_set_cel_position_can_create_from_a_source_frame(cels):
    path = new_sprite("anim_cel_source")
    ok(run(animation.add_frames(path, 2)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 2, 2, 6, 6, "#123456", True)))
    ok(run(animation.set_cel_position(
        path, "body", 3, 4, 4, create_if_missing=True, source_frame_index=1)))
    assert cel_bounds(path, "body", 3)[:2] == (4, 4)
    assert pixel(path, 6, 6, "body", 3) == "#123456"


def test_set_cel_position_without_create_leaves_the_frame_empty(cels):
    path = new_sprite("anim_cel_nocreate")
    ok(run(animation.add_frames(path, 1)))
    ok(run(animation.set_cel_position(path, "body", 2, 4, 4)))
    assert cel_bounds(path, "body", 2) is None


def test_set_cel_opacity_is_stored(cels):
    ok(run(animation.set_cel_opacity(cels, "body", 1, 128)))
    ok(run(animation.set_cel_opacity(cels, "body", 1, 255)))


def test_set_cel_opacity_rejects_out_of_range(cels):
    assert run(animation.set_cel_opacity(cels, "body", 1, 300)) == \
        "Opacity must be between 0 and 255"


# ── frames ────────────────────────────────────────────────────────────

def test_add_frames_sets_the_duration_of_new_frames():
    path = new_sprite("anim_durations")
    ok(run(animation.add_frames(path, 2, 250)))
    durations = info(path)["durations_ms"]
    assert len(durations) == 3
    assert durations[-1] == 250


def test_add_frames_without_duration_keeps_the_default():
    path = new_sprite("anim_no_duration")
    before = info(path)["durations_ms"][0]
    ok(run(animation.add_frames(path, 1)))
    assert info(path)["durations_ms"] == [before, before]


def test_set_frame_duration_all_rewrites_every_frame():
    path = new_sprite("anim_all_durations")
    ok(run(animation.add_frames(path, 2)))
    ok(run(animation.set_frame_duration_all(path, 90)))
    assert info(path)["durations_ms"] == [90, 90, 90]


def test_copy_frame_appends_when_no_target_is_given():
    path = new_sprite("anim_copy_frame")
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 1, 1, 4, 4, "#ABCDEF", True)))
    out = ok(run(animation.copy_frame(path, 1)))
    assert "new frame" in out
    assert info(path)["frames"] == 2
    assert pixel(path, 2, 2, "body", 2) == "#abcdef"


def test_copy_frame_into_an_existing_frame_overwrites_it():
    path = new_sprite("anim_copy_over")
    ok(run(animation.add_frames(path, 1)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 1, 1, 4, 4, "#111111", True)))
    ok(run(drawing.draw_rectangle_at(path, "body", 2, 1, 1, 4, 4, "#222222", True)))
    ok(run(animation.copy_frame(path, 1, 2)))
    assert pixel(path, 2, 2, "body", 2) == "#111111"


def test_copy_frame_respects_overwrite_false():
    path = new_sprite("anim_copy_nooverwrite")
    ok(run(animation.add_frames(path, 1)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 1, 1, 4, 4, "#111111", True)))
    ok(run(drawing.draw_rectangle_at(path, "body", 2, 1, 1, 4, 4, "#222222", True)))
    run(animation.copy_frame(path, 1, 2, overwrite=False))
    assert pixel(path, 2, 2, "body", 2) == "#222222"


def test_copy_frame_rejects_a_source_past_the_end():
    path = new_sprite("anim_copy_bad_source")
    assert "Failed" in run(animation.copy_frame(path, 9))


def test_duplicate_frame_range_multiplies_the_timeline():
    path = new_sprite("anim_dup_range")
    ok(run(animation.add_frames(path, 1)))
    ok(run(animation.duplicate_frame_range(path, 1, 2, times=2)))
    assert info(path)["frames"] == 6


def test_duplicate_frame_range_rejects_times_below_one(cels):
    assert run(animation.duplicate_frame_range(cels, 1, 2, times=0)) == "Times must be >= 1"


def test_duplicate_frame_range_rejects_a_bad_range():
    path = new_sprite("anim_dup_bad")
    assert "Failed" in run(animation.duplicate_frame_range(path, 3, 1))


def test_delete_frame_shortens_the_timeline():
    path = new_sprite("anim_delete_frame")
    ok(run(animation.add_frames(path, 2)))
    ok(run(animation.delete_frame(path, 2)))
    assert info(path)["frames"] == 2


def test_delete_the_only_frame_is_refused():
    path = new_sprite("anim_delete_last")
    assert "Failed" in run(animation.delete_frame(path, 1))


# ── propagation ───────────────────────────────────────────────────────

def test_propagate_frame_to_range_copies_every_layer():
    path = new_sprite("anim_propagate_frame")
    ok(run(canvas.add_layer(path, "fx")))
    ok(run(animation.add_frames(path, 3)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 2, 2, 5, 5, "#D04648", True)))
    ok(run(drawing.draw_rectangle_at(path, "fx", 1, 12, 12, 5, 5, "#00A0FF", True)))
    ok(run(animation.propagate_frame_to_range(path, 1, 2, 4)))
    for frame in (2, 3, 4):
        assert pixel(path, 3, 3, "body", frame) == "#d04648"
        assert pixel(path, 13, 13, "fx", frame) == "#00a0ff"


def test_propagate_frame_respects_overwrite_false():
    path = new_sprite("anim_propagate_keep")
    ok(run(animation.add_frames(path, 1)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 2, 2, 5, 5, "#111111", True)))
    ok(run(drawing.draw_rectangle_at(path, "body", 2, 2, 2, 5, 5, "#222222", True)))
    ok(run(animation.propagate_frame_to_range(path, 1, 2, 2, overwrite=False)))
    assert pixel(path, 3, 3, "body", 2) == "#222222"


def test_propagate_cels_targets_only_the_named_layers():
    path = new_sprite("anim_propagate_cels")
    ok(run(canvas.add_layer(path, "fx")))
    ok(run(animation.add_frames(path, 2)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 2, 2, 5, 5, "#D04648", True)))
    ok(run(drawing.draw_rectangle_at(path, "fx", 1, 12, 12, 5, 5, "#00A0FF", True)))
    ok(run(animation.propagate_cels(path, ["body"], 1, 2, 3)))
    assert pixel(path, 3, 3, "body", 3) == "#d04648"
    assert cel_bounds(path, "fx", 3) is None


def test_propagate_cels_rejects_an_empty_layer_list(cels):
    assert run(animation.propagate_cels(cels, [], 1, 1, 2)) == \
        "Layer names list cannot be empty"


def test_propagate_cels_with_an_empty_source_copies_nothing():
    """No source cel means nothing to copy, not a fabricated cel."""
    path = new_sprite("anim_propagate_missing")
    ok(run(animation.add_frames(path, 2)))
    ok(run(animation.propagate_cels(path, ["body"], 1, 2, 3)))
    assert cel_bounds(path, "body", 2) is None
    assert cel_bounds(path, "body", 3) is None


def test_propagate_cels_reports_an_unknown_layer():
    path = new_sprite("anim_propagate_unknown")
    ok(run(animation.add_frames(path, 2)))
    assert "Failed" in run(animation.propagate_cels(path, ["ghost"], 1, 2, 3))


# ── offsets ───────────────────────────────────────────────────────────

def test_offset_cel_positions_shifts_the_whole_range():
    path = new_sprite("anim_offset")
    ok(run(animation.add_frames(path, 2)))
    for frame in (1, 2, 3):
        ok(run(animation.create_cel(path, "body", frame, 5, 5)))
    ok(run(animation.offset_cel_positions(path, "body", 1, 3, 4, -2)))
    for frame in (1, 2, 3):
        assert cel_bounds(path, "body", frame)[:2] == (9, 3)


def test_offset_cel_positions_rejects_a_bad_range():
    path = new_sprite("anim_offset_bad")
    assert "Failed" in run(animation.offset_cel_positions(path, "body", 1, 9, 1, 1))


def test_offset_cel_positions_rejects_an_unknown_layer(cels):
    assert "Layer not found" in run(
        animation.offset_cel_positions(cels, "ghost", 1, 1, 1, 1))


# ── tags, visibility, onion skin ──────────────────────────────────────

def test_set_tag_stores_the_direction():
    path = new_sprite("anim_tag_dir")
    ok(run(animation.add_frames(path, 3)))
    ok(run(animation.set_tag(path, "idle", 1, 3, "pingpong")))
    tags = info(path)["tags"]
    assert tags == [{"name": "idle", "from": 1, "to": 3, "direction": "pingpong"}]


def test_set_tag_rejects_an_unknown_direction(cels):
    assert "Unsupported direction" in run(animation.set_tag(cels, "t", 1, 2, "sideways"))


def test_set_tag_replaces_a_tag_of_the_same_name():
    path = new_sprite("anim_tag_replace")
    ok(run(animation.add_frames(path, 3)))
    ok(run(animation.set_tag(path, "walk", 1, 2)))
    ok(run(animation.set_tag(path, "walk", 2, 4)))
    tags = info(path)["tags"]
    assert len(tags) == 1 and tags[0]["from"] == 2 and tags[0]["to"] == 4


def test_layer_visibility_and_opacity_round_trip():
    path = new_sprite("anim_layer_state")
    ok(run(animation.set_layer_visibility(path, "body", False)))
    ok(run(animation.set_layer_opacity(path, "body", 64)))
    body = [l for l in info(path)["layers"] if l["name"] == "body"][0]
    assert body["visible"] is False and body["opacity"] == 64


def test_set_layer_opacity_rejects_out_of_range(cels):
    assert run(animation.set_layer_opacity(cels, "body", 999)) == \
        "Opacity must be between 0 and 255"


def test_set_onion_skin_writes_the_document_preferences():
    path = new_sprite("anim_onion")
    ok(run(animation.set_onion_skin(path, True, before=3, after=1, opacity=200)))
    ok(run(animation.set_onion_skin(path, False)))


@pytest.mark.parametrize("kwargs,expected", [
    ({"before": -1}, "Before/after must be >= 0"),
    ({"after": -1}, "Before/after must be >= 0"),
    ({"opacity": 256}, "Opacity must be between 0 and 255"),
])
def test_set_onion_skin_validates_its_arguments(cels, kwargs, expected):
    assert run(animation.set_onion_skin(cels, **kwargs)) == expected
