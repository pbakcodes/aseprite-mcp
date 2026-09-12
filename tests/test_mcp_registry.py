"""MCP server surface check.

The other test modules exercise tools by importing their Python functions
directly, which would still pass if a tool stopped being registered with
the FastMCP server. This module asserts the registry itself, so a missing
``@mcp.tool()`` decorator or a name collision fails CI.
"""
import inspect
import pathlib
import re
import sys
import types

from conftest import run

import aseprite_mcp.tools  # noqa: F401  (registers all tools)
from aseprite_mcp import mcp

# Representative tools from the canvas / layer / drawing / export / text
# groups; the count guards against a whole module silently dropping out.
EXPECTED_TOOLS = (
    "create_canvas",
    "add_layer",
    "draw_rectangle_at",
    "get_sprite_info",
    "export_sprite",
    "export_spritesheet",
    "draw_text",
)
MINIMUM_TOOLS = 100

# Source modules are the stable ownership boundary for the README categories.
# A category may intentionally combine closely related modules.
CATEGORY_MODULES = {
    "Canvas": ("canvas",),
    "Drawing": ("drawing",),
    "Text": ("text",),
    "Layers": ("layers",),
    "Selection & Regions": ("selection",),
    "Effects": ("fx", "native_fx"),
    "Animation": ("animation",),
    "Palette": ("palette",),
    "Transform": ("transform",),
    "Slices": ("slices",),
    "Tilemap": ("tilemap",),
    "Export & Import": ("export",),
    "Inspection": ("pixel_read",),
    "Analysis & Visual Feedback": ("analysis",),
    "Quality": ("quality",),
    "Scene": ("scene",),
    "Preview & Guide": ("preview", "guide"),
    "Scripting": ("script",),
}


def test_registry_exposes_expected_tools():
    tools = run(mcp.list_tools())
    names = [tool.name for tool in tools]

    assert len(names) == len(set(names)), "duplicate tool names registered"
    assert len(names) >= MINIMUM_TOOLS, f"only {len(names)} tools registered"
    assert set(EXPECTED_TOOLS) <= set(names)


def test_every_tool_is_documented():
    tools = run(mcp.list_tools())
    undocumented = [tool.name for tool in tools if not (tool.description or "").strip()]
    assert not undocumented, f"tools without a description: {undocumented}"


def test_every_tool_module_is_imported():
    """A new file under aseprite_mcp/tools/ must be wired into __init__.

    A module that nobody imports registers no tools and is invisible to both
    the server and the coverage report, so this compares the directory on
    disk against the modules actually loaded into ``sys.modules``.
    """
    package_dir = pathlib.Path(aseprite_mcp.tools.__file__).parent
    on_disk = {
        path.stem
        for path in package_dir.glob("*.py")
        if not path.stem.startswith("_")
    }
    imported = {
        name.rpartition(".")[2]
        for name in sys.modules
        if name.startswith("aseprite_mcp.tools.")
    }

    assert on_disk, "no tool modules found on disk"
    assert on_disk <= imported, (
        "tool modules not imported by aseprite_mcp.tools.__init__: "
        f"{sorted(on_disk - imported)}"
    )


def test_readme_tool_catalog_matches_registry():
    """README totals, category counts, and tool tables match the registry."""
    registered = {tool.name for tool in run(mcp.list_tools())}
    expected_by_category = {}
    owned_tools = set()

    for category, module_names in CATEGORY_MODULES.items():
        category_tools = set()
        for module_name in module_names:
            module = getattr(aseprite_mcp.tools, module_name)
            module_tools = {
                name
                for name in dir(module)
                if name in registered
                and inspect.iscoroutinefunction(getattr(module, name))
                and getattr(module, name).__module__ == module.__name__
            }
            assert module_tools, f"{module_name} has no registered tools"
            assert not category_tools & module_tools
            category_tools.update(module_tools)

        assert not owned_tools & category_tools
        owned_tools.update(category_tools)
        expected_by_category[category] = category_tools

    assert owned_tools == registered, (
        f"registered tools without a README category: "
        f"{sorted(registered - owned_tools)}"
    )

    readme = pathlib.Path(__file__).parents[1].joinpath("README.md").read_text()
    headline = re.search(
        r"\*\*(\d+) tools across (\d+) categories\*\*",
        readme,
    )
    assert headline, "README tool-count headline not found"
    assert tuple(map(int, headline.groups())) == (
        len(registered),
        len(expected_by_category),
    )

    category_rows = re.findall(
        r"^\| \[([^\]]+)\]\(#[^)]+\) \| (\d+) \|",
        readme,
        re.MULTILINE,
    )
    assert [name for name, _ in category_rows] == list(expected_by_category)
    documented_counts = {name: int(count) for name, count in category_rows}
    expected_counts = {
        category: len(tools)
        for category, tools in expected_by_category.items()
    }
    assert documented_counts == expected_counts
    assert sum(documented_counts.values()) == len(registered)

    headings = list(re.finditer(r"^### (.+)$", readme, re.MULTILINE))
    documented_by_category = {}
    for index, heading in enumerate(headings):
        category = heading.group(1)
        if category not in expected_by_category:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(readme)
        section = readme[heading.end():end]
        tool_cells = re.findall(r"^\| ((?:`[^`]+`)(?: / `[^`]+`)*) \|", section, re.MULTILINE)
        tools = [
            name
            for cell in tool_cells
            for name in re.findall(r"`([^`]+)`", cell)
        ]
        assert len(tools) == len(set(tools)), f"duplicate tools in {category}"
        documented_by_category[category] = set(tools)

    assert set(documented_by_category) == set(expected_by_category)
    assert documented_by_category == expected_by_category
