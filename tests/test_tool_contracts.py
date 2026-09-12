"""Contract coverage driven by the MCP registry itself.

Rather than hand-listing tools, this module walks every function registered
with the FastMCP server, rebuilds a plausible argument set from the type
hints, and asserts the guarantees that hold for all of them:

* a tool that takes a file path reports a missing file as a normal string;
* no tool ever raises out to the transport, whatever it is handed;
* every registered tool is represented here, so a tool added tomorrow is
  covered on the day it lands instead of silently slipping through.
"""
import asyncio
import inspect
import os
import types
import typing

import pytest
from conftest import BASE, new_sprite, ok, run

import aseprite_mcp.tools as tools_pkg
from aseprite_mcp import mcp

MISSING = f"{BASE}/does-not-exist.aseprite"
MISSING_DIR = f"{BASE}/does-not-exist-dir"

# Tools that do not touch a caller-named input file at all.
NO_INPUT_FILE = {
    "list_palette_presets",
    "generate_color_ramp",
    "list_convolution_matrices",
    "animation_workflow_guide",
    "list_text_fonts",
    "measure_text",
    "run_lua_script",
    "start_preview_server",
    "stop_preview_server",
}

# Parameters whose value must name an existing *input* file for the guard to
# be the thing under test.
PATH_PARAMS = ("filename", "source_filename")

# Tools whose `filename` is an output path they create, so "not found" is the
# normal case rather than the error under test.
OUTPUT_FILE_TOOLS = {"create_canvas"}

# Tools that reach their missing-file guard only after another check fires.
GUARD_AFTER_VALIDATION = {
    "apply_palette_preset",   # unknown preset is rejected first
    "run_lua_script",         # empty/!valid script is rejected first
}


def tool_functions():
    """Every @mcp.tool function, as {name: function}."""
    found = {}
    for module_name in dir(tools_pkg):
        module = getattr(tools_pkg, module_name)
        if not isinstance(module, types.ModuleType):
            continue
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if inspect.iscoroutinefunction(attr) and attr.__module__ == module.__name__:
                found[attr_name] = attr
    return found


REGISTERED = {tool.name for tool in asyncio.run(mcp.list_tools())}
FUNCTIONS = {name: fn for name, fn in tool_functions().items() if name in REGISTERED}


def sample_for(param, existing_file):
    """A plausible argument for one parameter, from its name and annotation."""
    name = param.name
    if name in PATH_PARAMS:
        return existing_file
    if name in ("target_filename", "output_filename"):
        return f"{BASE}/contract-out.png"
    if name == "output_directory":
        return f"{BASE}/contract-out-dir"
    if name == "directory":
        return BASE
    if name == "image_path":
        return f"{BASE}/contract-in.png"
    if name == "script":
        return 'print("OK")'

    annotation = param.annotation
    origin = typing.get_origin(annotation)
    if origin in (list, typing.List):
        inner = typing.get_args(annotation)
        if inner and typing.get_origin(inner[0]) in (dict, typing.Dict):
            return [{"x": 0, "y": 0, "color": "#FFFFFF"}]
        if inner and inner[0] is dict:
            return [{"from": "#FFFFFF", "to": "#000000"}]
        return ["body"]
    if annotation is int:
        return 1
    if annotation is float:
        return 1.0
    if annotation is bool:
        return False
    if annotation is str:
        if "color" in name:
            return "#FFFFFF"
        if name in ("mode", "preset", "matrix", "font"):
            return "definitely-not-valid"
        return "body"
    if param.default is not inspect.Parameter.empty:
        return param.default
    return "body"


def call_with(fn, existing_file, **overrides):
    """Call a tool with synthesised required arguments."""
    signature = inspect.signature(fn)
    kwargs = {}
    for param in signature.parameters.values():
        if param.name in overrides:
            kwargs[param.name] = overrides[param.name]
        elif param.default is inspect.Parameter.empty:
            kwargs[param.name] = sample_for(param, existing_file)
    return run(fn(**kwargs))


@pytest.fixture(scope="module")
def real():
    path = new_sprite("contracts")
    os.makedirs(f"{BASE}/contract-out-dir", exist_ok=True)
    return path


# ── the registry guard ────────────────────────────────────────────────

def test_every_registered_tool_is_reachable_as_a_function():
    """A registered tool that this module cannot import cannot be contract-
    tested, so the gap has to fail loudly."""
    assert REGISTERED - set(FUNCTIONS) == set()
    assert len(FUNCTIONS) == len(REGISTERED) >= 116


def test_no_input_file_exemptions_are_still_real_tools():
    """An exemption for a tool that no longer exists would silently hide a
    tool that does."""
    assert NO_INPUT_FILE <= REGISTERED


def test_every_file_taking_tool_is_covered_by_the_missing_file_check():
    covered = {
        name for name, fn in FUNCTIONS.items()
        if any(p in inspect.signature(fn).parameters for p in PATH_PARAMS)
    }
    assert covered | NO_INPUT_FILE | OUTPUT_FILE_TOOLS == REGISTERED, (
        "tools neither exempted nor covered: "
        f"{sorted(REGISTERED - covered - NO_INPUT_FILE - OUTPUT_FILE_TOOLS)}"
    )


# ── missing input file ────────────────────────────────────────────────

