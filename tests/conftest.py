"""Shared fixtures for the end-to-end tool tests.

These tests run each MCP tool against a real Aseprite (ASEPRITE_PATH),
so they are smoke/integration tests, not unit tests. Tests within a
file form a sequence on a module-scoped sprite; files are independent.

Scratch files live under a fixed /tmp path (not pytest's tmp_path) so
they resolve identically inside the Docker-wrapped Aseprite, which only
mounts /tmp and /var/folders.
"""
import asyncio
import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import aseprite_mcp.tools  # noqa: F401  (registers all tools)
from aseprite_mcp.tools import canvas, drawing, pixel_read, quality

BASE = "/tmp/ase-pytest"


def run(coro):
    """Execute an async tool call from a sync test."""
    return asyncio.run(coro)


def ok(result):
    """Assert a tool call did not return an error message."""
    assert not str(result).startswith(
        ("Failed", "ERROR", "Invalid", "Script failed")
    ), result
    return result


@pytest.fixture(scope="session", autouse=True)
def base_dir():
    shutil.rmtree(BASE, ignore_errors=True)
    os.makedirs(BASE, exist_ok=True)
    return BASE


@pytest.fixture(scope="module")
def sprite(request, base_dir):
    """A fresh 32x32 sprite per test module with a painted 'body' layer."""
    name = request.module.__name__.removeprefix("tests.").removeprefix("test_")
    path = f"{BASE}/{name}.aseprite"
    ok(run(canvas.create_canvas(32, 32, path)))
    ok(run(canvas.add_layer(path, "body")))
    ok(run(drawing.draw_rectangle_at(path, "body", 1, 8, 8, 16, 16, "#D04648", True)))
    return path


def new_sprite(name, width=32, height=32, layer="body"):
    """Create a standalone sprite outside the module fixture's sequence.

    Tests that mutate frame counts or layer stacks need their own file so
    they do not perturb the module-scoped `sprite` other tests share.
    """
    path = f"{BASE}/{name}.aseprite"
    ok(run(canvas.create_canvas(width, height, path)))
    if layer:
        ok(run(canvas.add_layer(path, layer)))
    return path


def cel_bounds(filename, layer_name, frame_index):
    """Read one cel's (x, y, w, h) back out of the file, or None if absent.

    Position assertions go through audit_animation because that is the only
    tool that reports cel geometry, which keeps the check on observable
    output rather than on a tool's own success string.
    """
    report = json.loads(run(quality.audit_animation(
        filename,
        start_frame=frame_index,
        end_frame=frame_index,
        report_cels=True,
        report_bounds=True,
    )))
    for frame in report["cels"]:
        if frame["frame"] != frame_index:
            continue
        for cel in frame["cels"]:
            if cel["layer"] == layer_name:
                return cel["x"], cel["y"], cel["w"], cel["h"]
    return None


def pixel(filename, x, y, layer_name="", frame_index=1):
    """Read one pixel back as a lowercase '#rrggbb' string."""
    reading = ok(run(pixel_read.get_pixel_color(filename, x, y, layer_name, frame_index)))
    return reading.split(" ", 1)[0].lower()


def alpha(filename, x, y, layer_name="", frame_index=1):
    """Read one pixel's alpha channel back as an int."""
    reading = ok(run(pixel_read.get_pixel_color(filename, x, y, layer_name, frame_index)))
    return int(reading.rsplit("a=", 1)[1].rstrip(")"))


def composite_alpha(filename, x, y, frame_index=1):
    """Alpha of the flattened composite, which is where cel opacity shows up."""
    reading = ok(run(pixel_read.get_composite_pixel(filename, x, y, frame_index)))
    return int(reading.rsplit("a=", 1)[1].rstrip(")"))
