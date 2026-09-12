"""Validation for structured (list-of-object) tool arguments.

MCP arguments are just JSON, so a client is free to send ``pixels=["red"]``
or ``tiles=[{"col": "1; drop"}]``. Two things go wrong when such a value is
consumed unchecked:

* ``entry.get(...)`` raises ``AttributeError`` and ``int(entry["x"])`` raises
  ``ValueError`` — both escape the tool and surface as a transport-level
  exception instead of a readable reply.
* worse, a field that is interpolated straight into generated Lua is a
  script-injection primitive: ``{"x": "0) os.execute('...') --"}`` closes the
  ``putPixel(`` call and appends attacker Lua. Forcing every numeric field
  through ``int()`` makes that structurally impossible.

Tools raise :class:`InputError` from these helpers and convert it into their
usual controlled error string.
"""

from collections.abc import Mapping


class InputError(ValueError):
    """A caller-supplied structure had the wrong shape or an unusable value."""


# Upper bounds on caller-driven allocation and iteration. Aseprite happily
# accepts a 2**31 canvas or a 65536-pixel brush and then either allocates
# until the machine dies or spins in a per-pixel Lua loop for hours, so a
# single MCP argument is a denial of service without these. Both limits sit
# far above any real pixel-art use.
MAX_CANVAS_SIDE = 8192
MAX_CANVAS_PIXELS = 8192 * 8192
MAX_BRUSH = 256


def check_extent(width: int, height: int) -> str | None:
    """Validate a width/height pair, returning an error message or None.

    The lower bound keeps the wording every caller already returned, so the
    only behaviour change is the ceiling. Aseprite will happily be told to
    fill a 2**31 x 2**31 rectangle and then spend hours on it, which makes
    an unbounded extent a one-argument denial of service.
    """
    if width <= 0 or height <= 0:
        return "Width and height must be > 0"
    if width > MAX_CANVAS_SIDE or height > MAX_CANVAS_SIDE:
        return f"Width and height must be <= {MAX_CANVAS_SIDE}"
    if width * height > MAX_CANVAS_PIXELS:
        return f"Width x height must be at most {MAX_CANVAS_PIXELS} pixels"
    return None


# Canvas dimensions use the same ceiling as any other drawn extent.
check_canvas_size = check_extent


def check_thickness(thickness: int) -> str | None:
    """Validate a stroke width, returning an error message or None."""
    if thickness < 1:
        return "thickness must be >= 1"
    if thickness > MAX_BRUSH:
        return f"thickness must be <= {MAX_BRUSH}"
    return None


def as_mapping(entry: object, index: int, what: str) -> Mapping:
    """Return `entry` when it is a JSON object, else raise InputError."""
    if not isinstance(entry, Mapping):
        return _fail(
            f"{what} #{index + 1} must be an object with named fields, "
            f"got {type(entry).__name__}"
        )
    return entry


def as_int(entry: Mapping, key: str, default: int, index: int, what: str) -> int:
    """Read `key` from `entry` as an int, rejecting anything non-numeric."""
    value = entry.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return _fail(
            f"{what} #{index + 1} field '{key}' must be a number, "
            f"got {type(value).__name__}"
        )
    try:
        return int(value)
    except ValueError:
        return _fail(f"{what} #{index + 1} field '{key}' must be a number, got {value!r}")


def as_point(entry: object, index: int, what: str = "point") -> tuple[int, int]:
    """Validate a ``{"x": int, "y": int}`` entry and return it as a tuple."""
    mapping = as_mapping(entry, index, what)
    return as_int(mapping, "x", 0, index, what), as_int(mapping, "y", 0, index, what)


def as_str(entry: Mapping, key: str, default: str, index: int, what: str) -> str:
    """Read `key` from `entry` as a string, rejecting other JSON types."""
    value = entry.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        return _fail(
            f"{what} #{index + 1} field '{key}' must be a string, "
            f"got {type(value).__name__}"
        )
    return value


def lua_string_list(values, what: str = "name") -> str:
    """Render a list of caller-supplied strings as a Lua array literal.

    Each entry must actually be a string: ``lua_escape`` is ``str.replace``
    under the hood, so a JSON number or object in a ``List[str]`` argument
    used to raise AttributeError straight out of the tool.
    """
    from .commands import lua_escape

    parts = []
    for index, value in enumerate(values or ()):
        if not isinstance(value, str):
            return _fail(
                f"{what} #{index + 1} must be a string, got {type(value).__name__}"
            )
        parts.append(f'"{lua_escape(value)}"')
    return "{" + ",".join(parts) + "}"


def _fail(message: str):
    raise InputError(message)
