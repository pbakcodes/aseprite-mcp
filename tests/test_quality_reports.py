"""Scene/animation QA reports (tools/quality.py).

Each tool here answers with JSON, so the tests parse it and assert on the
content rather than pattern-matching a sentence.
"""
import json

import pytest
from conftest import cel_bounds, new_sprite, ok, run

from aseprite_mcp.tools import animation, canvas, drawing, quality


def report(result):
    """Parse a tool's JSON answer, failing loudly on an error string."""
    return json.loads(ok(result))


@pytest.fixture(scope="module")
def scene():
    """4 frames, 'body' painted everywhere and 'fx' painted on 1-2 only."""
    path = new_sprite("quality_scene")
    ok(run(canvas.add_layer(path, "fx")))
    ok(run(animation.add_frames(path, 3)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 2, 2, 6, 6, "#D04648", True)))
    ok(run(animation.propagate_cels(path, ["body"], 1, 2, 4)))
    ok(run(drawing.draw_rectangle_at(path, "fx", 1, 4, 4, 6, 6, "#00A0FF", True)))
    ok(run(animation.copy_cel(path, "fx", 1, 2)))
    return path


# ── ensure_layers_present ─────────────────────────────────────────────

def test_ensure_layers_present_fills_the_whole_range():
    path = new_sprite("quality_ensure")
    ok(run(animation.add_frames(path, 3)))
    ok(run(quality.ensure_layers_present(path, ["body"], 1, 4)))
    for frame in range(1, 5):
        assert cel_bounds(path, "body", frame) == (0, 0, 32, 32)


def test_ensure_layers_present_defaults_to_the_end_of_the_timeline():
    path = new_sprite("quality_ensure_default")
    ok(run(animation.add_frames(path, 2)))
    out = ok(run(quality.ensure_layers_present(path, ["body"])))
    assert "1-end" in out
    assert cel_bounds(path, "body", 3) is not None


def test_ensure_layers_present_rejects_an_empty_list(scene):
    assert run(quality.ensure_layers_present(scene, [])) == \
        "Layer names list cannot be empty"


def test_ensure_layers_present_rejects_a_range_past_the_end(scene):
    assert "Failed" in run(quality.ensure_layers_present(scene, ["body"], 1, 99))


def test_ensure_layers_present_reports_unknown_layers(scene):
    assert "Failed" in run(quality.ensure_layers_present(scene, ["ghost"]))


# ── validate_scene ────────────────────────────────────────────────────

def test_validate_scene_lists_missing_layers_and_cels(scene):
    data = report(run(quality.validate_scene(scene, ["body", "fx", "ghost"])))
    assert data["frames"] == 4
    assert data["range"] == {"start": 1, "end": 4}
    assert data["missing_layers"] == ["ghost"]
    assert {entry["frame"] for entry in data["missing_cels"]} == {3, 4}
    assert {entry["layer"] for entry in data["missing_cels"]} == {"fx"}


def test_validate_scene_is_clean_when_everything_is_there(scene):
    data = report(run(quality.validate_scene(scene, ["body"], 1, 4)))
    assert data["missing_layers"] == [] and data["missing_cels"] == []


def test_validate_scene_honours_a_narrow_range(scene):
    data = report(run(quality.validate_scene(scene, ["fx"], 1, 2)))
    assert data["missing_cels"] == []
    assert data["range"] == {"start": 1, "end": 2}


def test_validate_scene_rejects_an_empty_requirement_list(scene):
    assert run(quality.validate_scene(scene, [])) == \
        "Required layers list cannot be empty"


def test_validate_scene_rejects_a_range_past_the_end(scene):
    assert "Failed" in run(quality.validate_scene(scene, ["body"], 1, 99))


# ── audit_animation ───────────────────────────────────────────────────

def test_audit_reports_the_cel_census(scene):
    data = report(run(quality.audit_animation(scene)))
    assert data["frames"] == {"start": 1, "end": 4}
    assert data["summary"]["total_cels"] == data["summary"]["total_cels"]
    assert data["summary"]["layers_checked"] >= 2
    assert data["overlaps"] == [] and data["out_of_range"] == []


