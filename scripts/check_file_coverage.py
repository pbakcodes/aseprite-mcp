#!/usr/bin/env python3
"""Per-file coverage floor, read from `coverage json`.

The project-wide `--cov-fail-under` can be satisfied while one module rots,
so this enforces a floor on every functional module as well. It reads a
coverage JSON report produced in the same run, so it needs no network, no
coverage service and no extra dependency.

Usage:
    python scripts/check_file_coverage.py coverage.json [--summary FILE]

Exit status is 0 when every file clears its floor and 1 otherwise, so the
caller can combine it with pytest's own status without losing either.
"""
from __future__ import annotations

import argparse
import json
import sys

# Every functional module under aseprite_mcp/core and aseprite_mcp/tools has
# to clear this. It is a floor, not a target: the suite runs far above it.
DEFAULT_FLOOR = 80.0

# Modules held to a higher standard because they are pure, deterministic and
# have no excuse for an untested branch.
EXACT_FLOORS = {
    "aseprite_mcp/tools/guide.py": 100.0,
}

# Files exempt from the floor, each with the reason it cannot be met without
# writing a test that asserts nothing. Keep this list empty where possible.
EXEMPT: dict[str, str] = {}


def combined_percent(entry: dict) -> float:
    """Statement+branch coverage for one file, matching coverage's own maths."""
    summary = entry["summary"]
    covered = summary["covered_lines"] + summary.get("covered_branches", 0)
    total = summary["num_statements"] + summary.get("num_branches", 0)
    return 100.0 if total == 0 else covered / total * 100.0


def is_functional(path: str) -> bool:
    """True for the modules the floor applies to."""
    if not path.endswith(".py") or path.endswith("__init__.py"):
        return False
    return path.startswith(("aseprite_mcp/core/", "aseprite_mcp/tools/"))


def floor_for(path: str) -> float:
    return EXACT_FLOORS.get(path, DEFAULT_FLOOR)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="path to a coverage json report")
    parser.add_argument("--summary", help="append a markdown table to this file")
    args = parser.parse_args(argv)

    with open(args.report, encoding="utf-8") as handle:
        report = json.load(handle)

    files = report.get("files") or {}
    if not files:
        print("check_file_coverage: the report lists no files", file=sys.stderr)
        return 1

    measured = sorted(
        (combined_percent(entry), path)
        for path, entry in files.items()
        if is_functional(path)
    )
    if not measured:
        print("check_file_coverage: no functional modules in the report",
              file=sys.stderr)
        return 1

    failures = [
        (percent, path) for percent, path in measured
        if path not in EXEMPT and percent + 1e-9 < floor_for(path)
    ]

    print(f"Per-file coverage floor: {DEFAULT_FLOOR:.0f}% "
          f"({len(measured)} functional modules)")
    for percent, path in measured[:5]:
        print(f"  {percent:6.2f}%  {path}")
    for percent, path in failures:
        print(f"FAIL {path}: {percent:.2f}% < {floor_for(path):.0f}%",
              file=sys.stderr)
    for path, reason in EXEMPT.items():
        print(f"  exempt: {path} ({reason})")

    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as handle:
            handle.write("\n### Per-file coverage floor\n\n")
            handle.write(f"- floor: {DEFAULT_FLOOR:.0f}% "
                         f"on {len(measured)} functional modules\n")
            for path, required in sorted(EXACT_FLOORS.items()):
                handle.write(f"- `{path}` must be {required:.0f}%\n")
            handle.write("\n| Lowest modules | Cover |\n| --- | ----: |\n")
            for percent, path in measured[:5]:
                handle.write(f"| `{path}` | {percent:.2f}% |\n")
            if failures:
                handle.write("\n**Below the floor:**\n\n")
                for percent, path in failures:
                    handle.write(f"- `{path}`: {percent:.2f}% "
                                 f"(needs {floor_for(path):.0f}%)\n")
            else:
                handle.write("\nEvery functional module clears its floor.\n")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
