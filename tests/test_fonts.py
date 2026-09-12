"""Font loading, discovery and rasterisation (core/fonts.py).

The bitmap fixtures are built on disk so the tests run anywhere; the
TrueType half uses DejaVu, which the CI image installs (fonts-dejavu-core)
and which every desktop Linux ships, so it is a hard requirement rather
than a skip.
"""
import json
import os
import pathlib

import pytest
from conftest import ok, run
from PIL import Image

from aseprite_mcp.core import fonts as fontlib
from aseprite_mcp.tools import text

GLYPHS = {
    "A": [".##.", "#..#", "####", "#..#", "#..#", "...."],
    "B": ["###.", "#..#", "###.", "#..#", "###.", "...."],
    "O": [".##.", "#..#", "#..#", "#..#", ".##.", "...."],
}
CELL_W, CELL_H, ASCENT = 4, 6, 5


@pytest.fixture(autouse=True)
def fresh_cache():
    fontlib.clear_cache()
    yield
    fontlib.clear_cache()


def write_sheet(directory, chars, ink=(255, 255, 255, 255), background=(0, 0, 0, 0)):
    sheet = Image.new("RGBA", (CELL_W * len(chars), CELL_H), background)
    for index, char in enumerate(chars):
        for y, row in enumerate(GLYPHS[char]):
            for x, cell in enumerate(row):
                if cell == "#":
                    sheet.putpixel((index * CELL_W + x, y), ink)
    sheet.save(os.path.join(directory, "sheet.png"))


def write_font(tmp_path, name="fixture", chars="ABO", **overrides):
    directory = pathlib.Path(tmp_path) / name
    directory.mkdir(exist_ok=True, parents=True)
    write_sheet(str(directory), chars,
                ink=overrides.pop("ink", (255, 255, 255, 255)),
                background=overrides.pop("background", (0, 0, 0, 0)))
    sheet_spec = {
        "file": "sheet.png",
        "cell_w": CELL_W, "cell_h": CELL_H, "ascent": ASCENT,
        "chars": [chars],
    }
    sheet_spec.update(overrides.pop("sheet", {}))
    spec = {
        "name": name,
        "letter_gap": 1,
        "space_width": 2,
        "sheets": [sheet_spec],
    }
    spec.update(overrides)
    (directory / "font.json").write_text(json.dumps(spec))
    return str(directory)


def dejavu():
    for entry in fontlib.available_fonts():
        if entry["kind"] == "truetype" and entry["name"].startswith("DejaVuSans"):
            return entry["path"]
    pytest.fail("DejaVu is required: install fonts-dejavu-core")


# ── descriptor errors ─────────────────────────────────────────────────

def test_a_missing_descriptor_is_a_font_error(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(fontlib.FontError, match="Could not read"):
        fontlib.BitmapFont(str(empty))


def test_malformed_json_is_a_font_error(tmp_path):
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "font.json").write_text("{not json")
    with pytest.raises(fontlib.FontError, match="Could not read"):
        fontlib.BitmapFont(str(broken))


def test_a_descriptor_with_no_sheets_is_rejected(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "font.json").write_text(json.dumps({"name": "bare", "sheets": []}))
    with pytest.raises(fontlib.FontError, match="declares no sheets"):
        fontlib.BitmapFont(str(bare))


def test_a_missing_sheet_file_is_reported(tmp_path):
    directory = tmp_path / "nosheet"
    directory.mkdir()
    (directory / "font.json").write_text(json.dumps({
        "sheets": [{"file": "absent.png", "cell_w": 4, "cell_h": 6, "ascent": 5,
                    "chars": ["A"]}],
    }))
    with pytest.raises(fontlib.FontError, match="Bad sheet"):
        fontlib.BitmapFont(str(directory))


def test_a_sheet_entry_without_a_file_key_is_reported(tmp_path):
    directory = tmp_path / "nofile"
    directory.mkdir()
    write_sheet(str(directory), "A")
    (directory / "font.json").write_text(json.dumps({
        "sheets": [{"cell_w": 4, "cell_h": 6, "ascent": 5, "chars": ["A"]}],
    }))
    with pytest.raises(fontlib.FontError, match="Bad sheet"):
        fontlib.BitmapFont(str(directory))


def test_the_descriptor_name_defaults_to_the_directory(tmp_path):
    directory = tmp_path / "named"
    directory.mkdir()
    write_sheet(str(directory), "A")
    (directory / "font.json").write_text(json.dumps({
        "sheets": [{"file": "sheet.png", "cell_w": 4, "cell_h": 6, "ascent": 5,
                    "chars": ["A"]}],
    }))
    assert fontlib.BitmapFont(str(directory)).name == "named"


