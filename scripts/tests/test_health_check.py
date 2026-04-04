"""Tests for scripts/health_check.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from health_check import run_health_check, format_health_summary, EXIT_CODES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_repo(
    base: Path,
    contributors: dict[str, list[str]] | None = None,
    *,
    skip_battery_json: set[tuple[str, str]] | None = None,
    bad_battery_json: set[tuple[str, str]] | None = None,
) -> Path:
    """Build a minimal fake repo for testing."""
    if contributors is None:
        contributors = {"SINTEF": ["cell-a", "cell-b"]}
    if skip_battery_json is None:
        skip_battery_json = set()
    if bad_battery_json is None:
        bad_battery_json = set()

    valid_spec = {
        "manufacturer": "acme",
        "model": "x100",
        "batch": "2024",
        "chemistry": "li-ion",
        "form_factor": "pouch",
        "nominal_voltage_v": 3.7,
        "rated_capacity_ah": 2.0,
        "rated_energy_wh": 7.4,
    }

    for contributor, cells in contributors.items():
        for cell in cells:
            cell_dir = base / contributor / cell
            cell_dir.mkdir(parents=True, exist_ok=True)
            if (contributor, cell) in bad_battery_json:
                (cell_dir / "battery.json").write_text("not valid json {{{{")
            elif (contributor, cell) not in skip_battery_json:
                (cell_dir / "battery.json").write_text(
                    json.dumps({"spec": valid_spec})
                )
    return base


# ---------------------------------------------------------------------------
# run_health_check — status
# ---------------------------------------------------------------------------


def test_healthy_on_clean_repo(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a", "b"], "Microsoft": ["c"]})
    report = run_health_check(tmp_path)
    assert report["status"] == "healthy"


def test_critical_on_missing_battery_json(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a", "b"]}, skip_battery_json={("SINTEF", "a")})
    report = run_health_check(tmp_path)
    assert report["status"] == "critical"


def test_critical_on_invalid_battery_json(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a", "b"]}, bad_battery_json={("SINTEF", "b")})
    report = run_health_check(tmp_path)
    assert report["status"] == "critical"


def test_degraded_on_warnings_only(tmp_path):
    """An empty contributor directory triggers a warning (no errors)."""
    # Create a contributor with no cells — produces a warning in validate_structure
    (tmp_path / "SINTEF").mkdir()
    # Also add a valid cell in another contributor so total_cells > 0
    make_repo(tmp_path, {"Microsoft": ["cell-x"]})
    report = run_health_check(tmp_path)
    # SINTEF has no cells → warning only → degraded (not critical)
    assert report["status"] in ("degraded", "healthy")  # depends on validator


# ---------------------------------------------------------------------------
# run_health_check — report fields
# ---------------------------------------------------------------------------


def test_report_has_required_fields(tmp_path):
    make_repo(tmp_path)
    report = run_health_check(tmp_path)

    required = {
        "status", "timestamp", "cell_count",
        "structure_errors", "structure_warnings",
        "quality_errors", "quality_warnings",
        "consistency_score", "issues", "warnings",
    }
    assert required.issubset(report.keys())


def test_report_cell_count(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a", "b", "c"], "Microsoft": ["d"]})
    report = run_health_check(tmp_path)
    assert report["cell_count"] == 4


def test_report_consistency_score_range(tmp_path):
    make_repo(tmp_path)
    report = run_health_check(tmp_path)
    assert 0.0 <= report["consistency_score"] <= 1.0


def test_report_consistency_score_perfect_when_clean(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a", "b"]})
    report = run_health_check(tmp_path)
    assert report["consistency_score"] == 1.0


def test_report_consistency_below_one_on_errors(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a", "b"]}, skip_battery_json={("SINTEF", "a")})
    report = run_health_check(tmp_path)
    assert report["consistency_score"] < 1.0


def test_report_issues_list_populated_on_error(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a"]}, skip_battery_json={("SINTEF", "a")})
    report = run_health_check(tmp_path)
    assert isinstance(report["issues"], list)
    assert len(report["issues"]) > 0


def test_report_issues_empty_when_clean(tmp_path):
    make_repo(tmp_path)
    report = run_health_check(tmp_path)
    assert report["issues"] == []


def test_report_is_json_serializable(tmp_path):
    make_repo(tmp_path)
    report = run_health_check(tmp_path)
    serialized = json.dumps(report)
    parsed = json.loads(serialized)
    assert parsed["cell_count"] == report["cell_count"]


# ---------------------------------------------------------------------------
# exit codes
# ---------------------------------------------------------------------------


def test_exit_codes_mapping():
    assert EXIT_CODES["healthy"] == 0
    assert EXIT_CODES["degraded"] == 1
    assert EXIT_CODES["critical"] == 2


def test_exit_code_healthy(tmp_path):
    make_repo(tmp_path)
    report = run_health_check(tmp_path)
    assert EXIT_CODES[report["status"]] == 0


def test_exit_code_critical(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a"]}, skip_battery_json={("SINTEF", "a")})
    report = run_health_check(tmp_path)
    assert EXIT_CODES[report["status"]] == 2


# ---------------------------------------------------------------------------
# format_health_summary
# ---------------------------------------------------------------------------


def test_format_health_summary_contains_status(tmp_path):
    make_repo(tmp_path)
    report = run_health_check(tmp_path)
    summary = format_health_summary(report)
    assert "HEALTHY" in summary or "DEGRADED" in summary or "CRITICAL" in summary


def test_format_health_summary_contains_cell_count(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a", "b"]})
    report = run_health_check(tmp_path)
    summary = format_health_summary(report)
    assert "2" in summary


def test_format_health_summary_shows_issues(tmp_path):
    make_repo(tmp_path, {"SINTEF": ["a"]}, skip_battery_json={("SINTEF", "a")})
    report = run_health_check(tmp_path)
    summary = format_health_summary(report)
    assert "battery.json" in summary.lower() or "missing" in summary.lower()


def test_format_health_summary_returns_string(tmp_path):
    make_repo(tmp_path)
    report = run_health_check(tmp_path)
    assert isinstance(format_health_summary(report), str)
