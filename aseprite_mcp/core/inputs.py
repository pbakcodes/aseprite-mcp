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


def _fail(message: str):
    raise InputError(message)
