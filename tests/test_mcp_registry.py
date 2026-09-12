"""MCP server surface check.

The other test modules exercise tools by importing their Python functions
directly, which would still pass if a tool stopped being registered with
the FastMCP server. This module asserts the registry itself, so a missing
``@mcp.tool()`` decorator or a name collision fails CI.
"""
import pathlib
import sys

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
