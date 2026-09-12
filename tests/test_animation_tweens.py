"""Tween tools (tools/animation.py).

Tweens are only useful if the *intermediate* frames land where the maths
says, so every test reads the interpolated positions, opacities or cel
sizes back out of the file instead of accepting the success string.
"""
import json
import math

import pytest
from conftest import cel_bounds, composite_alpha, new_sprite, ok, run

from aseprite_mcp.tools import animation, drawing, quality

EASINGS = ("linear", "ease_in", "ease_out", "ease_in_out", "smoothstep")


def positions(path, layer, frames):
    """(x, y) of `layer`'s cel on each frame in `frames`."""
    return [cel_bounds(path, layer, frame)[:2] for frame in frames]


def tween_sprite(name, frames=5):
    """A sprite whose 'body' layer has a painted cel on every frame."""
    path = new_sprite(name)
    ok(run(animation.add_frames(path, frames - 1)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 6, 6, "#D04648", True)))
    ok(run(animation.propagate_frame_to_range(path, 1, 2, frames)))
    return path


# ── linear position tween ─────────────────────────────────────────────

def test_linear_tween_walks_the_cel_across_the_range():
    path = tween_sprite("tween_linear")
    ok(run(animation.tween_cel_positions(path, "body", 1, 5, 0, 0, 8, 16)))
    assert positions(path, "body", range(1, 6)) == [
        (0, 0), (2, 4), (4, 8), (6, 12), (8, 16),
    ]


def test_linear_tween_over_a_single_frame_uses_the_start_value():
    path = tween_sprite("tween_single", frames=2)
    ok(run(animation.tween_cel_positions(path, "body", 2, 2, 5, 7, 99, 99)))
    assert positions(path, "body", [2]) == [(5, 7)]


def test_linear_tween_can_create_the_missing_cels():
    path = new_sprite("tween_create")
    ok(run(animation.add_frames(path, 2)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 4, 4, "#D04648", True)))
    ok(run(animation.tween_cel_positions(
        path, "body", 1, 3, 0, 0, 4, 0,
        create_missing_cels=True, source_frame_index=1)))
    assert positions(path, "body", [1, 2, 3]) == [(0, 0), (2, 0), (4, 0)]


def test_linear_tween_without_create_leaves_empty_frames_empty():
    path = new_sprite("tween_nocreate")
    ok(run(animation.add_frames(path, 2)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 4, 4, "#D04648", True)))
    ok(run(animation.tween_cel_positions(path, "body", 1, 3, 0, 0, 4, 0)))
    assert cel_bounds(path, "body", 2) is None


def test_linear_tween_rejects_a_range_past_the_end():
    path = tween_sprite("tween_bad_range", frames=2)
    assert "Failed" in run(animation.tween_cel_positions(path, "body", 1, 9, 0, 0, 1, 1))


def test_linear_tween_rejects_an_unknown_layer():
    path = tween_sprite("tween_bad_layer", frames=2)
    assert "Layer not found" in run(
        animation.tween_cel_positions(path, "ghost", 1, 2, 0, 0, 1, 1))


# ── eased position tween ──────────────────────────────────────────────

@pytest.mark.parametrize("easing", EASINGS)
def test_eased_tween_pins_both_endpoints(easing):
    """Whatever the curve, f(0) and f(1) must still be the endpoints."""
    path = tween_sprite(f"tween_eased_{easing}")
    ok(run(animation.tween_cel_positions_eased(
        path, "body", 1, 5, 0, 0, 16, 0, easing=easing)))
    ends = positions(path, "body", [1, 5])
    assert ends == [(0, 0), (16, 0)]


def test_ease_in_starts_slower_than_linear():
    """ease_in is t*t, so the midpoint must sit behind the linear midpoint."""
    linear = tween_sprite("tween_cmp_linear")
    eased = tween_sprite("tween_cmp_ease_in")
    ok(run(animation.tween_cel_positions_eased(
        linear, "body", 1, 5, 0, 0, 16, 0, easing="linear")))
    ok(run(animation.tween_cel_positions_eased(
        eased, "body", 1, 5, 0, 0, 16, 0, easing="ease_in")))
    assert positions(linear, "body", [3])[0][0] == 8
    assert positions(eased, "body", [3])[0][0] == 4


def test_ease_out_is_the_mirror_of_ease_in():
    path = tween_sprite("tween_ease_out")
    ok(run(animation.tween_cel_positions_eased(
        path, "body", 1, 5, 0, 0, 16, 0, easing="ease_out")))
    assert positions(path, "body", [3])[0][0] == 12


def test_smoothstep_is_symmetric_around_the_midpoint():
    path = tween_sprite("tween_smoothstep")
    ok(run(animation.tween_cel_positions_eased(
        path, "body", 1, 5, 0, 0, 16, 0, easing="smoothstep")))
    xs = [x for x, _ in positions(path, "body", range(1, 6))]
    assert xs[2] == 8
    # the curve is symmetric; each end is rounded half-up independently, so
    # the pair sums to the span give or take that single rounding step.
    assert abs(xs[1] + xs[3] - 16) <= 1
    assert xs == sorted(xs)


def test_eased_tween_rejects_an_unknown_curve():
    path = tween_sprite("tween_bad_easing", frames=2)
    assert run(animation.tween_cel_positions_eased(
        path, "body", 1, 2, 0, 0, 1, 1, easing="bouncy")) == \
        "Unsupported easing (linear, ease_in, ease_out, ease_in_out, smoothstep)"


