"""Regression tests for Lua injection through tool arguments.

Every tool builds a Lua script by string interpolation, so any caller-
controlled value that reaches the script must be escaped (strings) or
forced through int() (numbers). These tests feed payloads that would
break out of the generated literal and assert three things:

* the payload never executes — the canary file it would create stays absent;
* the script structure is unchanged, i.e. the tool either works normally
  with the payload treated as data, or reports a controlled error;
* nothing raises out of the tool.
"""
import os

import pytest
from conftest import BASE, new_sprite, ok, pixel, run

from aseprite_mcp.core.commands import lua_escape
from aseprite_mcp.tools import (
    animation,
    canvas,
    drawing,
    layers,
    palette,
    quality,
    script,
    tilemap,
)

CANARY = f"{BASE}/injection-canary"

# Each payload tries to terminate the surrounding Lua literal and append a
# statement. The trailing comment swallows whatever the generator emits next.
PAYLOADS = (
    '" os.execute("touch ' + CANARY + '") --',
    "' os.execute('touch " + CANARY + "') --",
    'x"]=nil, os.execute("touch ' + CANARY + '") --',
    "back\\slash",
    "new\nline",
    'quote"inside',
    "--[[ block comment ]]",
    "\0null",
)


@pytest.fixture(autouse=True)
def no_canary():
    """Fail the test if any payload managed to run os.execute."""
    for suffix in ("", "2"):
        if os.path.exists(CANARY + suffix):
            os.remove(CANARY + suffix)
    yield
    leaked = [CANARY + suffix for suffix in ("", "2") if os.path.exists(CANARY + suffix)]
    assert not leaked, f"injected Lua executed: {leaked}"


@pytest.fixture(scope="module")
def target():
    path = new_sprite("injection")
    ok(run(animation.add_frames(path, 2)))
    return path


def controlled(result):
    """A tool answer is fine as long as it is a string, not an exception."""
    assert isinstance(result, str) and result, result
    return result


# ── the escaper itself ────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ('a"b', 'a\\"b'),
    ("a\\b", "a\\\\b"),
    ("a\nb", "a\\nb"),
    ("a\rb", "a\\rb"),
    ("a\0b", "a\\0b"),
    ("plain", "plain"),
])
def test_lua_escape_neutralises_every_terminator(raw, expected):
    assert lua_escape(raw) == expected


def test_lua_escape_is_applied_before_the_backslash_doubling():
    """Escaping " first would leave \\" -> \\\\" and re-open the literal."""
    assert lua_escape('\\"') == '\\\\\\"'


# ── quality.py helpers: the reported injection sinks ──────────────────

def eval_lua(target, body):
    """Run a Lua snippet through Aseprite and return its printed lines."""
    out = ok(run(script.run_lua_script(body, target)))
    return [line for line in out.splitlines() if line.startswith("PROBE:")]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_layer_frame_ranges_builds_exactly_one_entry(target, payload):
    """The generated table must hold one key carrying the payload verbatim.

    Running the snippet inside Aseprite is the only check that proves the
    payload stayed *data*: a successful break-out would change the key
    count, change the stored length, or fail to compile.
    """
    entry = f"{payload}:1-2"
    expected = entry.split(":", 1)[0].strip()
    lua = quality._parse_layer_frame_ranges([entry])
    probe = eval_lua(target, f"""
    local t = {lua}
    local count, key = 0, nil
    for k in pairs(t) do count = count + 1 key = k end
    print("PROBE:" .. count)
    print("PROBE:" .. #key)
    print("PROBE:" .. #t[key])
    """)
    assert probe == [f"PROBE:1", f"PROBE:{len(expected)}", "PROBE:1"]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_overlap_pairs_builds_exactly_one_pair(target, payload):
    entry = f"{payload},other"
    left, right = entry.split(",", 1)
    left, right = left.strip(), right.strip()
    lua = quality._parse_overlap_pairs([entry])
    probe = eval_lua(target, f"""
    local t = {lua}
    print("PROBE:" .. #t)
    print("PROBE:" .. #t[1])
    print("PROBE:" .. #t[1][1])
    print("PROBE:" .. #t[1][2])
    """)
    assert probe == ["PROBE:1", "PROBE:2",
                     f"PROBE:{len(left)}", f"PROBE:{len(right)}"]