def test_audit_finds_a_declared_overlap(scene):
    data = report(run(quality.audit_animation(
        scene, overlap_pairs=["body,fx"], report_bounds=True)))
    assert data["summary"]["overlaps_total"] == 2
    frames = sorted(entry["frame"] for entry in data["overlaps"])
    assert frames == [1, 2]
    assert len(data["overlaps"][0]["a_bounds"]) == 4


def test_audit_accepts_the_colon_spelling_of_a_pair(scene):
    data = report(run(quality.audit_animation(scene, overlap_pairs=["body:fx"])))
    assert data["summary"]["overlaps_total"] == 2


def test_audit_ignores_a_malformed_pair(scene):
    data = report(run(quality.audit_animation(scene, overlap_pairs=["bodyfx", ""])))
    assert data["summary"]["overlaps_total"] == 0


def test_audit_truncates_the_overlap_list(scene):
    data = report(run(quality.audit_animation(
        scene, overlap_pairs=["body,fx"], max_overlaps=1)))
    assert data["summary"]["overlaps"] == 1
    assert data["summary"]["overlaps_total"] == 2
    assert data["summary"]["overlaps_truncated"] is True


def test_audit_flags_cels_outside_their_declared_range(scene):
    data = report(run(quality.audit_animation(
        scene, layer_frame_ranges=["fx:1-1"])))
    assert data["summary"]["out_of_range"] == 1
    assert data["out_of_range"] == [{"frame": 2, "layer": "fx"}]


def test_audit_accepts_several_spans_for_one_layer(scene):
    data = report(run(quality.audit_animation(
        scene, layer_frame_ranges=["body:1-2,3-4"])))
    assert data["summary"]["out_of_range"] == 0


def test_audit_ignores_malformed_range_entries(scene):
    data = report(run(quality.audit_animation(scene, layer_frame_ranges=[
        "no-colon", ":1-2", "body:", "body:x-y", "body:4-1", "body:0-2", "",
    ])))
    assert data["summary"]["out_of_range"] == 0


def test_audit_can_cap_the_out_of_range_list(scene):
    data = report(run(quality.audit_animation(
        scene, layer_frame_ranges=["body:1-1", "fx:1-1"], max_out_of_range=1)))
    assert len(data["out_of_range"]) == 1


def test_audit_reports_cel_bounds_on_request(scene):
    data = report(run(quality.audit_animation(
        scene, report_cels=True, report_bounds=True)))
    first = [f for f in data["cels"] if f["frame"] == 1][0]
    body = [c for c in first["cels"] if c["layer"] == "body"][0]
    # draw_rectangle_at trims the cel to the painted 6x6 block at (2, 2)
    assert (body["x"], body["y"], body["w"], body["h"]) == (2, 2, 6, 6)


def test_audit_can_report_cels_without_bounds(scene):
    data = report(run(quality.audit_animation(scene, report_cels=True)))
    first = [f for f in data["cels"] if f["frame"] == 1][0]
    assert all("w" not in cel for cel in first["cels"])


def test_audit_can_restrict_itself_to_named_layers(scene):
    data = report(run(quality.audit_animation(scene, layer_names=["fx"])))
    assert data["summary"]["layers_checked"] == 1
    assert data["summary"]["total_cels"] == 2


@pytest.mark.parametrize("kwargs,expected", [
    ({"start_frame": 0}, "Start frame must be >= 1"),
    ({"start_frame": 3, "end_frame": 2}, "End frame must be >= start frame"),
    ({"max_overlaps": -1}, "Max limits must be >= 0"),
    ({"max_out_of_range": -1}, "Max limits must be >= 0"),
])
def test_audit_validates_its_arguments(scene, kwargs, expected):
    assert run(quality.audit_animation(scene, **kwargs)) == expected


def test_audit_rejects_a_range_past_the_end(scene):
    assert "Failed" in run(quality.audit_animation(scene, 1, 99))


# ── animation_sanitize ────────────────────────────────────────────────