# ── sheet semantics ───────────────────────────────────────────────────

def test_the_first_sheet_to_claim_a_codepoint_wins(tmp_path):
    directory = tmp_path / "layered"
    directory.mkdir()
    write_sheet(str(directory), "AB")
    Image.new("RGBA", (CELL_W * 2, CELL_H), (255, 255, 255, 255)).save(
        directory / "fallback.png")
    (directory / "font.json").write_text(json.dumps({
        "sheets": [
            {"file": "sheet.png", "cell_w": CELL_W, "cell_h": CELL_H,
             "ascent": ASCENT, "chars": ["AB"]},
            {"file": "fallback.png", "cell_w": CELL_W, "cell_h": CELL_H,
             "ascent": ASCENT, "chars": ["AB"]},
        ],
    }))
    font = fontlib.BitmapFont(str(directory))
    ink, _ = fontlib.shape("A", font, 1)
    # the second, solid-white sheet would be a full 4x6 block
    assert len(ink) == len([c for row in GLYPHS["A"] for c in row if c == "#"])


def test_the_dark_ink_rule_reads_dark_pixels_as_ink(tmp_path):
    """Aseprite's own sheets are dark glyphs whose box ends at opaque white.

    The box is measured from the cell origin until the first white pixel, so
    the fixture is a solid 3x4 dark block in the corner of a 6x6 white cell.
    """
    directory = pathlib.Path(tmp_path) / "darkfont"
    directory.mkdir(parents=True)
    sheet = Image.new("RGBA", (6, 6), (255, 255, 255, 255))
    for y in range(4):
        for x in range(3):
            sheet.putpixel((x, y), (0, 0, 0, 255))
    sheet.save(directory / "sheet.png")
    (directory / "font.json").write_text(json.dumps({
        "sheets": [{"file": "sheet.png", "cell_w": 6, "cell_h": 6, "ascent": 4,
                    "ink_rule": "dark", "chars": ["A"]}],
    }))

    ink, metrics = fontlib.shape("A", fontlib.BitmapFont(str(directory)), 1)
    assert len(ink) == 12, "the 3x4 dark block is the glyph"
    assert (metrics["width"], metrics["height"]) == (3, 4)


def test_the_dark_ink_rule_ignores_a_light_grey_pixel(tmp_path):
    """Only pixels below the darkness threshold count as ink."""
    directory = pathlib.Path(tmp_path) / "greyfont"
    directory.mkdir(parents=True)
    sheet = Image.new("RGBA", (6, 6), (255, 255, 255, 255))
    sheet.putpixel((0, 0), (0, 0, 0, 255))
    sheet.putpixel((1, 0), (200, 200, 200, 255))
    sheet.putpixel((0, 1), (10, 10, 10, 255))
    sheet.save(directory / "sheet.png")
    (directory / "font.json").write_text(json.dumps({
        "sheets": [{"file": "sheet.png", "cell_w": 6, "cell_h": 6, "ascent": 2,
                    "ink_rule": "dark", "chars": ["A"]}],
    }))
    # shape() reports y relative to the baseline, so ascent=2 shifts the two
    # glyph rows to -2 and -1.
    ink, _ = fontlib.shape("A", fontlib.BitmapFont(str(directory)), 1)
    assert ink == {(0, -2), (0, -1)}, "only the dark column is ink"


def test_box_advance_uses_the_cell_width(tmp_path):
    ink_advance = write_font(tmp_path, "inkadv", sheet={"advance": "ink"})
    box_advance = write_font(tmp_path, "boxadv", sheet={"advance": "box"})
    _, ink_metrics = fontlib.shape("A", fontlib.load_font(ink_advance), 1)
    _, box_metrics = fontlib.shape("A", fontlib.load_font(box_advance), 1)
    assert ink_metrics["advance_width"] == 5   # 4px ink + 1px letter_gap
    assert box_metrics["advance_width"] == 4   # the 4px cell