def test_layer_frame_ranges_escapes_a_quote():
    assert quality._parse_layer_frame_ranges(['a"b:1-2']) == '{["a\\"b"]={{1,2}},}'


def test_overlap_pairs_escapes_both_sides():
    assert quality._parse_overlap_pairs(['a"b,c\\d']) == '{{"a\\"b","c\\\\d"}}'


@pytest.mark.parametrize("payload", PAYLOADS)
def test_audit_animation_survives_a_payload_layer_name(target, payload):
    controlled(run(quality.audit_animation(
        target,
        overlap_pairs=[f"{payload},body"],
        layer_frame_ranges=[f"{payload}:1-2"],
    )))


@pytest.mark.parametrize("payload", PAYLOADS)
def test_animation_sanitize_survives_a_payload_layer_name(target, payload):
    controlled(run(quality.animation_sanitize(
        target,
        layer_names=[payload],
        layer_order=[payload],
        ensure_layers=[payload],
        overlap_pairs=[f"{payload},body"],
        layer_frame_ranges=[f"{payload}:1-2"],
        report_only=True,
    )))


@pytest.mark.parametrize("payload", PAYLOADS)
def test_validate_scene_survives_a_payload_layer_name(target, payload):
    controlled(run(quality.validate_scene(target, [payload])))


def test_reports_stay_parseable_when_a_layer_name_carries_a_quote():
    """A quote in a layer name must not corrupt the JSON the tools emit."""
    import json

    path = new_sprite("injection_json")
    ok(run(canvas.add_layer(path, 'we"ird\\name')))
    ok(run(quality.ensure_layers_present(path, ['we"ird\\name'])))

    validated = json.loads(ok(run(quality.validate_scene(path, ['we"ird\\name']))))
    assert validated["missing_layers"] == []

    audited = json.loads(ok(run(quality.audit_animation(path, report_cels=True))))
    assert 'we"ird\\name' in {
        cel["layer"] for frame in audited["cels"] for cel in frame["cels"]
    }

    sanitized = json.loads(ok(run(quality.animation_sanitize(
        path, layer_names=['we"ird\\name'], report_only=True))))
    assert 'we"ird\\name' in sanitized["layer_stats"]


# ── layer names elsewhere ─────────────────────────────────────────────

@pytest.mark.parametrize("payload", PAYLOADS)
def test_layer_name_arguments_are_escaped_everywhere(target, payload):
    controlled(run(canvas.add_layer(target, payload)))
    controlled(run(canvas.set_layer(target, payload)))
    controlled(run(animation.set_layer_visibility(target, payload, True)))
    controlled(run(animation.create_cel(target, payload, 1)))
    controlled(run(drawing.draw_rectangle_at(target, payload, 1, 0, 0, 2, 2)))
    controlled(run(layers.rename_layer(target, payload, "renamed")))
    controlled(run(tilemap.get_tilemap_info(target, payload)))


@pytest.mark.parametrize("payload", PAYLOADS)
def test_filename_arguments_do_not_execute(payload):
    controlled(run(canvas.create_canvas(8, 8, f"{BASE}/{payload}.aseprite")))


# ── numeric fields: the second injection surface ──────────────────────

NUMERIC_PAYLOADS = (
    '0) os.execute("touch ' + CANARY + '") --',
    "1e9999",
    "0x10",
    "nan",
    None,
    [],
    {},
)


@pytest.mark.parametrize("payload", NUMERIC_PAYLOADS)
def test_draw_pixels_rejects_a_non_numeric_coordinate(target, payload):
    result = controlled(run(drawing.draw_pixels(
        target, [{"x": payload, "y": 0, "color": "#FFFFFF"}])))
    assert "must be a number" in result


@pytest.mark.parametrize("payload", NUMERIC_PAYLOADS)
def test_draw_pixels_at_rejects_a_non_numeric_coordinate(target, payload):
    result = controlled(run(drawing.draw_pixels_at(
        target, "body", 1, [{"x": 0, "y": payload, "color": "#FFFFFF"}])))
    assert "must be a number" in result


