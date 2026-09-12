"""Export and import (tools/export.py).

Exports are checked by opening the produced file with Pillow — dimensions,
frame count and JSON schema — rather than trusting the success string.
"""
import glob
import json
import os

import pytest
from conftest import BASE, new_sprite, ok, pixel, run
from PIL import Image

from aseprite_mcp.tools import animation, canvas, drawing, export


@pytest.fixture(scope="module")
def sheet_source():
    """A 16x16 sprite, 4 frames, tagged 'walk' over frames 2-3."""
    path = new_sprite("export_source", 16, 16)
    ok(run(animation.add_frames(path, 3)))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 16, 16, "#D04648", True)))
    ok(run(animation.propagate_frame_to_range(path, 1, 2, 4)))
    ok(run(animation.set_tag(path, "walk", 2, 3)))
    return path


@pytest.fixture(scope="module")
def outdir():
    path = f"{BASE}/exports"
    os.makedirs(path, exist_ok=True)
    return path


# ── export_sprite ─────────────────────────────────────────────────────

def test_export_png_appends_the_extension(sheet_source, outdir):
    out = f"{outdir}/plain"
    ok(run(export.export_sprite(sheet_source, out, "png")))
    produced = sorted(glob.glob(f"{out}*.png"))
    assert produced, "no PNG written"
    assert Image.open(produced[0]).size == (16, 16)


def test_export_gif_keeps_every_frame(sheet_source, outdir):
    out = f"{outdir}/anim.gif"
    ok(run(export.export_sprite(sheet_source, out, "gif")))
    with Image.open(out) as img:
        assert img.n_frames == 4


def test_export_uppercase_format_is_normalised(sheet_source, outdir):
    out = f"{outdir}/upper.png"
    ok(run(export.export_sprite(sheet_source, out, "PNG")))
    assert glob.glob(f"{outdir}/upper*.png")


def test_export_to_an_unwritable_format_is_reported(sheet_source, outdir):
    assert "Failed" in run(export.export_sprite(sheet_source, f"{outdir}/x", "json"))


# ── copy_sprite ───────────────────────────────────────────────────────

def test_copy_sprite_produces_an_openable_duplicate(sheet_source, outdir):
    out = f"{outdir}/copy.aseprite"
    ok(run(export.copy_sprite(sheet_source, out)))
    data = json.loads(ok(run(animation.get_sprite_info(out))))
    assert data["frames"] == 4 and data["width"] == 16


def test_copy_sprite_refuses_to_clobber_by_default(sheet_source, outdir):
    out = f"{outdir}/copy.aseprite"
    assert "already exists" in run(export.copy_sprite(sheet_source, out))


def test_copy_sprite_overwrites_on_request(sheet_source, outdir):
    out = f"{outdir}/copy.aseprite"
    ok(run(export.copy_sprite(sheet_source, out, overwrite=True)))


def test_copy_sprite_appends_the_aseprite_extension(sheet_source, outdir):
    ok(run(export.copy_sprite(sheet_source, f"{outdir}/noext")))
    assert os.path.exists(f"{outdir}/noext.aseprite")


# ── export_frame ──────────────────────────────────────────────────────

def test_export_frame_writes_exactly_that_frame(sheet_source, outdir):
    out = f"{outdir}/frame2.png"
    ok(run(export.export_frame(sheet_source, 2, out)))
    assert Image.open(out).size == (16, 16)


def test_export_frame_scales_by_whole_pixels(sheet_source, outdir):
    out = f"{outdir}/frame_scaled.png"
    ok(run(export.export_frame(sheet_source, 1, out, scale=4)))
    assert Image.open(out).size == (64, 64)


def test_export_frame_appends_png(sheet_source, outdir):
    ok(run(export.export_frame(sheet_source, 1, f"{outdir}/frame_noext")))
    assert os.path.exists(f"{outdir}/frame_noext.png")


@pytest.mark.parametrize("scale", [0, 65])
def test_export_frame_rejects_an_out_of_range_scale(sheet_source, outdir, scale):
    assert run(export.export_frame(sheet_source, 1, f"{outdir}/s.png", scale)) == \
        "scale must be between 1 and 64"