def test_a_sheet_origin_offsets_the_cell_grid(tmp_path):
    directory = tmp_path / "origin"
    directory.mkdir()
    shifted = Image.new("RGBA", (CELL_W + 2, CELL_H + 2), (0, 0, 0, 0))
    for y, row in enumerate(GLYPHS["A"]):
        for x, cell in enumerate(row):
            if cell == "#":
                shifted.putpixel((x + 2, y + 2), (255, 255, 255, 255))
    shifted.save(directory / "sheet.png")
    (directory / "font.json").write_text(json.dumps({
        "sheets": [{"file": "sheet.png", "cell_w": CELL_W, "cell_h": CELL_H,
                    "ascent": ASCENT, "origin": [2, 2], "chars": ["A"]}],
    }))
    ink, _ = fontlib.shape("A", fontlib.BitmapFont(str(directory)), 1)
    assert len(ink) == len([c for row in GLYPHS["A"] for c in row if c == "#"])


def test_an_empty_glyph_falls_back_to_space_width(tmp_path):
    directory = tmp_path / "blank"
    directory.mkdir()
    Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0)).save(directory / "sheet.png")
    (directory / "font.json").write_text(json.dumps({
        "space_width": 7, "letter_gap": 1,
        "sheets": [{"file": "sheet.png", "cell_w": CELL_W, "cell_h": CELL_H,
                    "ascent": ASCENT, "chars": [" "]}],
    }))
    _, metrics = fontlib.shape(" ", fontlib.BitmapFont(str(directory)), 1)
    assert metrics["advance_width"] == 8   # 7px space + 1px gap
    assert metrics["width"] == 0


def test_the_glyph_cache_returns_the_same_object(tmp_path):
    font = fontlib.load_font(write_font(tmp_path))
    assert font.glyph(ord("A")) is font.glyph(ord("A"))
    assert font.glyph(ord("Z")) is None
    assert font.glyph(ord("Z")) is None    # the negative result is cached too


def test_overrides_without_an_ascent_use_the_row_count(tmp_path):
    path = write_font(tmp_path, "override_default",
                      overrides={str(ord("A")): {"rows": ["##", "##"]}})
    ink, metrics = fontlib.shape("A", fontlib.load_font(path), 1)
    assert len(ink) == 4
    assert metrics["top"] == -2, "ascent should default to the row count"


# ── shaping ───────────────────────────────────────────────────────────

def test_negative_bold_is_rejected(tmp_path):
    font = fontlib.load_font(write_font(tmp_path))
    with pytest.raises(fontlib.FontError, match="bold must be >= 0"):
        fontlib.shape("A", font, 1, bold=-1)


def test_a_zero_scale_is_rejected_for_bitmap_fonts(tmp_path):
    font = fontlib.load_font(write_font(tmp_path))
    with pytest.raises(fontlib.FontError, match="scale factor"):
        fontlib.shape("A", font, 0)


def test_a_zero_size_is_rejected_for_truetype_fonts():
    with pytest.raises(fontlib.FontError, match="pixel height"):
        fontlib.shape("A", fontlib.load_font(dejavu()), 0)


def test_bold_widens_the_advance(tmp_path):
    font = fontlib.load_font(write_font(tmp_path))
    _, plain = fontlib.shape("A", font, 1)
    _, bold = fontlib.shape("A", font, 1, bold=2)
    assert bold["advance_width"] == plain["advance_width"] + 2


def test_dilate_grows_right_and_down_only():
    grown = fontlib._dilate({(0, 0)}, 1)
    assert grown == {(0, 0), (1, 0), (0, 1)}


# ── discovery ─────────────────────────────────────────────────────────

def test_user_fonts_are_listed_before_system_fonts(tmp_path, monkeypatch):
    fontdir = tmp_path / "userfonts"
    fontdir.mkdir()
    write_font(str(fontdir), "mybitmap")
    (fontdir / "MyFace.ttf").write_bytes(b"not really a font")
    monkeypatch.setattr(fontlib, "FONT_DIR", str(fontdir))

    found = fontlib.available_fonts()
    user = [entry for entry in found if entry["source"] == "user"]
    assert {entry["name"] for entry in user} == {"mybitmap", "MyFace"}
    assert {entry["kind"] for entry in user} == {"bitmap", "truetype"}
    assert found.index(user[0]) < len(user)


def test_a_missing_user_font_directory_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(fontlib, "FONT_DIR", str(tmp_path / "absent"))
    assert list(fontlib._iter_user_fonts()) == []


def test_a_user_font_shadows_a_system_font_of_the_same_name(tmp_path, monkeypatch):
    system_name = os.path.splitext(os.path.basename(dejavu()))[0]
    fontdir = tmp_path / "shadow"
    fontdir.mkdir()
    (fontdir / f"{system_name}.ttf").write_bytes(b"placeholder")
    monkeypatch.setattr(fontlib, "FONT_DIR", str(fontdir))

    matches = [e for e in fontlib.available_fonts() if e["name"] == system_name]
    assert len(matches) == 1 and matches[0]["source"] == "user"


