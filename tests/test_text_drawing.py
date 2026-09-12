"""draw_text placement, decoration and error paths (tools/text.py).

Anchors are checked through the reported blit origin, which is the value a
caller uses to lay out a HUD; decorations are checked by reading the drawn
pixels back.
"""
import json
import os
import re

import pytest
from conftest import BASE, new_sprite, ok, pixel, run
from PIL import Image

from aseprite_mcp.core import fonts as fontlib
from aseprite_mcp.tools import text

GLYPHS = {
    "A": [".##.", "#..#", "####", "#..#", "#..#", "...."],
    "B": ["###.", "#..#", "###.", "#..#", "###.", "...."],
    "O": [".##.", "#..#", "#..#", "#..#", ".##.", "...."],
}
CELL_W, CELL_H, ASCENT = 4, 6, 5


@pytest.fixture(scope="module")
def bitmap_font(tmp_path_factory):
    directory = tmp_path_factory.mktemp("text-font")
    chars = "ABO"
    sheet = Image.new("RGBA", (CELL_W * len(chars), CELL_H), (0, 0, 0, 0))
    for index, char in enumerate(chars):
        for y, row in enumerate(GLYPHS[char]):
            for x, cell in enumerate(row):
                if cell == "#":
                    sheet.putpixel((index * CELL_W + x, y), (255, 255, 255, 255))
    sheet.save(directory / "sheet.png")
    (directory / "font.json").write_text(json.dumps({
        "name": "textfixture",
        "letter_gap": 1,
        "space_width": 2,
        "sheets": [{
            "file": "sheet.png",
            "cell_w": CELL_W, "cell_h": CELL_H, "ascent": ASCENT,
            "chars": [chars],
        }],
    }))
    fontlib.clear_cache()
    return str(directory)


@pytest.fixture()
def canvas_file():
    return new_sprite("text_canvas")


def blit_origin(result):
    """The (x, y) the tool reports drawing at."""
    match = re.search(r"at \((-?\d+), (-?\d+)\)", result)
    assert match, result
    return int(match.group(1)), int(match.group(2))


def stamp_size(result):
    match = re.search(r"stamp (\d+)x(\d+)", result)
    assert match, result
    return int(match.group(1)), int(match.group(2))


# ── anchors ───────────────────────────────────────────────────────────

# 'B' is a 4x5 box whose ink starts at the pen origin, drawn at (16, 16).
ANCHOR_ORIGINS = {
    "topleft": (16, 16),
    "top": (14, 16),
    "topright": (12, 16),
    "left": (16, 14),
    "center": (14, 14),
    "right": (12, 14),
    "bottomleft": (16, 11),
    "bottom": (14, 11),
    "bottomright": (12, 11),
    "baselineleft": (16, 11),
    "baseline": (14, 11),
    "baselineright": (12, 11),
}


@pytest.mark.parametrize("anchor,expected", sorted(ANCHOR_ORIGINS.items()))
def test_every_anchor_places_the_box_where_it_says(canvas_file, bitmap_font,
                                                   anchor, expected):
    out = ok(run(text.draw_text(canvas_file, "B", 16, 16, bitmap_font, size=1,
                                color="#FFFFFF", layer_name="body",
                                anchor=anchor)))
    assert blit_origin(out) == expected


def test_the_baseline_anchors_ignore_the_ink_height(canvas_file, bitmap_font):
    """A baseline anchor is a typography reference, so descenders must not
    shift it the way a bounding box would."""
    box = ok(run(text.draw_text(canvas_file, "B", 8, 8, bitmap_font,
                                layer_name="body", anchor="bottomleft")))
    baseline = ok(run(text.draw_text(canvas_file, "B", 8, 8, bitmap_font,
                                     layer_name="body", anchor="baselineleft")))
    assert blit_origin(box)[1] == blit_origin(baseline)[1] == 3


def test_an_unknown_anchor_lists_the_valid_ones(canvas_file, bitmap_font):
    out = run(text.draw_text(canvas_file, "A", 0, 0, bitmap_font, anchor="middle"))
    assert out.startswith("Invalid anchor 'middle'")
    assert "baselineright" in out and "topleft" in out


# ── colours ───────────────────────────────────────────────────────────

def test_the_fill_colour_lands_on_the_canvas(canvas_file, bitmap_font):
    ok(run(text.draw_text(canvas_file, "O", 4, 4, bitmap_font, size=1,
                          color="#FF8800", layer_name="body")))
    assert pixel(canvas_file, 5, 4, "body") == "#ff8800"


