"""Tests for scripts/generate_dashboard.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from generate_dashboard import generate_html, load_metrics


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_metrics(
    *,
    total_cells: int = 5,
    struct_errors: int = 0,
    struct_warnings: int = 0,
    qual_errors: int = 0,
    qual_warnings: int = 0,
    consistency_score: float = 1.0,
    battery_json_coverage: float = 1.0,
    runtime: float = 0.5,
    timestamp: str = "2024-01-15T12:00:00+00:00",
    contributors: dict | None = None,
) -> dict:
    """Build a fake metrics dict matching collect_metrics.py output format."""
    if contributors is None:
        contributors = {"SINTEF": 3, "Microsoft": 2}
    return {
        "timestamp": timestamp,
        "cell_counts": {
            "total": total_cells,
            "by_contributor": contributors,
            "with_battery_json": int(total_cells * battery_json_coverage),
            "battery_json_coverage": battery_json_coverage,
        },
        "consistency_score": consistency_score,
        "structure_errors": struct_errors,
        "structure_warnings": struct_warnings,
        "quality_errors": qual_errors,
        "quality_warnings": qual_warnings,
        "runtime_total_seconds": runtime,
        "runtime_structure_seconds": round(runtime * 0.4, 3),
        "runtime_quality_seconds": round(runtime * 0.6, 3),
    }


# ---------------------------------------------------------------------------
# load_metrics
# ---------------------------------------------------------------------------


def test_load_metrics_reads_json(tmp_path):
    data = make_metrics()
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(data))
    loaded = load_metrics(path)
    assert loaded["cell_counts"]["total"] == 5


def test_load_metrics_raises_on_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json{{{")
    with pytest.raises(json.JSONDecodeError):
        load_metrics(path)


def test_load_metrics_raises_on_missing_file(tmp_path):
    path = tmp_path / "nonexistent.json"
    with pytest.raises(OSError):
        load_metrics(path)


# ---------------------------------------------------------------------------
# generate_html — basic structure
# ---------------------------------------------------------------------------


def test_generate_html_returns_string():
    html = generate_html([])
    assert isinstance(html, str)


def test_generate_html_is_valid_html_skeleton():
    html = generate_html([])
    assert "<!DOCTYPE html>" in html
    assert "<html" in html
    assert "</html>" in html


def test_generate_html_with_no_metrics():
    html = generate_html([])
    assert "N/A" in html or "No data" in html


def test_generate_html_contains_repo_name():
    html = generate_html([], repo_name="my-test-repo")
    assert "my-test-repo" in html


def test_generate_html_contains_dashboard_title():
    html = generate_html([make_metrics()])
    assert "Dashboard" in html or "dashboard" in html


# ---------------------------------------------------------------------------
# generate_html — single metrics entry
# ---------------------------------------------------------------------------


def test_generate_html_shows_pass_status_when_clean():
    html = generate_html([make_metrics()])
    assert "PASS" in html


def test_generate_html_shows_fail_status_on_errors():
    html = generate_html([make_metrics(struct_errors=2)])
    assert "FAIL" in html


def test_generate_html_shows_fail_on_low_consistency():
    html = generate_html([make_metrics(consistency_score=0.9)])
    assert "FAIL" in html


def test_generate_html_shows_cell_count():
    html = generate_html([make_metrics(total_cells=28)])
    assert "28" in html


def test_generate_html_shows_contributor_names():
    html = generate_html([make_metrics(contributors={"SINTEF": 19, "Microsoft": 9})])
    assert "SINTEF" in html
    assert "Microsoft" in html


def test_generate_html_shows_timestamp():
    m = make_metrics(timestamp="2024-06-01T08:00:00+00:00")
    html = generate_html([m])
    assert "2024-06-01" in html


def test_generate_html_shows_consistency_percentage():
    html = generate_html([make_metrics(consistency_score=1.0)])
    assert "100.0%" in html


def test_generate_html_shows_error_counts():
    html = generate_html([make_metrics(struct_errors=3, qual_errors=1)])
    assert "3" in html
    assert "1" in html


# ---------------------------------------------------------------------------
# generate_html — multiple metrics (history)
# ---------------------------------------------------------------------------


def test_generate_html_shows_history_with_multiple_metrics():
    metrics = [
        make_metrics(timestamp="2024-01-01T00:00:00+00:00", total_cells=5),
        make_metrics(timestamp="2024-01-02T00:00:00+00:00", total_cells=6),
        make_metrics(timestamp="2024-01-03T00:00:00+00:00", total_cells=7),
    ]
    html = generate_html(metrics)
    # All three timestamps should appear in history table
    assert "2024-01-01" in html
    assert "2024-01-02" in html
    assert "2024-01-03" in html


def test_generate_html_limits_history_to_10():
    metrics = [
        make_metrics(timestamp=f"2024-01-{i:02d}T00:00:00+00:00")
        for i in range(1, 16)  # 15 entries
    ]
    html = generate_html(metrics)
    # Should show at most 10 history rows (last 10)
    assert "2024-01-06" in html  # 6th from start = last 10 starts at 6
    assert "2024-01-15" in html  # most recent always shown


def test_generate_html_mixed_pass_fail_history():
    metrics = [
        make_metrics(timestamp="2024-01-01T00:00:00+00:00", struct_errors=0),
        make_metrics(timestamp="2024-01-02T00:00:00+00:00", struct_errors=1),
        make_metrics(timestamp="2024-01-03T00:00:00+00:00", struct_errors=0),
    ]
    html = generate_html(metrics)
    assert "PASS" in html
    assert "FAIL" in html