def test_an_unreadable_system_font_directory_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(fontlib, "_SYSTEM_FONT_DIRS", (str(tmp_path / "absent"),))
    assert list(fontlib._iter_system_fonts()) == []


def test_system_fonts_are_found_inside_subdirectories(tmp_path, monkeypatch):
    nested = tmp_path / "truetype" / "family"
    nested.mkdir(parents=True)
    (nested / "Nested.ttf").write_bytes(b"placeholder")
    monkeypatch.setattr(fontlib, "_SYSTEM_FONT_DIRS", (str(tmp_path),))
    assert [name for name, _, _ in fontlib._iter_system_fonts()] == ["Nested"]


def test_the_subdirectory_walk_has_a_depth_limit(tmp_path, monkeypatch):
    too_deep = tmp_path / "a" / "b" / "c"
    too_deep.mkdir(parents=True)
    (too_deep / "TooDeep.ttf").write_bytes(b"placeholder")
    monkeypatch.setattr(fontlib, "_SYSTEM_FONT_DIRS", (str(tmp_path),))
    assert list(fontlib._iter_system_fonts()) == []


def test_the_real_system_font_directories_contain_dejavu():
    """Guards the regression that made discovery return nothing on Linux."""
    names = {entry["name"] for entry in fontlib.available_fonts()}
    assert any(name.startswith("DejaVuSans") for name in names)


# ── resolution ────────────────────────────────────────────────────────

def test_a_font_can_be_resolved_by_name(tmp_path, monkeypatch):
    fontdir = tmp_path / "byname"
    fontdir.mkdir()
    write_font(str(fontdir), "namedfont")
    monkeypatch.setattr(fontlib, "FONT_DIR", str(fontdir))
    fontlib.clear_cache()
    assert isinstance(fontlib.load_font("NAMEDFONT"), fontlib.BitmapFont)


def test_a_font_path_can_point_straight_at_a_ttf():
    assert isinstance(fontlib.load_font(dejavu()), fontlib.TrueTypeFont)


def test_an_unknown_font_names_the_discovery_tool():
    with pytest.raises(fontlib.FontError, match="list_text_fonts"):
        fontlib.load_font("no-such-font-anywhere")


def test_resolved_fonts_are_cached_until_cleared(tmp_path):
    path = write_font(tmp_path)
    first = fontlib.load_font(path)
    assert fontlib.load_font(path) is first
    fontlib.clear_cache()
    assert fontlib.load_font(path) is not first


def test_a_directory_without_a_descriptor_is_not_a_bitmap_font(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(fontlib.FontError, match="not found"):
        fontlib.load_font(str(plain))


# ── truetype ──────────────────────────────────────────────────────────

def test_truetype_rasterises_hard_pixels_by_default():
    ink, metrics = fontlib.shape("A", fontlib.load_font(dejavu()), 24)
    assert ink and metrics["height"] > 8


def test_antialias_keeps_more_pixels_than_thresholding():
    font = fontlib.load_font(dejavu())
    hard, _ = fontlib.shape("A", font, 24)
    soft, _ = fontlib.shape("A", font, 24, antialias=True)
    assert len(soft) > len(hard)
    assert hard <= soft


def test_truetype_letter_spacing_widens_the_advance():
    font = fontlib.load_font(dejavu())
    _, tight = fontlib.shape("AB", font, 20, letter_spacing=0)
    _, loose = fontlib.shape("AB", font, 20, letter_spacing=4)
    # spacing is injected per glyph, so the run also loses the kerning the
    # single-shot path applies; it must still be strictly wider.
    assert loose["advance_width"] > tight["advance_width"]
    assert loose["width"] > tight["width"]


def test_truetype_glyphs_sit_above_the_baseline():
    _, metrics = fontlib.shape("A", fontlib.load_font(dejavu()), 20)
    assert metrics["top"] < 0 and metrics["bottom"] <= 0


def test_a_broken_truetype_file_is_reported(tmp_path):
    fake = tmp_path / "Broken.ttf"
    fake.write_bytes(b"definitely not a font")
    with pytest.raises(fontlib.FontError, match="Could not load font"):
        fontlib.shape("A", fontlib.TrueTypeFont(str(fake)), 12)


def test_measure_text_reports_truetype_metrics():
    out = ok(run(text.measure_text("Hi", dejavu(), 16)))
    assert "width=" in out and "advance_width=" in out