def test_a_short_hex_fill_is_accepted(canvas_file, bitmap_font):
    ok(run(text.draw_text(canvas_file, "O", 12, 4, bitmap_font,
                          color="#0F0", layer_name="body")))
    assert pixel(canvas_file, 13, 4, "body") == "#00ff00"


@pytest.mark.parametrize("kwargs,expected", [
    ({"color": "#GG0000"}, "Invalid color value: #GG0000"),
    ({"outline_color": "#GG0000"}, "Invalid outline_color value: #GG0000"),
    ({"shadow_color": "#GG0000"}, "Invalid shadow_color value: #GG0000"),
])
def test_each_colour_argument_is_reported_by_name(canvas_file, bitmap_font,
                                                  kwargs, expected):
    assert run(text.draw_text(canvas_file, "A", 0, 0, bitmap_font,
                              layer_name="body", **kwargs)) == expected


# ── decorations ───────────────────────────────────────────────────────

def test_an_outline_surrounds_the_glyph_without_moving_it(canvas_file, bitmap_font):
    plain = ok(run(text.draw_text(canvas_file, "O", 4, 12, bitmap_font,
                                  color="#FFFFFF", layer_name="body")))
    outlined = ok(run(text.draw_text(canvas_file, "O", 16, 12, bitmap_font,
                                     color="#FFFFFF", layer_name="body",
                                     outline_color="#FF0000")))
    assert blit_origin(plain)[1] == blit_origin(outlined)[1] + 1
    assert stamp_size(plain) == (4, 5)
    assert stamp_size(outlined) == (6, 7)
    assert pixel(canvas_file, 16, 12, "body") == "#ff0000"


def test_a_wider_outline_grows_the_stamp_further(canvas_file, bitmap_font):
    thin = ok(run(text.draw_text(canvas_file, "O", 4, 20, bitmap_font,
                                 layer_name="body", outline_color="#FF0000")))
    thick = ok(run(text.draw_text(canvas_file, "O", 16, 20, bitmap_font,
                                  layer_name="body", outline_color="#FF0000",
                                  outline_width=2)))
    assert stamp_size(thick)[0] > stamp_size(thin)[0]


def test_a_square_outline_omits_the_diagonals(canvas_file, bitmap_font):
    rounded = ok(run(text.draw_text(canvas_file, "B", 4, 4, bitmap_font,
                                    layer_name="body", outline_color="#FF0000")))
    boxy = ok(run(text.draw_text(canvas_file, "B", 16, 4, bitmap_font,
                                 layer_name="body", outline_color="#FF0000",
                                 outline_diagonal=False)))
    assert stamp_size(rounded) == stamp_size(boxy)
    # the rounded form fills the corner the 4-way form leaves empty
    rounded_corner = pixel(canvas_file, 3, 3, "body")
    boxy_corner = pixel(canvas_file, 15, 3, "body")
    assert rounded_corner != boxy_corner


def test_a_shadow_is_offset_from_the_glyph(canvas_file, bitmap_font):
    """'O' is a ring, so its bottom-right shadow shows past the outer edge."""
    ok(run(text.draw_text(canvas_file, "O", 8, 8, bitmap_font,
                          color="#FFFFFF", layer_name="body",
                          shadow_color="#0000FF", shadow_dx=2, shadow_dy=2)))
    assert pixel(canvas_file, 9, 8, "body") == "#ffffff"
    assert pixel(canvas_file, 13, 13, "body") == "#0000ff"
    assert pixel(canvas_file, 11, 14, "body") == "#0000ff"


def test_a_shadow_never_covers_the_glyph(canvas_file, bitmap_font):
    ok(run(text.draw_text(canvas_file, "O", 8, 16, bitmap_font,
                          color="#FFFFFF", layer_name="body",
                          shadow_color="#0000FF", shadow_dx=0, shadow_dy=0)))
    assert pixel(canvas_file, 9, 16, "body") == "#ffffff"


def test_an_outline_and_a_shadow_compose(canvas_file, bitmap_font):
    plain = ok(run(text.draw_text(canvas_file, "O", 2, 22, bitmap_font,
                                  layer_name="body")))
    both = ok(run(text.draw_text(canvas_file, "O", 10, 10, bitmap_font,
                                 color="#FFFFFF", layer_name="body",
                                 outline_color="#FF0000",
                                 shadow_color="#0000FF", shadow_dx=3, shadow_dy=3)))
    # outline adds 1px on each side; the shadow then extends 3px down-right
    # but is clipped back by the outline it overlaps.
    assert stamp_size(plain) == (4, 5)
    assert stamp_size(both) == (8, 9)