FILE_TOOLS = sorted(
    name for name, fn in FUNCTIONS.items()
    if any(p in inspect.signature(fn).parameters for p in PATH_PARAMS)
    and name not in OUTPUT_FILE_TOOLS
)


@pytest.mark.parametrize("name", FILE_TOOLS)
def test_a_missing_input_file_is_a_controlled_error(name):
    assert not os.path.exists(MISSING)
    result = call_with(FUNCTIONS[name], MISSING)
    assert isinstance(result, str)
    if name in GUARD_AFTER_VALIDATION:
        # an earlier guard fires first; the answer must still be controlled
        assert not result.startswith("Traceback"), result
        return
    assert result == f"File {MISSING} not found", result


def test_the_guard_ordering_exemptions_are_still_accurate():
    """If one of these tools starts checking the file first, the exemption is
    dead weight hiding a real assertion."""
    for name in GUARD_AFTER_VALIDATION:
        result = call_with(FUNCTIONS[name], MISSING)
        assert result != f"File {MISSING} not found", (
            f"{name} now checks the file first; drop it from "
            "GUARD_AFTER_VALIDATION so the strict assertion applies"
        )


def test_create_canvas_writes_to_a_path_that_does_not_exist_yet():
    """The one tool whose `filename` is an output, so "not found" is normal."""
    target = f"{BASE}/contract-created.aseprite"
    if os.path.exists(target):
        os.remove(target)
    ok(run(FUNCTIONS["create_canvas"](8, 8, target)))
    assert os.path.exists(target)


@pytest.mark.parametrize("name", FILE_TOOLS)
def test_a_directory_passed_as_the_input_file_is_a_controlled_error(name):
    """os.path.exists is true for a directory, so the guard falls through to
    Aseprite; the answer must still be a string, never an exception."""
    result = call_with(FUNCTIONS[name], BASE)
    assert isinstance(result, str) and result


# ── nothing raises, whatever the arguments ────────────────────────────

@pytest.mark.parametrize("name", sorted(FUNCTIONS))
def test_no_tool_raises_on_plausible_arguments(real, name):
    result = call_with(FUNCTIONS[name], real)
    assert isinstance(result, str) and result


@pytest.mark.parametrize("name", sorted(FUNCTIONS))
def test_no_tool_raises_on_empty_strings(real, name):
    signature = inspect.signature(FUNCTIONS[name])
    overrides = {
        param.name: ""
        for param in signature.parameters.values()
        if param.annotation is str and param.name not in PATH_PARAMS
        and param.name not in ("script", "directory")
    }
    result = call_with(FUNCTIONS[name], real, **overrides)
    assert isinstance(result, str) and result


@pytest.mark.parametrize("name", sorted(FUNCTIONS))
def test_no_tool_raises_on_extreme_integers(real, name):
    signature = inspect.signature(FUNCTIONS[name])
    overrides = {
        param.name: -(2 ** 31)
        for param in signature.parameters.values()
        if param.annotation is int and "port" not in param.name
    }
    result = call_with(FUNCTIONS[name], real, **overrides)
    assert isinstance(result, str) and result


@pytest.mark.parametrize("name", sorted(FUNCTIONS))
def test_no_tool_raises_on_huge_integers(real, name):
    signature = inspect.signature(FUNCTIONS[name])
    overrides = {
        param.name: 2 ** 31
        for param in signature.parameters.values()
        if param.annotation is int and "port" not in param.name
    }
    result = call_with(FUNCTIONS[name], real, **overrides)
    assert isinstance(result, str) and result


STRUCTURED = sorted(
    name for name, fn in FUNCTIONS.items()
    if any(
        typing.get_origin(param.annotation) in (list, typing.List)
        for param in inspect.signature(fn).parameters.values()
    )
)


@pytest.mark.parametrize("name", STRUCTURED)
@pytest.mark.parametrize("junk", [[], ["oops"], [None], [42], [[1, 2]], [{"nope": 1}]])
def test_structured_arguments_never_leak_a_python_exception(real, name, junk):
    """The whole point of core.inputs: a wrong JSON shape must come back as a
    sentence, not as AttributeError/TypeError/KeyError."""
    signature = inspect.signature(FUNCTIONS[name])
    overrides = {
        param.name: junk
        for param in signature.parameters.values()
        if typing.get_origin(param.annotation) in (list, typing.List)
    }
    result = call_with(FUNCTIONS[name], real, **overrides)
    assert isinstance(result, str) and result
    assert "Traceback" not in result


# ── the registry surface itself ───────────────────────────────────────

def test_registered_names_are_unique_and_documented():
    registry = run(mcp.list_tools())
    names = [tool.name for tool in registry]
    assert len(names) == len(set(names))
    assert all((tool.description or "").strip() for tool in registry)


def test_every_tool_declares_a_json_schema():
    for tool in run(mcp.list_tools()):
        schema = tool.inputSchema
        assert schema.get("type") == "object", tool.name
        assert "properties" in schema, tool.name


def test_required_parameters_match_the_python_signature():
    """A default that exists in Python but not in the schema (or vice versa)
    makes the advertised contract wrong for every client."""
    for tool in run(mcp.list_tools()):
        fn = FUNCTIONS[tool.name]
        expected = {
            param.name
            for param in inspect.signature(fn).parameters.values()
            if param.default is inspect.Parameter.empty
        }
        assert set(tool.inputSchema.get("required", [])) == expected, tool.name