def test_sanitize_report_only_changes_nothing():
    path = new_sprite("quality_report_only")
    ok(run(animation.add_frames(path, 2)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 1, 1, 4, 4, "#D04648", True)))
    data = report(run(quality.animation_sanitize(
        path, layer_names=["body"], ensure_layers=["body"], report_only=True)))
    assert data["ensured"] == 2
    assert cel_bounds(path, "body", 2) is None, "report_only must not write"


def test_sanitize_ensure_layers_creates_the_missing_cels():
    path = new_sprite("quality_ensure_apply")
    ok(run(animation.add_frames(path, 2)))
    data = report(run(quality.animation_sanitize(path, ensure_layers=["body"])))
    assert data["ensured"] == 3
    assert cel_bounds(path, "body", 3) is not None


def test_sanitize_sets_opacity_zero_for_out_of_range_cels():
    path = new_sprite("quality_out_of_range")
    ok(run(animation.add_frames(path, 2)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 1, 1, 4, 4, "#D04648", True)))
    ok(run(animation.propagate_cels(path, ["body"], 1, 2, 3)))
    data = report(run(quality.animation_sanitize(
        path, layer_names=["body"], layer_frame_ranges=["body:1-1"])))
    assert data["out_of_range"] == 2
    assert data["opacity_set"] == 2
    assert "cels_out_of_range" in data["alerts"]


def test_sanitize_can_delete_out_of_range_cels():
    path = new_sprite("quality_delete_cels")
    ok(run(animation.add_frames(path, 2)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 1, 1, 4, 4, "#D04648", True)))
    ok(run(animation.propagate_cels(path, ["body"], 1, 2, 3)))
    data = report(run(quality.animation_sanitize(
        path, layer_names=["body"], layer_frame_ranges=["body:1-1"],
        out_of_range_action="delete_cels")))
    assert data["deleted"] == 2
    assert cel_bounds(path, "body", 2) is None


def test_sanitize_action_none_reports_without_touching_cels():
    path = new_sprite("quality_action_none")
    ok(run(animation.add_frames(path, 1)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 1, 1, 4, 4, "#D04648", True)))
    ok(run(animation.propagate_cels(path, ["body"], 1, 2, 2)))
    data = report(run(quality.animation_sanitize(
        path, layer_names=["body"], layer_frame_ranges=["body:1-1"],
        out_of_range_action="none")))
    assert data["out_of_range"] == 1
    assert data["deleted"] == 0 and data["opacity_set"] == 0
    assert cel_bounds(path, "body", 2) is not None


def test_sanitize_honours_a_custom_out_of_range_opacity():
    path = new_sprite("quality_custom_opacity")
    ok(run(animation.add_frames(path, 1)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 1, 1, 4, 4, "#D04648", True)))
    ok(run(animation.propagate_cels(path, ["body"], 1, 2, 2)))
    data = report(run(quality.animation_sanitize(
        path, layer_names=["body"], layer_frame_ranges=["body:1-1"],
        out_of_range_opacity=40)))
    assert data["opacity_set"] == 1


def test_sanitize_reorders_a_flat_layer_stack():
    path = new_sprite("quality_reorder")
    ok(run(canvas.add_layer(path, "fx")))
    data = report(run(quality.animation_sanitize(path, layer_order=["fx", "body"])))
    assert data["reordered"] is True
    layers = json.loads(ok(run(animation.get_sprite_info(path))))["layers"]
    # spr.layers runs bottom-to-top, and layer_order is applied from the
    # bottom up, so the requested order must appear verbatim at the front.
    names = [layer["name"] for layer in layers if not layer["is_group"]]
    assert names[:2] == ["fx", "body"]


def test_sanitize_refuses_to_reorder_across_groups():
    path = new_sprite("quality_reorder_groups")
    ok(run(canvas.add_group(path, "grp")))
    ok(run(canvas.add_layer(path, "inner", group="grp")))
    data = report(run(quality.animation_sanitize(path, layer_order=["inner", "body"])))
    assert data["reordered"] is False