def test_bold_thickens_the_drawn_glyph(canvas_file, bitmap_font):
    plain = ok(run(text.draw_text(canvas_file, "O", 2, 2, bitmap_font, size=2,
                                  layer_name="body")))
    bold = ok(run(text.draw_text(canvas_file, "O", 16, 2, bitmap_font, size=2,
                                 layer_name="body", bold=1)))
    assert stamp_size(bold)[0] > stamp_size(plain)[0]


# ── layer and frame handling ──────────────────────────────────────────

def test_draw_text_creates_a_missing_layer(canvas_file, bitmap_font):
    ok(run(text.draw_text(canvas_file, "A", 2, 2, bitmap_font,
                          layer_name="captions")))
    assert pixel(canvas_file, 3, 2, "captions") == "#ffffff"


def test_draw_text_can_refuse_to_create_the_layer(canvas_file, bitmap_font):
    out = run(text.draw_text(canvas_file, "A", 2, 2, bitmap_font,
                             layer_name="absent", create_if_missing=False))
    assert "Layer not found" in out


def test_draw_text_uses_the_active_layer_when_none_is_named(canvas_file, bitmap_font):
    ok(run(text.draw_text(canvas_file, "A", 20, 20, bitmap_font)))


def test_draw_text_rejects_a_frame_past_the_end(canvas_file, bitmap_font):
    out = run(text.draw_text(canvas_file, "A", 0, 0, bitmap_font,
                             layer_name="body", frame_index=9))
    assert "Frame index out of range" in out


def test_draw_text_reports_a_missing_file(bitmap_font):
    missing = f"{BASE}/no-such-text-target.aseprite"
    assert run(text.draw_text(missing, "A", 0, 0, bitmap_font)) == \
        f"File {missing} not found"


def test_draw_text_reports_an_unknown_font(canvas_file):
    out = run(text.draw_text(canvas_file, "A", 0, 0, "no-such-font"))
    assert out.startswith("ERROR") and "not found" in out


def test_the_temporary_stamp_is_cleaned_up(canvas_file, bitmap_font, tmp_path,
                                           monkeypatch):
    """The PNG handed to Aseprite must not accumulate in the temp directory."""
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    ok(run(text.draw_text(canvas_file, "AB", 0, 0, bitmap_font, layer_name="body")))
    assert [p for p in os.listdir(tmp_path) if p.endswith(".png")] == []


def test_text_with_no_renderable_glyphs_is_a_no_op(canvas_file, bitmap_font):
    assert run(text.draw_text(canvas_file, "???", 0, 0, bitmap_font)).startswith(
        "OK: nothing to draw")


# ── list_text_fonts ───────────────────────────────────────────────────

def test_list_fonts_reports_both_sections(tmp_path, monkeypatch):
    fontdir = tmp_path / "userfonts"
    fontdir.mkdir()
    (fontdir / "Mine.ttf").write_bytes(b"placeholder")
    monkeypatch.setattr(fontlib, "FONT_DIR", str(fontdir))

    out = ok(run(text.list_text_fonts()))
    assert "User fonts" in out and "Mine" in out
    assert "System fonts" in out


def test_list_fonts_says_so_when_there_are_none(monkeypatch):
    monkeypatch.setattr(fontlib, "available_fonts", lambda: [])
    assert run(text.list_text_fonts()) == \
        "No fonts found. Drop a .ttf into ~/.aseprite-mcp/fonts/."


def test_list_fonts_omits_the_user_section_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(fontlib, "FONT_DIR", str(tmp_path / "absent"))
    out = ok(run(text.list_text_fonts()))
    assert "User fonts" not in out
    assert "System fonts" in out


# ── measure_text ──────────────────────────────────────────────────────

def test_measure_reports_every_metric(bitmap_font):
    out = ok(run(text.measure_text("AB", bitmap_font, 2)))
    for field in ("width=", "height=", "advance_width=", "above_baseline=",
                  "below_baseline=", "left_bearing="):
        assert field in out


def test_measure_reports_a_font_error_rather_than_raising():
    out = run(text.measure_text("A", "not-a-font-at-all"))
    assert out.startswith("ERROR")


def test_measure_rejects_negative_bold(bitmap_font):
    out = run(text.measure_text("A", bitmap_font, 1, bold=-1))
    assert out.startswith("ERROR") and "bold" in out
