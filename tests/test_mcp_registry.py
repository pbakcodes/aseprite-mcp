"""MCP server surface check.

The other test modules exercise tools by importing their Python functions
directly, which would still pass if a tool stopped being registered with
the FastMCP server. This module asserts the registry itself, so a missing
``@mcp.tool()`` decorator or a name collision fails CI.
"""
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