def test_sanitize_counts_empty_frames_and_inactive_layers():
    path = new_sprite("quality_empty_frames")
    ok(run(animation.add_frames(path, 2)))
    ok(run(canvas.add_layer(path, "unused")))
    data = report(run(quality.animation_sanitize(path, layer_names=["unused"])))
    assert data["analysis"]["empty_frames"] == 3
    assert data["analysis"]["inactive_layers"] == ["unused"]
    assert "empty_frames_detected" in data["alerts"]


def test_sanitize_reports_layer_stats_and_bounds(scene):
    data = report(run(quality.animation_sanitize(
        scene, layer_names=["fx"], report_only=True, include_stats=True)))
    stats = data["layer_stats"]["fx"]
    assert stats["cel_count"] == 2 and stats["frames_active"] == 2
    assert stats["bounds"] == [4, 4, 10, 10]


def test_sanitize_can_omit_layer_stats(scene):
    data = report(run(quality.animation_sanitize(scene, report_only=True,
                                                 include_stats=False)))
    assert "layer_stats" not in data


def test_sanitize_reports_null_bounds_for_an_idle_layer():
    path = new_sprite("quality_null_bounds")
    ok(run(canvas.add_layer(path, "idle")))
    data = report(run(quality.animation_sanitize(
        path, layer_names=["idle"], report_only=True)))
    assert data["layer_stats"]["idle"]["bounds"] is None


def test_sanitize_can_flag_full_canvas_cels():
    path = new_sprite("quality_full_canvas")
    ok(run(quality.ensure_layers_present(path, ["body"])))
    data = report(run(quality.animation_sanitize(
        path, layer_names=["body"], report_only=True)))
    assert data["layer_stats"]["body"]["full_canvas_cels"] == 1
    assert "full_canvas_cels:body" in data["alerts"]


def test_sanitize_skips_full_canvas_overlaps_by_default(scene):
    path = new_sprite("quality_ignore_full")
    ok(run(canvas.add_layer(path, "fx")))
    ok(run(quality.ensure_layers_present(path, ["body", "fx"])))
    ignored = report(run(quality.animation_sanitize(
        path, overlap_pairs=["body,fx"], report_only=True)))
    counted = report(run(quality.animation_sanitize(
        path, overlap_pairs=["body,fx"], report_only=True,
        ignore_full_canvas_overlaps=False)))
    assert ignored["analysis"]["overlaps"] == 0
    assert counted["analysis"]["overlaps"] == 1


def test_sanitize_samples_overlaps_with_bounds(scene):
    data = report(run(quality.animation_sanitize(
        scene, layer_names=["body", "fx"], overlap_pairs=["body,fx"],
        ignore_full_canvas_overlaps=False, report_bounds=True, report_only=True)))
    assert data["analysis"]["overlaps"] == 2
    sample = data["overlap_samples"][0]
    assert sample["a"] == "body" and sample["b"] == "fx"
    assert len(sample["b_bounds"]) == 4


def test_sanitize_truncates_overlap_samples(scene):
    data = report(run(quality.animation_sanitize(
        scene, layer_names=["body", "fx"], overlap_pairs=["body,fx"],
        ignore_full_canvas_overlaps=False, max_overlaps=1, report_only=True)))
    assert len(data["overlap_samples"]) == 1
    assert data["analysis"]["overlaps_truncated"] is True


@pytest.mark.parametrize("kwargs,expected", [
    ({"start_frame": 0}, "Start frame must be >= 1"),
    ({"start_frame": 4, "end_frame": 2}, "End frame must be >= start frame"),
    ({"max_overlaps": -1}, "max_overlaps must be >= 0"),
    ({"out_of_range_action": "explode"}, "Unsupported out_of_range_action"),
    ({"out_of_range_opacity": 999}, "out_of_range_opacity must be 0-255"),
    ({"out_of_range_opacity": -1}, "out_of_range_opacity must be 0-255"),
])
def test_sanitize_validates_its_arguments(scene, kwargs, expected):
    assert run(quality.animation_sanitize(scene, **kwargs)) == expected


def test_sanitize_rejects_a_range_past_the_end(scene):
    assert "Failed" in run(quality.animation_sanitize(scene, 1, 99))