# ── export_spritesheet ────────────────────────────────────────────────

def test_horizontal_sheet_is_as_wide_as_the_frame_count(sheet_source, outdir):
    out = f"{outdir}/sheet_h.png"
    ok(run(export.export_spritesheet(sheet_source, out, "horizontal")))
    assert Image.open(out).size == (64, 16)


def test_vertical_sheet_stacks_the_frames(sheet_source, outdir):
    out = f"{outdir}/sheet_v.png"
    ok(run(export.export_spritesheet(sheet_source, out, "vertical")))
    assert Image.open(out).size == (16, 64)


@pytest.mark.parametrize("sheet_type", ["rows", "columns", "packed"])
def test_every_supported_sheet_type_produces_an_image(sheet_source, outdir, sheet_type):
    out = f"{outdir}/sheet_{sheet_type}.png"
    ok(run(export.export_spritesheet(sheet_source, out, sheet_type)))
    assert Image.open(out).size[0] > 0


def test_sheet_scale_and_padding_change_the_geometry(sheet_source, outdir):
    plain = f"{outdir}/sheet_plain.png"
    padded = f"{outdir}/sheet_padded.png"
    ok(run(export.export_spritesheet(sheet_source, plain, "horizontal")))
    ok(run(export.export_spritesheet(sheet_source, padded, "horizontal",
                                     scale=2, padding=2)))
    assert Image.open(padded).size[0] > Image.open(plain).size[0] * 2


def test_json_array_data_file_lists_frames_as_an_array(sheet_source, outdir):
    out = f"{outdir}/sheet_array.png"
    data_file = f"{outdir}/sheet_array.json"
    ok(run(export.export_spritesheet(sheet_source, out, "horizontal", data_file)))
    data = json.loads(open(data_file).read())
    assert isinstance(data["frames"], list) and len(data["frames"]) == 4


def test_json_hash_data_file_keys_frames_by_name(sheet_source, outdir):
    out = f"{outdir}/sheet_hash.png"
    data_file = f"{outdir}/sheet_hash.json"
    ok(run(export.export_spritesheet(sheet_source, out, "horizontal", data_file,
                                     data_format="json-hash")))
    data = json.loads(open(data_file).read())
    assert isinstance(data["frames"], dict) and len(data["frames"]) == 4


def test_list_tags_adds_the_tag_metadata(sheet_source, outdir):
    out = f"{outdir}/sheet_tags.png"
    data_file = f"{outdir}/sheet_tags.json"
    ok(run(export.export_spritesheet(sheet_source, out, "horizontal", data_file,
                                     list_tags=True)))
    meta = json.loads(open(data_file).read())["meta"]
    assert [tag["name"] for tag in meta["frameTags"]] == ["walk"]


def test_tag_filter_exports_only_the_tagged_frames(sheet_source, outdir):
    out = f"{outdir}/sheet_walk.png"
    ok(run(export.export_spritesheet(sheet_source, out, "horizontal",
                                     tag_name="walk")))
    assert Image.open(out).size == (32, 16)


def test_sheet_appends_png(sheet_source, outdir):
    ok(run(export.export_spritesheet(sheet_source, f"{outdir}/sheet_noext")))
    assert os.path.exists(f"{outdir}/sheet_noext.png")


@pytest.mark.parametrize("kwargs,expected", [
    ({"sheet_type": "diagonal"},
     "sheet_type must be one of: horizontal, vertical, rows, columns, packed"),
    ({"scale": 0}, "scale must be between 1 and 64"),
    ({"scale": 999}, "scale must be between 1 and 64"),
    ({"padding": -1}, "padding must be >= 0"),
    ({"data_format": "yaml"}, "data_format must be 'json-array' or 'json-hash'"),
])
def test_spritesheet_validates_its_arguments(sheet_source, outdir, kwargs, expected):
    assert run(export.export_spritesheet(
        sheet_source, f"{outdir}/bad.png", **kwargs)) == expected


