"""The per-file coverage gate itself (scripts/check_file_coverage.py).

The gate is what stops a single module rotting behind a healthy project
total, so its own logic is worth testing: a script that silently passes on
a malformed report would be worse than no gate at all.
"""
import importlib.util
import json
import pathlib

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check_file_coverage.py"

spec = importlib.util.spec_from_file_location("check_file_coverage", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def report(files):
    """Build a coverage-json-shaped report from {path: (stmts, covered, branches, covered_branches)}."""
    return {
        "files": {
            path: {
                "summary": {
                    "num_statements": stmts,
                    "covered_lines": covered,
                    "num_branches": branches,
                    "covered_branches": covered_branches,
                }
            }
            for path, (stmts, covered, branches, covered_branches) in files.items()
        }
    }


def write(tmp_path, files):
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(report(files)))
    return str(path)


# ── the percentage maths ──────────────────────────────────────────────

def test_statements_and_branches_are_combined():
    entry = report({"x": (80, 40, 20, 10)})["files"]["x"]
    assert gate.combined_percent(entry) == 50.0


def test_a_file_with_no_branches_is_measured_on_statements_alone():
    entry = report({"x": (10, 9, 0, 0)})["files"]["x"]
    assert gate.combined_percent(entry) == 90.0


def test_an_empty_file_counts_as_fully_covered():
    entry = report({"x": (0, 0, 0, 0)})["files"]["x"]
    assert gate.combined_percent(entry) == 100.0


# ── which files the floor applies to ──────────────────────────────────

@pytest.mark.parametrize("path", [
    "aseprite_mcp/core/commands.py",
    "aseprite_mcp/tools/drawing.py",
])
def test_functional_modules_are_in_scope(path):
    assert gate.is_functional(path)


@pytest.mark.parametrize("path", [
    "aseprite_mcp/__init__.py",
    "aseprite_mcp/core/__init__.py",
    "aseprite_mcp/tools/__init__.py",
    "aseprite_mcp/__main__.py",
    "tests/conftest.py",
    "scripts/check_file_coverage.py",
    "aseprite_mcp/tools/notes.txt",
])
def test_everything_else_is_out_of_scope(path):
    assert not gate.is_functional(path)


def test_guide_is_held_to_a_hundred_percent():
    assert gate.floor_for("aseprite_mcp/tools/guide.py") == 100.0
    assert gate.floor_for("aseprite_mcp/tools/drawing.py") == gate.DEFAULT_FLOOR


# ── pass / fail behaviour ─────────────────────────────────────────────

def test_a_healthy_report_passes(tmp_path, capsys):
    path = write(tmp_path, {
        "aseprite_mcp/tools/drawing.py": (100, 95, 20, 19),
        "aseprite_mcp/tools/guide.py": (10, 10, 4, 4),
    })
    assert gate.main([path]) == 0
    assert "Per-file coverage floor" in capsys.readouterr().out


def test_a_module_below_the_floor_fails(tmp_path, capsys):
    path = write(tmp_path, {
        "aseprite_mcp/tools/drawing.py": (100, 50, 0, 0),
        "aseprite_mcp/tools/guide.py": (10, 10, 4, 4),
    })
    assert gate.main([path]) == 1
    assert "FAIL aseprite_mcp/tools/drawing.py" in capsys.readouterr().err


def test_guide_at_ninety_nine_percent_still_fails(tmp_path, capsys):
    """The stricter floor has to actually bite, not round away."""
    path = write(tmp_path, {"aseprite_mcp/tools/guide.py": (100, 99, 0, 0)})
    assert gate.main([path]) == 1
    assert "99.00% < 100%" in capsys.readouterr().err


def test_a_module_exactly_on_the_floor_passes(tmp_path):
    path = write(tmp_path, {"aseprite_mcp/tools/drawing.py": (100, 80, 0, 0)})
    assert gate.main([path]) == 0


def test_a_non_functional_module_is_ignored_even_at_zero(tmp_path):
    path = write(tmp_path, {
        "aseprite_mcp/tools/__init__.py": (20, 0, 0, 0),
        "aseprite_mcp/tools/drawing.py": (100, 100, 0, 0),
    })
    assert gate.main([path]) == 0


def test_an_empty_report_fails_rather_than_passing_silently(tmp_path, capsys):
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"files": {}}))
    assert gate.main([str(path)]) == 1
    assert "lists no files" in capsys.readouterr().err


def test_a_report_without_functional_modules_fails(tmp_path, capsys):
    path = write(tmp_path, {"tests/conftest.py": (10, 10, 0, 0)})
    assert gate.main([path]) == 1
    assert "no functional modules" in capsys.readouterr().err


# ── the job summary ───────────────────────────────────────────────────

def test_the_summary_lists_the_lowest_modules(tmp_path):
    path = write(tmp_path, {
        "aseprite_mcp/tools/drawing.py": (100, 85, 0, 0),
        "aseprite_mcp/tools/export.py": (100, 99, 0, 0),
        "aseprite_mcp/tools/guide.py": (10, 10, 0, 0),
    })
    summary = tmp_path / "summary.md"
    assert gate.main([path, "--summary", str(summary)]) == 0
    written = summary.read_text()
    assert "Per-file coverage floor" in written
    assert "`aseprite_mcp/tools/drawing.py` | 85.00%" in written
    assert "Every functional module clears its floor." in written


def test_the_summary_names_the_failures(tmp_path):
    path = write(tmp_path, {"aseprite_mcp/tools/drawing.py": (100, 10, 0, 0)})
    summary = tmp_path / "summary.md"
    assert gate.main([path, "--summary", str(summary)]) == 1
    written = summary.read_text()
    assert "Below the floor" in written
    assert "`aseprite_mcp/tools/drawing.py`: 10.00%" in written


def test_the_summary_is_appended_not_replaced(tmp_path):
    path = write(tmp_path, {"aseprite_mcp/tools/drawing.py": (10, 10, 0, 0)})
    summary = tmp_path / "summary.md"
    summary.write_text("### Earlier section\n")
    gate.main([path, "--summary", str(summary)])
    assert summary.read_text().startswith("### Earlier section")


# ── the exemption list ────────────────────────────────────────────────

def test_the_exemption_list_is_empty_by_default():
    """Every exemption hides a module; the list has to justify itself."""
    assert gate.EXEMPT == {}, (
        "an exemption needs a reason recorded alongside it: " f"{gate.EXEMPT}"
    )


def test_an_exemption_would_suppress_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "EXEMPT", {"aseprite_mcp/tools/drawing.py": "reason"})
    path = write(tmp_path, {"aseprite_mcp/tools/drawing.py": (100, 1, 0, 0)})
    assert gate.main([path]) == 0