@pytest.mark.parametrize("payload", NUMERIC_PAYLOADS)
def test_polygon_points_reject_a_non_numeric_coordinate(target, payload):
    points = [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": payload, "y": 4}]
    assert "must be a number" in controlled(run(
        drawing.draw_polygon(target, "body", 1, points)))


@pytest.mark.parametrize("payload", NUMERIC_PAYLOADS)
def test_path_points_reject_a_non_numeric_coordinate(target, payload):
    points = [{"x": 0, "y": 0}, {"x": payload, "y": 4}]
    assert "must be a number" in controlled(run(
        drawing.draw_path(target, "body", 1, points)))


@pytest.mark.parametrize("payload", NUMERIC_PAYLOADS)
def test_set_tiles_rejects_a_non_numeric_field(target, payload):
    assert "must be a number" in controlled(run(tilemap.set_tiles(
        target, "tiles", 1, [{"col": payload, "row": 0, "tile_index": 1}])))


@pytest.mark.parametrize("payload", NUMERIC_PAYLOADS)
def test_draw_on_tile_rejects_a_non_numeric_coordinate(target, payload):
    assert "must be a number" in controlled(run(tilemap.draw_on_tile(
        target, "tiles", 1, [{"x": payload, "y": 0, "color": "#FFFFFF"}])))


def test_numeric_strings_are_still_accepted(target):
    """Coercion must not break a client that sends numbers as JSON strings."""
    path = new_sprite("injection_numeric")
    ok(run(drawing.draw_pixels_at(
        path, "body", 1, [{"x": "3", "y": "4", "color": "#FF0000"}])))
    assert pixel(path, 3, 4, "body") == "#ff0000"


def test_floats_are_truncated_rather_than_interpolated(target):
    path = new_sprite("injection_float")
    ok(run(drawing.draw_pixels_at(
        path, "body", 1, [{"x": 5.9, "y": 6.2, "color": "#00FF00"}])))
    assert pixel(path, 5, 6, "body") == "#00ff00"


# ── malformed structures must not raise ───────────────────────────────

MALFORMED = ("a string", 42, None, ["nested"], 3.5, True)


@pytest.mark.parametrize("entry", MALFORMED)
def test_every_structured_argument_rejects_a_non_object_entry(target, entry):
    assert "must be an object" in controlled(run(
        drawing.draw_pixels(target, [entry])))
    assert "must be an object" in controlled(run(
        drawing.draw_pixels_at(target, "body", 1, [entry])))
    assert "must be an object" in controlled(run(
        drawing.draw_polygon(target, "body", 1, [entry, entry, entry])))
    assert "must be an object" in controlled(run(
        drawing.draw_path(target, "body", 1, [entry, entry])))
    assert "must be an object" in controlled(run(
        tilemap.set_tiles(target, "tiles", 1, [entry])))
    assert "must be an object" in controlled(run(
        tilemap.draw_on_tile(target, "tiles", 1, [entry])))
    assert "must be an object" in controlled(run(
        palette.remap_colors_in_cel_range(target, "body", 1, 1, [entry])))


@pytest.mark.parametrize("colour", [42, [], {}, ["#ff0000"]])
def test_non_string_colours_are_rejected(target, colour):
    assert "must be a string" in controlled(run(
        drawing.draw_pixels(target, [{"x": 0, "y": 0, "color": colour}])))
    assert "must be a string" in controlled(run(
        tilemap.draw_on_tile(target, "tiles", 1, [{"x": 0, "y": 0, "color": colour}])))
    assert "must be a string" in controlled(run(
        palette.remap_colors_in_cel_range(
            target, "body", 1, 1, [{"from": colour, "to": "#000000"}])))


def test_non_string_palette_entries_are_rejected(target):
    assert controlled(run(palette.set_palette(target, [123]))) == \
        "Colors must use #RRGGBB values"


# ── run_lua_script is deliberately arbitrary code ─────────────────────

def test_run_lua_script_is_the_one_intentional_escape_hatch(target):
    """It executes caller Lua by design; it must still report failures."""
    ok(run(script.run_lua_script('print("hello from lua")', target)))
    assert run(script.run_lua_script("this is not lua", target)).startswith(
        ("Failed", "Script failed"))
    assert run(script.run_lua_script("  ")) == "Script cannot be empty"