# ── export_layers ─────────────────────────────────────────────────────

def test_export_layers_writes_one_png_per_visible_layer(outdir):
    path = new_sprite("export_layers", 8, 8)
    ok(run(canvas.add_layer(path, "fx")))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 8, 8, "#D04648", True)))
    ok(run(drawing.draw_rectangle_at(path, "fx", 1, 0, 0, 4, 4, "#00FF00", True)))
    target = f"{outdir}/layers"
    ok(run(export.export_layers(path, target)))
    produced = {os.path.basename(p) for p in glob.glob(f"{target}/*.png")}
    assert {"body.png", "fx.png"} <= produced


def test_export_layers_skips_hidden_layers_by_default(outdir):
    path = new_sprite("export_hidden", 8, 8)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 8, 8, "#D04648", True)))
    ok(run(canvas.add_layer(path, "secret")))
    ok(run(drawing.draw_rectangle_at(path, "secret", 1, 0, 0, 4, 4, "#00FF00", True)))
    ok(run(animation.set_layer_visibility(path, "secret", False)))

    visible_only = f"{outdir}/layers_visible"
    ok(run(export.export_layers(path, visible_only)))
    assert not os.path.exists(f"{visible_only}/secret.png")

    everything = f"{outdir}/layers_all"
    ok(run(export.export_layers(path, everything, include_hidden=True)))
    assert os.path.exists(f"{everything}/secret.png")


def test_export_layers_creates_the_output_directory(outdir):
    path = new_sprite("export_layers_mkdir", 8, 8)
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 0, 0, 8, 8, "#D04648", True)))
    target = f"{outdir}/made/up/deep"
    ok(run(export.export_layers(path, target)))
    assert glob.glob(f"{target}/*.png")


# ── export_tag ────────────────────────────────────────────────────────

def test_export_tag_writes_only_the_tagged_frames(sheet_source, outdir):
    out = f"{outdir}/walk.gif"
    ok(run(export.export_tag(sheet_source, "walk", out)))
    with Image.open(out) as img:
        assert img.n_frames == 2


def test_export_tag_can_scale(sheet_source, outdir):
    out = f"{outdir}/walk_big.gif"
    ok(run(export.export_tag(sheet_source, "walk", out, scale=3)))
    with Image.open(out) as img:
        assert img.size == (48, 48)


def test_export_tag_rejects_a_bad_scale(sheet_source, outdir):
    assert run(export.export_tag(sheet_source, "walk", f"{outdir}/x.gif", 0)) == \
        "scale must be between 1 and 64"


# ── import_image_as_layer ─────────────────────────────────────────────

def test_import_image_creates_the_layer_and_blits_the_pixels(outdir):
    source = f"{outdir}/import_src.png"
    Image.new("RGBA", (6, 6), (0, 128, 255, 255)).save(source)

    path = new_sprite("export_import", 16, 16)
    ok(run(export.import_image_as_layer(path, source, "imported", 1, 4, 4)))
    assert pixel(path, 5, 5, "imported") == "#0080ff"
    assert pixel(path, 0, 0, "imported") != "#0080ff"


def test_import_image_reuses_an_existing_layer(outdir):
    source = f"{outdir}/import_src2.png"
    Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(source)
    path = new_sprite("export_import_existing", 16, 16)
    ok(run(export.import_image_as_layer(path, source, "body", 1, 0, 0)))
    layers = json.loads(ok(run(animation.get_sprite_info(path))))["layers"]
    assert [layer["name"] for layer in layers].count("body") == 1


def test_import_image_reports_a_missing_source():
    path = new_sprite("export_import_missing", 8, 8)
    assert "not found" in run(export.import_image_as_layer(
        path, f"{BASE}/no-such-image.png", "x"))


def test_import_image_rejects_a_frame_past_the_end(outdir):
    source = f"{outdir}/import_src3.png"
    Image.new("RGBA", (2, 2), (1, 2, 3, 255)).save(source)
    path = new_sprite("export_import_frame", 8, 8)
    assert "Failed" in run(export.import_image_as_layer(path, source, "x", 9))