def test_eased_tween_creates_cels_on_request():
    path = new_sprite("tween_eased_create")
    ok(run(animation.add_frames(path, 2)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 4, 4, "#D04648", True)))
    ok(run(animation.tween_cel_positions_eased(
        path, "body", 1, 3, 0, 0, 8, 0, easing="linear", create_missing_cels=True)))
    assert positions(path, "body", [2]) == [(4, 0)]


# ── oscillation ───────────────────────────────────────────────────────

def test_oscillation_follows_sine_on_x_and_cosine_on_y():
    path = tween_sprite("tween_oscillate")
    ok(run(animation.set_cel_position(path, "body", 1, 10, 10)))
    for frame in range(2, 6):
        ok(run(animation.set_cel_position(path, "body", frame, 10, 10)))
    ok(run(animation.oscillate_cel_positions(
        path, "body", 1, 5, amplitude_x=4, amplitude_y=2, cycles=1.0)))

    expected = []
    for index in range(5):
        t = index / 4
        angle = 2 * math.pi * t
        expected.append((
            10 + math.floor(4 * math.sin(angle) + 0.5),
            10 + math.floor(2 * math.cos(angle) + 0.5),
        ))
    assert positions(path, "body", range(1, 6)) == expected


def test_oscillation_with_a_phase_offset_starts_off_centre():
    path = tween_sprite("tween_phase")
    for frame in range(1, 6):
        ok(run(animation.set_cel_position(path, "body", frame, 8, 8)))
    ok(run(animation.oscillate_cel_positions(
        path, "body", 1, 5, amplitude_x=4, cycles=1.0, phase_deg=90)))
    assert positions(path, "body", [1])[0][0] == 12


def test_oscillation_with_zero_amplitude_leaves_the_cel_alone():
    path = tween_sprite("tween_no_amplitude")
    for frame in range(1, 6):
        ok(run(animation.set_cel_position(path, "body", frame, 3, 4)))
    ok(run(animation.oscillate_cel_positions(path, "body", 1, 5)))
    assert set(positions(path, "body", range(1, 6))) == {(3, 4)}


def test_oscillation_rejects_a_bad_range():
    path = tween_sprite("tween_osc_bad", frames=2)
    assert "Failed" in run(animation.oscillate_cel_positions(path, "body", 3, 1))


# ── opacity tween ─────────────────────────────────────────────────────

def test_opacity_tween_ramps_through_the_range():
    path = tween_sprite("tween_opacity")
    ok(run(animation.tween_cel_opacity_eased(
        path, "body", 1, 5, 0, 255, easing="linear")))
    report = json.loads(ok(run(quality.animation_sanitize(
        path, layer_names=["body"], report_only=True, include_stats=True))))
    assert report["layer_stats"]["body"]["cel_count"] == 5
    # cel opacity only shows up once the frame is flattened
    assert composite_alpha(path, 1, 1, 1) == 0
    assert composite_alpha(path, 1, 1, 5) == 255
    assert 100 < composite_alpha(path, 1, 1, 3) < 160


@pytest.mark.parametrize("easing", EASINGS)
def test_opacity_tween_accepts_every_easing(easing):
    path = tween_sprite(f"tween_op_{easing}", frames=3)
    ok(run(animation.tween_cel_opacity_eased(
        path, "body", 1, 3, 255, 0, easing=easing)))
    assert composite_alpha(path, 1, 1, 3) == 0


@pytest.mark.parametrize("start,end", [(-1, 10), (10, 256)])
def test_opacity_tween_rejects_out_of_range_values(start, end):
    path = tween_sprite("tween_op_range", frames=2)
    assert run(animation.tween_cel_opacity_eased(
        path, "body", 1, 2, start, end)) == "Opacity must be between 0 and 255"


def test_opacity_tween_rejects_an_unknown_curve():
    path = tween_sprite("tween_op_easing", frames=2)
    assert "Unsupported easing" in run(animation.tween_cel_opacity_eased(
        path, "body", 1, 2, 0, 255, easing="elastic"))


# ── scale tween ───────────────────────────────────────────────────────

def test_scale_tween_grows_the_cel_toward_the_end_frame():
    path = tween_sprite("tween_scale")
    ok(run(animation.tween_cel_scale_eased(
        path, "body", 1, 5, 1.0, 2.0, easing="linear", anchor="topleft")))
    widths = [cel_bounds(path, "body", frame)[2] for frame in range(1, 6)]
    assert widths == sorted(widths), widths
    assert widths[0] < widths[-1]


def test_scale_tween_centre_anchor_keeps_the_middle_put():
    path = tween_sprite("tween_scale_center")
    for frame in range(1, 6):
        ok(run(animation.set_cel_position(path, "body", frame, 10, 10)))
    ok(run(animation.tween_cel_scale_eased(
        path, "body", 1, 5, 1.0, 2.0, easing="linear", anchor="center")))
    first = cel_bounds(path, "body", 1)
    last = cel_bounds(path, "body", 5)
    assert first[0] + first[2] / 2 == pytest.approx(last[0] + last[2] / 2, abs=1)


def test_scale_tween_rejects_a_non_positive_scale():
    path = tween_sprite("tween_scale_zero", frames=2)
    assert run(animation.tween_cel_scale_eased(path, "body", 1, 2, 0, 2)) == \
        "Scale must be > 0"


def test_scale_tween_rejects_an_unknown_anchor():
    path = tween_sprite("tween_scale_anchor", frames=2)
    assert run(animation.tween_cel_scale_eased(
        path, "body", 1, 2, 1, 2, anchor="corner")) == \
        "Unsupported anchor (center, topleft)"


def test_scale_tween_rejects_an_unknown_curve():
    path = tween_sprite("tween_scale_easing", frames=2)
    assert "Unsupported easing" in run(animation.tween_cel_scale_eased(
        path, "body", 1, 2, 1, 2, easing="spring"))
